VALID_USERNAME = "thriftstack"
VALID_PASSWORD = "Bootstraps2026!"

from datetime import timedelta
from io import BytesIO

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_file,
)
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from utils.db import get_connection

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-key-change-later"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=5)

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if username == VALID_USERNAME and password == VALID_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))

        error = "Invalid username or password."

    return render_template("login.html", error=error)

def generate_next_bin_number(conn):
    row = conn.execute(
        """
        SELECT bin_number
        FROM inventory_lots
        ORDER BY CAST(bin_number AS INTEGER) DESC
        LIMIT 1
        """
    ).fetchone()

    if row is None or row["bin_number"] is None:
        return "000001"

    next_number = int(row["bin_number"]) + 1
    return f"{next_number:06d}"


def get_location_name(conn, location_id):
    row = conn.execute(
        "SELECT location_name FROM locations WHERE location_id = ?",
        (location_id,),
    ).fetchone()
    return row["location_name"] if row else None


def normalize_quadrant(location_name, quadrant_value):
    if location_name != "Warehouse":
        return None
    quadrant = (quadrant_value or "").strip().upper()
    return quadrant if quadrant in {"A", "B", "C", "D"} else None


def build_report_data(conn, report_type):
    report_results = []
    report_columns = []
    report_title = "Reports"

    if report_type == "inventory_by_category":
        report_title = "Inventory by Category"
        report_results = conn.execute(
            """
            SELECT
                c.category_name,
                COUNT(il.inventory_lot_id) AS bin_count,
                COALESCE(SUM(il.quantity_on_hand), 0) AS total_units
            FROM categories c
            LEFT JOIN inventory_lots il
                ON c.category_id = il.category_id
            GROUP BY c.category_id, c.category_name
            ORDER BY c.category_name
            """
        ).fetchall()
        report_columns = ["category_name", "bin_count", "total_units"]

    elif report_type == "inventory_by_location":
        report_title = "Inventory by Location"
        report_results = conn.execute(
            """
            SELECT
                l.location_name,
                COALESCE(il.warehouse_quadrant, '') AS warehouse_quadrant,
                COUNT(il.inventory_lot_id) AS bin_count,
                COALESCE(SUM(il.quantity_on_hand), 0) AS total_units
            FROM locations l
            LEFT JOIN inventory_lots il
                ON l.location_id = il.current_location_id
            GROUP BY l.location_id, l.location_name, il.warehouse_quadrant
            ORDER BY l.location_name, il.warehouse_quadrant
            """
        ).fetchall()
        report_columns = ["location_name", "warehouse_quadrant", "bin_count", "total_units"]

    elif report_type == "inventory_by_storage_purpose":
        report_title = "Inventory by Storage Purpose"
        report_results = conn.execute(
            """
            SELECT
                sp.purpose_name,
                COUNT(il.inventory_lot_id) AS bin_count,
                COALESCE(SUM(il.quantity_on_hand), 0) AS total_units
            FROM storage_purposes sp
            LEFT JOIN inventory_lots il
                ON sp.storage_purpose_id = il.storage_purpose_id
            GROUP BY sp.storage_purpose_id, sp.purpose_name
            ORDER BY sp.purpose_name
            """
        ).fetchall()
        report_columns = ["purpose_name", "bin_count", "total_units"]

    elif report_type == "event_inventory":
        report_title = "Event Inventory"
        report_results = conn.execute(
            """
            SELECT
                e.event_name,
                COUNT(il.inventory_lot_id) AS bin_count,
                COALESCE(SUM(il.quantity_on_hand), 0) AS total_units
            FROM events e
            LEFT JOIN inventory_lots il
                ON e.event_id = il.event_id
            GROUP BY e.event_id, e.event_name
            ORDER BY e.event_name
            """
        ).fetchall()
        report_columns = ["event_name", "bin_count", "total_units"]

    elif report_type == "status_summary":
        report_title = "Status Summary"
        report_results = conn.execute(
            """
            SELECT
                status,
                COUNT(*) AS bin_count,
                COALESCE(SUM(quantity_on_hand), 0) AS total_units
            FROM inventory_lots
            GROUP BY status
            ORDER BY status
            """
        ).fetchall()
        report_columns = ["status", "bin_count", "total_units"]

    elif report_type == "transaction_history":
        report_title = "Transaction History"
        report_results = conn.execute(
            """
            SELECT
                it.transaction_datetime,
                it.transaction_type,
                il.bin_number,
                c.category_name,
                COALESCE(it.quantity, 1) AS quantity,
                COALESCE(fl.location_name, '') AS from_location,
                COALESCE(tl.location_name, '') AS to_location
            FROM inventory_transactions it
            JOIN inventory_lots il
                ON it.inventory_lot_id = il.inventory_lot_id
            JOIN categories c
                ON il.category_id = c.category_id
            LEFT JOIN locations fl
                ON it.from_location_id = fl.location_id
            LEFT JOIN locations tl
                ON it.to_location_id = tl.location_id
            ORDER BY it.transaction_datetime DESC, it.transaction_id DESC
            LIMIT 100
            """
        ).fetchall()
        report_columns = [
            "transaction_datetime",
            "transaction_type",
            "bin_number",
            "category_name",
            "quantity",
            "from_location",
            "to_location",
        ]

    return report_title, report_columns, report_results


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def dashboard():
    conn = get_connection()

    summary = conn.execute(
        """
        SELECT
            COUNT(*) AS total_bins,
            COALESCE(SUM(quantity_on_hand), 0) AS total_units,
            COALESCE(SUM(CASE WHEN sp.purpose_name = 'Event' THEN quantity_on_hand ELSE 0 END), 0) AS event_units,
            COALESCE(SUM(CASE WHEN sp.purpose_name = 'Carryover' THEN quantity_on_hand ELSE 0 END), 0) AS carryover_units
        FROM inventory_lots il
        JOIN storage_purposes sp
            ON il.storage_purpose_id = sp.storage_purpose_id
        WHERE il.status = 'active'
        """
    ).fetchone()

    conn.close()

    return render_template("dashboard.html", summary=summary)


@app.route("/inventory")
def inventory():
    conn = get_connection()

    summary = conn.execute(
        """
        SELECT
            COUNT(*) AS total_bins,
            COALESCE(SUM(quantity_on_hand), 0) AS total_units
        FROM inventory_lots
        WHERE status = 'active'
        """
    ).fetchone()

    conn.close()

    return render_template("inventory.html", inventory_summary=summary)


@app.route("/inventory/list")
def inventory_list():
    conn = get_connection()

    lots = conn.execute(
        """
        SELECT
            il.inventory_lot_id,
            il.bin_number,
            c.category_name,
            sp.purpose_name,
            l.location_name,
            il.warehouse_quadrant,
            e.event_name,
            il.quantity_on_hand,
            il.status,
            il.date_added
        FROM inventory_lots il
        JOIN categories c ON il.category_id = c.category_id
        JOIN storage_purposes sp ON il.storage_purpose_id = sp.storage_purpose_id
        JOIN locations l ON il.current_location_id = l.location_id
        LEFT JOIN events e ON il.event_id = e.event_id
        ORDER BY CAST(il.bin_number AS INTEGER)
        """
    ).fetchall()

    conn.close()

    return render_template("inventory_list.html", inventory_lots=lots)


@app.route("/inventory/add", methods=["GET", "POST"])
def add_inventory():
    conn = get_connection()

    if request.method == "POST":
        bin_number = request.form.get("bin_number")
        category_id = request.form.get("category_id")
        storage_purpose_id = request.form.get("storage_purpose_id")
        location_id = request.form.get("current_location_id")
        location_name = get_location_name(conn, location_id)
        warehouse_quadrant = normalize_quadrant(
            location_name, request.form.get("warehouse_quadrant")
        )
        event_id = request.form.get("event_id") or None
        quantity = int(request.form.get("quantity_on_hand") or 1)
        status = request.form.get("status") or "active"

        if location_name == "Warehouse" and warehouse_quadrant is None:
            conn.close()
            return "Warehouse quadrant is required for Warehouse bins.", 400

        cursor = conn.execute(
            """
            INSERT INTO inventory_lots (
                bin_number,
                category_id,
                storage_purpose_id,
                current_location_id,
                warehouse_quadrant,
                event_id,
                quantity_on_hand,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bin_number,
                category_id,
                storage_purpose_id,
                location_id,
                warehouse_quadrant,
                event_id,
                quantity,
                status,
            ),
        )

        conn.execute(
            """
            INSERT INTO inventory_transactions (
                inventory_lot_id,
                transaction_type,
                quantity,
                from_location_id,
                to_location_id,
                event_id,
                reason_note
            )
            VALUES (?, 'add', ?, NULL, ?, ?, ?)
            """,
            (
                cursor.lastrowid,
                quantity,
                location_id,
                event_id,
                f"Bin {bin_number} created",
            ),
        )

        conn.commit()
        conn.close()

        return redirect(url_for("inventory_list"))

    next_bin_number = generate_next_bin_number(conn)
    categories = conn.execute(
        "SELECT * FROM categories WHERE is_active = 1 ORDER BY category_name"
    ).fetchall()
    purposes = conn.execute(
        "SELECT * FROM storage_purposes WHERE is_active = 1 ORDER BY purpose_name"
    ).fetchall()
    locations = conn.execute(
        "SELECT * FROM locations WHERE is_active = 1 ORDER BY location_name"
    ).fetchall()
    events = conn.execute(
        "SELECT * FROM events WHERE is_active = 1 ORDER BY event_name"
    ).fetchall()

    conn.close()

    return render_template(
        "add_inventory.html",
        next_bin_number=next_bin_number,
        categories=categories,
        storage_purposes=purposes,
        locations=locations,
        events=events,
    )


@app.route("/inventory/move", methods=["GET", "POST"])
def move_inventory():
    conn = get_connection()

    if request.method == "POST":
        lot_id = request.form.get("inventory_lot_id")
        to_location_id = request.form.get("to_location_id")

        lot = conn.execute(
            """
            SELECT inventory_lot_id, current_location_id, bin_number
            FROM inventory_lots
            WHERE inventory_lot_id = ?
            """,
            (lot_id,),
        ).fetchone()

        destination_name = get_location_name(conn, to_location_id)
        warehouse_quadrant = normalize_quadrant(
            destination_name, request.form.get("warehouse_quadrant")
        )

        if destination_name == "Warehouse" and warehouse_quadrant is None:
            conn.close()
            return "Warehouse quadrant is required when moving into Warehouse.", 400

        conn.execute(
            """
            UPDATE inventory_lots
            SET current_location_id = ?,
                warehouse_quadrant = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE inventory_lot_id = ?
            """,
            (to_location_id, warehouse_quadrant, lot_id),
        )

        conn.execute(
            """
            INSERT INTO inventory_transactions (
                inventory_lot_id,
                transaction_type,
                quantity,
                from_location_id,
                to_location_id,
                event_id,
                reason_note
            )
            VALUES (?, 'move', 1, ?, ?, NULL, ?)
            """,
            (
                lot_id,
                lot["current_location_id"],
                to_location_id,
                f"Bin {lot['bin_number']} moved",
            ),
        )

        conn.commit()
        conn.close()

        return redirect(url_for("inventory_list"))

    lots = conn.execute(
        """
        SELECT il.inventory_lot_id, il.bin_number, c.category_name, l.location_name
        FROM inventory_lots il
        JOIN categories c ON il.category_id = c.category_id
        JOIN locations l ON il.current_location_id = l.location_id
        WHERE il.status = 'active'
        ORDER BY CAST(il.bin_number AS INTEGER)
        """
    ).fetchall()

    locations = conn.execute(
        "SELECT * FROM locations WHERE is_active = 1 ORDER BY location_name"
    ).fetchall()

    conn.close()

    return render_template("move_inventory.html", inventory_lots=lots, locations=locations)


@app.route("/inventory/deploy", methods=["GET", "POST"])
def deploy_inventory():
    if "deploy_bins" not in session:
        session["deploy_bins"] = []

    conn = get_connection()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_bin":
            bin_number = (request.form.get("bin_number") or "").strip()

            if bin_number:
                row = conn.execute(
                    """
                    SELECT bin_number, status
                    FROM inventory_lots
                    WHERE bin_number = ?
                    """,
                    (bin_number,),
                ).fetchone()

                if row and row["status"] == "active":
                    queued = session.get("deploy_bins", [])
                    if bin_number not in queued:
                        queued.append(bin_number)
                        session["deploy_bins"] = queued

            conn.close()
            return redirect(url_for("deploy_inventory"))

        if action == "submit_deploy":
            queued = session.get("deploy_bins", [])

            if queued:
                placeholders = ",".join(["?"] * len(queued))

                rows = conn.execute(
                    f"""
                    SELECT inventory_lot_id, bin_number, current_location_id
                    FROM inventory_lots
                    WHERE bin_number IN ({placeholders})
                    """,
                    queued,
                ).fetchall()

                conn.execute(
                    f"""
                    UPDATE inventory_lots
                    SET status = 'depleted',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE bin_number IN ({placeholders})
                    """,
                    queued,
                )

                for row in rows:
                    conn.execute(
                        """
                        INSERT INTO inventory_transactions (
                            inventory_lot_id,
                            transaction_type,
                            quantity,
                            from_location_id,
                            to_location_id,
                            event_id,
                            reason_note
                        )
                        VALUES (?, 'deploy', 1, ?, NULL, NULL, ?)
                        """,
                        (
                            row["inventory_lot_id"],
                            row["current_location_id"],
                            f"Bin {row['bin_number']} deployed",
                        ),
                    )

                conn.commit()

            session["deploy_bins"] = []
            conn.close()
            return redirect(url_for("inventory_list"))

        if action == "clear_list":
            session["deploy_bins"] = []
            conn.close()
            return redirect(url_for("deploy_inventory"))

    queued_bins = session.get("deploy_bins", [])
    queued_bin_rows = []

    if queued_bins:
        placeholders = ",".join(["?"] * len(queued_bins))
        queued_bin_rows = conn.execute(
            f"""
            SELECT
                il.bin_number,
                c.category_name,
                l.location_name,
                il.status
            FROM inventory_lots il
            JOIN categories c ON il.category_id = c.category_id
            JOIN locations l ON il.current_location_id = l.location_id
            WHERE il.bin_number IN ({placeholders})
            ORDER BY CAST(il.bin_number AS INTEGER)
            """,
            queued_bins,
        ).fetchall()

    conn.close()

    return render_template("deploy_inventory.html", queued_bins=queued_bin_rows)


@app.route("/inventory/adjust", methods=["GET", "POST"])
def adjust_inventory():
    conn = get_connection()

    if request.method == "POST":
        lot_id = request.form.get("inventory_lot_id")
        adjustment_type = request.form.get("adjustment_type")
        quantity = int(request.form.get("quantity"))
        reason_note = request.form.get("reason_note") or ""

        lot = conn.execute(
            """
            SELECT inventory_lot_id, quantity_on_hand, bin_number, current_location_id, status
            FROM inventory_lots
            WHERE inventory_lot_id = ?
            """,
            (lot_id,),
        ).fetchone()

        current = lot["quantity_on_hand"]

        if adjustment_type == "adjust_up":
            new_quantity = current + quantity
        else:
            new_quantity = max(0, current - quantity)

        new_status = "depleted" if new_quantity == 0 else "active"

        conn.execute(
            """
            UPDATE inventory_lots
            SET quantity_on_hand = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE inventory_lot_id = ?
            """,
            (new_quantity, new_status, lot_id),
        )

        conn.execute(
            """
            INSERT INTO inventory_transactions (
                inventory_lot_id,
                transaction_type,
                quantity,
                from_location_id,
                to_location_id,
                event_id,
                reason_note
            )
            VALUES (?, ?, ?, ?, NULL, NULL, ?)
            """,
            (
                lot_id,
                adjustment_type,
                quantity,
                lot["current_location_id"],
                reason_note or f"Bin {lot['bin_number']} adjusted",
            ),
        )

        conn.commit()
        conn.close()

        return redirect(url_for("inventory_list"))

    lots = conn.execute(
        """
        SELECT inventory_lot_id, bin_number, quantity_on_hand
        FROM inventory_lots
        WHERE status = 'active'
        ORDER BY CAST(bin_number AS INTEGER)
        """
    ).fetchall()

    conn.close()

    return render_template("adjust_inventory.html", inventory_lots=lots)


@app.route("/events")
def events():
    conn = get_connection()

    event_summary = conn.execute(
        """
        SELECT COUNT(CASE WHEN is_active = 1 THEN 1 END) AS active_events
        FROM events
        """
    ).fetchone()

    event_totals = conn.execute(
        """
        SELECT
            COUNT(il.inventory_lot_id) AS total_event_bins,
            COALESCE(SUM(il.quantity_on_hand), 0) AS total_event_units
        FROM inventory_lots il
        WHERE il.event_id IS NOT NULL AND il.status = 'active'
        """
    ).fetchone()

    tallies = conn.execute(
        """
        SELECT
            e.event_name,
            e.start_date,
            e.end_date,
            e.is_active,
            COUNT(il.inventory_lot_id) AS bins_assigned,
            COALESCE(SUM(il.quantity_on_hand), 0) AS total_units
        FROM events e
        LEFT JOIN inventory_lots il
            ON e.event_id = il.event_id
        GROUP BY e.event_id, e.event_name, e.start_date, e.end_date, e.is_active
        ORDER BY e.event_name
        """
    ).fetchall()

    events_list = conn.execute(
        """
        SELECT *
        FROM events
        ORDER BY event_name
        """
    ).fetchall()

    conn.close()

    event_summary = {
        "active_events": event_summary["active_events"],
        "total_event_bins": event_totals["total_event_bins"],
        "total_event_units": event_totals["total_event_units"],
    }

    return render_template(
        "events.html",
        event_summary=event_summary,
        event_tallies=tallies,
        events=events_list,
    )


@app.route("/events/add", methods=["GET", "POST"])
def add_event():
    conn = get_connection()

    if request.method == "POST":
        name = request.form.get("event_name")
        start_date = request.form.get("start_date") or None
        end_date = request.form.get("end_date") or None
        notes = request.form.get("notes") or ""
        is_active = int(request.form.get("is_active", "1"))

        conn.execute(
            """
            INSERT INTO events (event_name, start_date, end_date, notes, is_active)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, start_date, end_date, notes, is_active),
        )

        conn.commit()
        conn.close()

        return redirect(url_for("events"))

    conn.close()
    return render_template("add_event.html")


@app.route("/reports")
def reports():
    conn = get_connection()

    report_summary = conn.execute(
        """
        SELECT
            COUNT(*) AS total_bins,
            COALESCE(SUM(il.quantity_on_hand), 0) AS total_units,
            COALESCE(SUM(CASE WHEN sp.purpose_name = 'Event' THEN il.quantity_on_hand ELSE 0 END), 0) AS event_units,
            COALESCE(SUM(CASE WHEN sp.purpose_name = 'Carryover' THEN il.quantity_on_hand ELSE 0 END), 0) AS carryover_units
        FROM inventory_lots il
        JOIN storage_purposes sp
            ON il.storage_purpose_id = sp.storage_purpose_id
        """
    ).fetchone()

    total_transactions = conn.execute(
        "SELECT COUNT(*) AS total_transactions FROM inventory_transactions"
    ).fetchone()

    report_summary = dict(report_summary)
    report_summary["total_transactions"] = total_transactions["total_transactions"]

    report_type = request.args.get("report_type")
    report_title = "Reports"
    report_columns = []
    report_results = []

    if report_type:
        report_title, report_columns, report_results = build_report_data(conn, report_type)

    conn.close()

    return render_template(
        "reports.html",
        report_summary=report_summary,
        report_title=report_title,
        report_columns=report_columns,
        report_results=report_results,
        selected_report_type=report_type,
    )


@app.route("/reports/download")
def reports_download():
    report_type = request.args.get("report_type")
    if not report_type:
        return redirect(url_for("reports"))

    conn = get_connection()

    report_summary = conn.execute(
        """
        SELECT
            COUNT(*) AS total_bins,
            COALESCE(SUM(il.quantity_on_hand), 0) AS total_units,
            COALESCE(SUM(CASE WHEN sp.purpose_name = 'Event' THEN il.quantity_on_hand ELSE 0 END), 0) AS event_units,
            COALESCE(SUM(CASE WHEN sp.purpose_name = 'Carryover' THEN il.quantity_on_hand ELSE 0 END), 0) AS carryover_units
        FROM inventory_lots il
        JOIN storage_purposes sp
            ON il.storage_purpose_id = sp.storage_purpose_id
        """
    ).fetchone()

    report_title, report_columns, report_results = build_report_data(conn, report_type)
    conn.close()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=0.4 * inch,
        leftMargin=0.4 * inch,
        topMargin=0.4 * inch,
        bottomMargin=0.4 * inch,
    )

    styles = getSampleStyleSheet()
    elements = [
        Paragraph(report_title, styles["Title"]),
        Spacer(1, 0.15 * inch),
        Paragraph(
            (
                f"Total Bins: {report_summary['total_bins']} | "
                f"Total Units: {report_summary['total_units']} | "
                f"Event Units: {report_summary['event_units']} | "
                f"Carryover Units: {report_summary['carryover_units']}"
            ),
            styles["Normal"],
        ),
        Spacer(1, 0.2 * inch),
    ]

    table_data = [[col.replace("_", " ").title() for col in report_columns]]
    for row in report_results:
        table_data.append([str(row[col]) for col in report_columns])

    if len(table_data) == 1:
        table_data.append(["No data"] + [""] * (len(report_columns) - 1))

    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9d9d9")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f4f4")]),
            ]
        )
    )

    elements.append(table)
    doc.build(elements)
    buffer.seek(0)

    filename = f"{report_type}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype="application/pdf")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)