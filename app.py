import csv
import os
from datetime import timedelta
from io import BytesIO, StringIO
from unittest import result

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_file,
)
from sqlalchemy import bindparam, text
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from utils.db import engine, get_connection


app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key-change-later")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=45)

VALID_USERNAME = os.getenv("THRIFTSTACK_USERNAME", "thriftstack").lower()
VALID_PASSWORD = os.getenv("THRIFTSTACK_PASSWORD", "password")


# ---------------------------------------------------------
# AUTH
# ---------------------------------------------------------

@app.before_request
def check_login():
    session.permanent = True
    if request.endpoint not in ("login", "static") and not session.get("logged_in"):
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""

        if username == VALID_USERNAME and password == VALID_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))

        error = "Invalid username or password."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def fetch_one(conn, sql, params=None):
    return conn.execute(text(sql), params or {}).mappings().first()


def fetch_all(conn, sql, params=None):
    return conn.execute(text(sql), params or {}).mappings().all()


def generate_next_bin_number():
    with get_connection() as conn:
        row = fetch_one(
            conn,
            """
            SELECT COALESCE(MAX(CAST(bin_number AS INTEGER)), 0) AS max_bin
            FROM inventory_lots
            WHERE bin_number ~ '^[0-9]+$'
            """
        )

    next_number = int(row["max_bin"]) + 1 if row else 1
    return f"{next_number:06d}"


def get_location_name(conn, location_id):
    row = fetch_one(
        conn,
        """
        SELECT location_name
        FROM locations
        WHERE location_id = :location_id
        """,
        {"location_id": location_id},
    )
    return row["location_name"] if row else None


def normalize_zone(location_name, zone_value):
    if location_name != "Warehouse":
        return None

    zone = (zone_value or "").strip().upper()
    return zone if zone in {"A", "B", "C", "D", "E"} else None


def get_lookup_data():
    with get_connection() as conn:
        categories = fetch_all(
            conn,
            """
            SELECT *
            FROM categories
            WHERE is_active = TRUE
            ORDER BY category_name
            """
        )

        purposes = fetch_all(
            conn,
            """
            SELECT *
            FROM storage_purposes
            WHERE is_active = TRUE
            ORDER BY purpose_name
            """
        )

        locations = fetch_all(
            conn,
            """
            SELECT *
            FROM locations
            WHERE is_active = TRUE
            ORDER BY location_name
            """
        )

        events = fetch_all(
            conn,
            """
            SELECT *
            FROM events
            WHERE is_active = TRUE
            ORDER BY event_name
            """
        )

    return categories, purposes, locations, events


def create_bin(conn, *, bin_number, category_id, storage_purpose_id, location_id, event_id=None, zone=None, note="Bin created"):
    location_name = get_location_name(conn, location_id)
    warehouse_zone = normalize_zone(location_name, zone)

    if location_name == "Warehouse" and warehouse_zone is None:
        raise ValueError("Warehouse zone is required for Warehouse bins.")

    result = conn.execute(
    text(
        """
        INSERT INTO inventory_lots (
            bin_number,
            category_id,
            storage_purpose_id,
            current_location_id,
            warehouse_zone,
            event_id,
            quantity_on_hand,
            status
        )
        VALUES (
            :bin_number,
            :category_id,
            :storage_purpose_id,
            :current_location_id,
            :warehouse_zone,
            :event_id,
            1,
            'active'
        )
        ON CONFLICT (bin_number) DO NOTHING
        RETURNING inventory_lot_id
        """
    ),
    {
        "bin_number": bin_number,
        "category_id": category_id,
        "storage_purpose_id": storage_purpose_id,
        "current_location_id": location_id,
        "warehouse_zone": warehouse_zone,
        "event_id": event_id,
    },
).mappings().first()

    if not result:
        raise ValueError(f"Bin {bin_number} already exists. Refresh and try again.")


    conn.execute(
        text(
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
            VALUES (
                :inventory_lot_id,
                'add',
                1,
                NULL,
                :to_location_id,
                :event_id,
                :reason_note
            )
            """
        ),
        {
            "inventory_lot_id": result["inventory_lot_id"],
            "to_location_id": location_id,
            "event_id": event_id,
            "reason_note": note,
        },
    )

    return result["inventory_lot_id"]


def get_or_create_event(conn, event_name):
    event_name = (event_name or "").strip()
    if not event_name:
        return None

    event = fetch_one(
        conn,
        """
        SELECT event_id
        FROM events
        WHERE event_name = :event_name
        """,
        {"event_name": event_name},
    )

    if event:
        return event["event_id"]

    event_result = conn.execute(
        text(
            """
            INSERT INTO events (event_name, is_active)
            VALUES (:event_name, TRUE)
            RETURNING event_id
            """
        ),
        {"event_name": event_name},
    ).mappings().first()

    return event_result["event_id"]

def get_or_create_category(conn, category_name):
    category_name = (category_name or "").strip()
    if not category_name:
        return None

    category = fetch_one(
        conn,
        """
        SELECT category_id
        FROM categories
        WHERE LOWER(category_name) = LOWER(:category_name)
        """,
        {"category_name": category_name},
    )

    if category:
        return category["category_id"]

    result = conn.execute(
        text(
            """
            INSERT INTO categories (category_name, department, is_active)
            VALUES (:category_name, NULL, TRUE)
            RETURNING category_id
            """
        ),
        {"category_name": category_name},
    ).mappings().first()

    return result["category_id"]

def get_active_inventory_summary():
    with get_connection() as conn:
        return fetch_one(
            conn,
            """
            SELECT
                COUNT(*) AS total_bins,
                COALESCE(SUM(CASE WHEN sp.purpose_name = 'Event' THEN 1 ELSE 0 END), 0) AS event_bins,
                COALESCE(SUM(CASE WHEN sp.purpose_name = 'Carryover' THEN 1 ELSE 0 END), 0) AS carryover_bins
            FROM inventory_lots il
            JOIN storage_purposes sp
                ON il.storage_purpose_id = sp.storage_purpose_id
            WHERE il.status = 'active'
            """
        )


def apply_inventory_action(conn, selected_ids, action, to_location_id=None, warehouse_zone=None):
    selected_ids = [int(x) for x in selected_ids]

    if not selected_ids:
        return

    rows = conn.execute(
        text(
            """
            SELECT inventory_lot_id, bin_number, current_location_id
            FROM inventory_lots
            WHERE inventory_lot_id IN :selected_ids
            """
        ).bindparams(bindparam("selected_ids", expanding=True)),
        {"selected_ids": selected_ids},
    ).mappings().all()

    if action in {"deplete", "delete"}:
        new_status = "depleted" if action == "deplete" else "deleted"

        conn.execute(
            text(
                """
                UPDATE inventory_lots
                SET status = :status,
                    updated_at = CURRENT_TIMESTAMP
                WHERE inventory_lot_id IN :selected_ids
                """
            ).bindparams(bindparam("selected_ids", expanding=True)),
            {"status": new_status, "selected_ids": selected_ids},
        )

        transaction_type = "deplete" if action == "deplete" else "delete"

        for row in rows:
            conn.execute(
                text(
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
                    VALUES (
                        :inventory_lot_id,
                        :transaction_type,
                        1,
                        :from_location_id,
                        NULL,
                        NULL,
                        :reason_note
                    )
                    """
                ),
                {
                    "inventory_lot_id": row["inventory_lot_id"],
                    "transaction_type": transaction_type,
                    "from_location_id": row["current_location_id"],
                    "reason_note": f"Bin {row['bin_number']} marked {new_status}",
                },
            )

    elif action == "move" and to_location_id:
        destination_name = get_location_name(conn, to_location_id)
        normalized_zone = normalize_zone(destination_name, warehouse_zone)

        if destination_name == "Warehouse" and normalized_zone is None:
            raise ValueError("Warehouse zone is required when moving into Warehouse.")

        conn.execute(
            text(
                """
                UPDATE inventory_lots
                SET current_location_id = :to_location_id,
                    warehouse_zone = :warehouse_zone,
                    updated_at = CURRENT_TIMESTAMP
                WHERE inventory_lot_id IN :selected_ids
                """
            ).bindparams(bindparam("selected_ids", expanding=True)),
            {
                "to_location_id": to_location_id,
                "warehouse_zone": normalized_zone,
                "selected_ids": selected_ids,
            },
        )

        for row in rows:
            conn.execute(
                text(
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
                    VALUES (
                        :inventory_lot_id,
                        'move',
                        1,
                        :from_location_id,
                        :to_location_id,
                        NULL,
                        :reason_note
                    )
                    """
                ),
                {
                    "inventory_lot_id": row["inventory_lot_id"],
                    "from_location_id": row["current_location_id"],
                    "to_location_id": to_location_id,
                    "reason_note": f"Bin {row['bin_number']} moved",
                },
            )


# ---------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------

@app.route("/")
def dashboard():
    categories, purposes, locations, events = get_lookup_data()

    return render_template(
        "dashboard.html",
        summary=get_active_inventory_summary(),
        next_bin_number=generate_next_bin_number(),
        categories=categories,
        storage_purposes=purposes,
        locations=locations,
        events=events,
    )


@app.route("/inventory/quick-add", methods=["POST"])
def quick_add_inventory():
    try:
        with engine.begin() as conn:
            create_bin(
                conn,
                bin_number=request.form.get("bin_number"),
                category_id=request.form.get("category_id"),
                storage_purpose_id=request.form.get("storage_purpose_id"),
                location_id=request.form.get("current_location_id"),
                event_id=request.form.get("event_id") or None,
                zone=request.form.get("warehouse_zone"),
                note=f"Bin {request.form.get('bin_number')} created from dashboard",
            )
    except ValueError as error:
        return str(error), 400

    return redirect(url_for("dashboard"))


# ---------------------------------------------------------
# INVENTORY
# ---------------------------------------------------------

@app.route("/inventory")
def inventory():
    return render_template("inventory.html", inventory_summary=get_active_inventory_summary())


@app.route("/inventory/list", methods=["GET", "POST"])
def inventory_list():
    search = (request.args.get("search") or "").strip()

    if request.method == "POST":
        search = (request.form.get("search") or "").strip()
        action = request.form.get("action")
        selected_bins = request.form.getlist("selected_bins")

        if selected_bins:
            try:
                with engine.begin() as conn:
                    apply_inventory_action(
                        conn,
                        selected_bins,
                        action,
                        to_location_id=request.form.get("to_location_id"),
                        warehouse_zone=request.form.get("warehouse_zone"),
                    )
            except ValueError as error:
                return str(error), 400

        return redirect(url_for("inventory_list", search=search))

    with get_connection() as conn:
        params = {}
        search_clause = ""

        if search:
            search_clause = """
                AND (
                    LOWER(il.bin_number) LIKE LOWER(:term)
                    OR LOWER(c.category_name) LIKE LOWER(:term)
                    OR LOWER(sp.purpose_name) LIKE LOWER(:term)
                    OR LOWER(COALESCE(e.event_name, '')) LIKE LOWER(:term)
                )
            """
            params["term"] = f"%{search}%"

        lots = fetch_all(
            conn,
            f"""
            SELECT
                il.inventory_lot_id,
                il.bin_number,
                c.category_name,
                sp.purpose_name,
                l.location_name,
                il.warehouse_zone,
                e.event_name,
                il.status,
                il.date_added
            FROM inventory_lots il
            JOIN categories c ON il.category_id = c.category_id
            JOIN storage_purposes sp ON il.storage_purpose_id = sp.storage_purpose_id
            JOIN locations l ON il.current_location_id = l.location_id
            LEFT JOIN events e ON il.event_id = e.event_id
            WHERE il.status = 'active'
            {search_clause}
            ORDER BY CAST(il.bin_number AS INTEGER)
            """,
            params,
        )

        locations = fetch_all(
            conn,
            """
            SELECT *
            FROM locations
            WHERE is_active = TRUE
            ORDER BY location_name
            """
        )

    return render_template(
        "inventory_list.html",
        inventory_lots=lots,
        locations=locations,
        search=search,
    )


@app.route("/inventory/add", methods=["GET", "POST"])
def add_inventory():
    if request.method == "POST":
        try:
            with engine.begin() as conn:
                create_bin(
                    conn,
                    bin_number=request.form.get("bin_number"),
                    category_id=request.form.get("category_id"),
                    storage_purpose_id=request.form.get("storage_purpose_id"),
                    location_id=request.form.get("current_location_id"),
                    event_id=request.form.get("event_id") or None,
                    zone=request.form.get("warehouse_zone"),
                    note=f"Bin {request.form.get('bin_number')} created",
                )
        except ValueError as error:
            return str(error), 400

        return redirect(url_for("inventory_list"))

    categories, purposes, locations, events = get_lookup_data()

    return render_template(
        "add_inventory.html",
        next_bin_number=generate_next_bin_number(),
        categories=categories,
        storage_purposes=purposes,
        locations=locations,
        events=events,
    )


@app.route("/inventory/upload", methods=["GET", "POST"])
def upload_bins():
    if request.method == "POST":
        uploaded_file = request.files.get("csv_file")

        if not uploaded_file:
            return "No file uploaded", 400

        stream = StringIO(uploaded_file.stream.read().decode("utf-8-sig"))
        reader = csv.DictReader(stream)

        if not reader.fieldnames:
            return "CSV is missing headers.", 400

        created_count = 0
        skipped_count = 0
        skipped_reasons = []

        def clean(value):
            return (value or "").strip()

        def get_value(row, *keys):
            for key in keys:
                value = row.get(key)
                if value is not None and str(value).strip() != "":
                    return str(value).strip()
            return ""

        with engine.begin() as conn:
            for row_number, row in enumerate(reader, start=2):
                raw_bin_number = get_value(row, "bin_number", "Bin Number", "Bin", "bin")
                category_name = get_value(row, "category", "Category")
                purpose_name = get_value(row, "storage_purpose", "Purpose", "purpose")
                location_name = get_value(row, "location", "Location")
                zone = get_value(row, "warehouse_zone", "Zone", "zone", "warehouse_quadrant").upper()
                event_name = get_value(row, "event", "Event")

                if raw_bin_number:
                    bin_number = raw_bin_number.zfill(6)
                else:
                    bin_number = generate_next_bin_number()

                if not category_name or not purpose_name or not location_name:
                    skipped_count += 1
                    skipped_reasons.append(
                        f"Row {row_number}: missing category, purpose, or location."
                    )
                    continue

                existing = fetch_one(
                    conn,
                    """
                    SELECT inventory_lot_id
                    FROM inventory_lots
                    WHERE bin_number = :bin_number
                    """,
                    {"bin_number": bin_number},
                )

                if existing:
                    skipped_count += 1
                    skipped_reasons.append(
                        f"Row {row_number}: bin {bin_number} already exists."
                    )
                    continue

                category_id = get_or_create_category(conn, category_name)

                purpose = fetch_one(
                    conn,
                    """
                    SELECT storage_purpose_id
                    FROM storage_purposes
                    WHERE LOWER(purpose_name) = LOWER(:purpose_name)
                    """,
                    {"purpose_name": purpose_name},
                )

                location = fetch_one(
                    conn,
                    """
                    SELECT location_id, location_name
                    FROM locations
                    WHERE LOWER(location_name) = LOWER(:location_name)
                    """,
                    {"location_name": location_name},
                )

                if not category:
                    skipped_count += 1
                    skipped_reasons.append(
                        f"Row {row_number}: category '{category_name}' was not found."
                    )
                    continue

                if not purpose:
                    skipped_count += 1
                    skipped_reasons.append(
                        f"Row {row_number}: purpose '{purpose_name}' was not found."
                    )
                    continue

                if not location:
                    skipped_count += 1
                    skipped_reasons.append(
                        f"Row {row_number}: location '{location_name}' was not found."
                    )
                    continue

                if location["location_name"] == "Warehouse" and zone not in {"A", "B", "C", "D", "E"}:
                    skipped_count += 1
                    skipped_reasons.append(
                        f"Row {row_number}: Warehouse bins require zone A, B, C, D, or E."
                    )
                    continue

                if location["location_name"] != "Warehouse":
                    zone = ""

                event_id = get_or_create_event(conn, event_name)

                try:
                    create_bin(
                        conn,
                        bin_number=bin_number,
                        category_id=category_id,
                        storage_purpose_id=purpose["storage_purpose_id"],
                        location_id=location["location_id"],
                        event_id=event_id,
                        zone=zone,
                        note=f"Bin {bin_number} uploaded from CSV",
                    )
                    created_count += 1

                except ValueError as error:
                    skipped_count += 1
                    skipped_reasons.append(
                        f"Row {row_number}: {str(error)}"
                    )
                    continue

        if skipped_reasons:
            return (
                "<h2>Upload Complete</h2>"
                f"<p>Created: {created_count}</p>"
                f"<p>Skipped: {skipped_count}</p>"
                "<h3>Skipped Rows</h3>"
                "<ul>"
                + "".join(f"<li>{reason}</li>" for reason in skipped_reasons[:50])
                + "</ul>"
                "<p><a href='/inventory/list'>Back to Inventory</a></p>"
            )

        return redirect(url_for("inventory_list"))

    return render_template("upload_bins.html")

# ---------------------------------------------------------
# EVENTS
# ---------------------------------------------------------

@app.route("/events")
def events():
    with get_connection() as conn:
        summary = fetch_one(
            conn,
            """
            SELECT
                COUNT(*) FILTER (WHERE is_active = TRUE) AS active_events,
                COUNT(il.inventory_lot_id) FILTER (WHERE il.status = 'active') AS total_event_bins
            FROM events e
            LEFT JOIN inventory_lots il
                ON e.event_id = il.event_id
            """
        )

        event_rows = fetch_all(
            conn,
            """
            SELECT
                e.event_id,
                e.event_name,
                e.start_date,
                e.end_date,
                e.is_active,
                COUNT(il.inventory_lot_id) FILTER (WHERE il.status = 'active') AS bins_assigned
            FROM events e
            LEFT JOIN inventory_lots il
                ON e.event_id = il.event_id
            GROUP BY e.event_id, e.event_name, e.start_date, e.end_date, e.is_active
            ORDER BY e.event_name
            """
        )

    return render_template(
        "events.html",
        events=event_rows,
        event_summary=summary,
    )


@app.route("/events/add", methods=["GET", "POST"])
def add_event():
    if request.method == "POST":
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO events (event_name, start_date, end_date, notes, is_active)
                    VALUES (:event_name, :start_date, :end_date, :notes, :is_active)
                    """
                ),
                {
                    "event_name": request.form.get("event_name"),
                    "start_date": request.form.get("start_date") or None,
                    "end_date": request.form.get("end_date") or None,
                    "notes": request.form.get("notes") or "",
                    "is_active": request.form.get("is_active", "1") == "1",
                },
            )

        return redirect(url_for("events"))

    return render_template("add_event.html")


@app.route("/events/delete/<int:event_id>", methods=["POST"])
def delete_event(event_id):
    with engine.begin() as conn:
        active_bins = fetch_one(
            conn,
            """
            SELECT COUNT(*) AS active_bin_count
            FROM inventory_lots
            WHERE event_id = :event_id
              AND status = 'active'
            """,
            {"event_id": event_id},
        )

        if active_bins["active_bin_count"] > 0:
            return "This event cannot be archived because it still has active bins assigned.", 400

        conn.execute(
            text(
                """
                UPDATE events
                SET is_active = FALSE
                WHERE event_id = :event_id
                """
            ),
            {"event_id": event_id},
        )

    return redirect(url_for("events"))


# ---------------------------------------------------------
# REPORTS
# ---------------------------------------------------------

def build_report_data(conn, report_type):
    reports = {
        "inventory_by_category": (
            "Active Bins by Category",
            ["category_name", "bin_count"],
            """
            SELECT c.category_name, COUNT(il.inventory_lot_id) AS bin_count
            FROM categories c
            LEFT JOIN inventory_lots il
                ON c.category_id = il.category_id
               AND il.status = 'active'
            GROUP BY c.category_id, c.category_name
            ORDER BY c.category_name
            """,
        ),
        "inventory_by_location": (
            "Active Bins by Location",
            ["location_name", "warehouse_zone", "bin_count"],
            """
            SELECT
                l.location_name,
                COALESCE(il.warehouse_zone, '') AS warehouse_zone,
                COUNT(il.inventory_lot_id) AS bin_count
            FROM locations l
            LEFT JOIN inventory_lots il
                ON l.location_id = il.current_location_id
               AND il.status = 'active'
            GROUP BY l.location_id, l.location_name, il.warehouse_zone
            ORDER BY l.location_name, il.warehouse_zone
            """,
        ),
        "inventory_by_storage_purpose": (
            "Active Bins by Storage Purpose",
            ["purpose_name", "bin_count"],
            """
            SELECT sp.purpose_name, COUNT(il.inventory_lot_id) AS bin_count
            FROM storage_purposes sp
            LEFT JOIN inventory_lots il
                ON sp.storage_purpose_id = il.storage_purpose_id
               AND il.status = 'active'
            GROUP BY sp.storage_purpose_id, sp.purpose_name
            ORDER BY sp.purpose_name
            """,
        ),
        "event_inventory": (
            "Active Event Bins",
            ["event_name", "bin_count"],
            """
            SELECT e.event_name, COUNT(il.inventory_lot_id) AS bin_count
            FROM events e
            LEFT JOIN inventory_lots il
                ON e.event_id = il.event_id
               AND il.status = 'active'
            GROUP BY e.event_id, e.event_name
            ORDER BY e.event_name
            """,
        ),
        "status_summary": (
            "Bin Status Summary",
            ["status", "bin_count"],
            """
            SELECT status, COUNT(*) AS bin_count
            FROM inventory_lots
            GROUP BY status
            ORDER BY status
            """,
        ),
        "transaction_history": (
            "Transaction History",
            [
                "transaction_datetime",
                "transaction_type",
                "bin_number",
                "category_name",
                "from_location",
                "to_location",
                "reason_note",
            ],
            """
            SELECT
                it.transaction_datetime,
                it.transaction_type,
                il.bin_number,
                c.category_name,
                COALESCE(fl.location_name, '') AS from_location,
                COALESCE(tl.location_name, '') AS to_location,
                COALESCE(it.reason_note, '') AS reason_note
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
            """,
        ),
    }

    if report_type not in reports:
        return "Reports", [], []

    title, columns, sql = reports[report_type]
    return title, columns, fetch_all(conn, sql)


@app.route("/reports")
def reports():
    with get_connection() as conn:
        report_summary = get_active_inventory_summary()
        total_transactions = fetch_one(
            conn,
            """
            SELECT COUNT(*) AS total_transactions
            FROM inventory_transactions
            """
        )

        report_summary = dict(report_summary)
        report_summary["total_transactions"] = total_transactions["total_transactions"]

        report_type = request.args.get("report_type")
        report_title, report_columns, report_results = build_report_data(conn, report_type)

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

    with get_connection() as conn:
        report_summary = get_active_inventory_summary()
        report_title, report_columns, report_results = build_report_data(conn, report_type)

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
                f"Active Bins: {report_summary['total_bins']} | "
                f"Event Bins: {report_summary['event_bins']} | "
                f"Carryover Bins: {report_summary['carryover_bins']}"
            ),
            styles["Normal"],
        ),
        Spacer(1, 0.2 * inch),
    ]

    table_data = [[col.replace("_", " ").title() for col in report_columns]]

    for row in report_results:
        table_data.append([str(row[col]) for col in report_columns])

    if len(table_data) == 1:
        table_data.append(["No data"] + [""] * max(len(report_columns) - 1, 0))

    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9d9d9")),
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

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{report_type}.pdf",
        mimetype="application/pdf",
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)