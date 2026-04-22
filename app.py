import os
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
from sqlalchemy import text
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from utils.db import engine, get_connection

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key-change-later")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=5)

VALID_USERNAME = os.getenv("THRIFTSTACK_USERNAME", "thriftstack")
VALID_PASSWORD = os.getenv("THRIFTSTACK_PASSWORD", "password")


@app.before_request
def check_login():
    session.permanent = True
    if request.endpoint not in ("login", "static") and not session.get("logged_in"):
        return redirect(url_for("login"))


def generate_next_bin_number():
    with get_connection() as conn:
        row = conn.execute(
            text(
                """
                SELECT bin_number
                FROM inventory_lots
                ORDER BY CAST(bin_number AS INTEGER) DESC
                LIMIT 1
                """
            )
        ).mappings().first()

    if row is None or row["bin_number"] is None:
        return "000001"

    next_number = int(row["bin_number"]) + 1
    return f"{next_number:06d}"


def get_location_name(conn, location_id):
    row = conn.execute(
        text(
            """
            SELECT location_name
            FROM locations
            WHERE location_id = :location_id
            """
        ),
        {"location_id": location_id},
    ).mappings().first()
    return row["location_name"] if row else None


def normalize_quadrant(location_name, quadrant_value):
    if location_name != "Warehouse":
        return None

    quadrant = (quadrant_value or "").strip().upper()
    return quadrant if quadrant in {"A", "B", "C", "D"} else None


def get_quick_bin_lookups():
    with get_connection() as conn:
        categories = conn.execute(
            text(
                """
                SELECT *
                FROM categories
                WHERE is_active = TRUE
                ORDER BY category_name
                """
            )
        ).mappings().all()

        purposes = conn.execute(
            text(
                """
                SELECT *
                FROM storage_purposes
                WHERE is_active = TRUE
                ORDER BY purpose_name
                """
            )
        ).mappings().all()

        locations = conn.execute(
            text(
                """
                SELECT *
                FROM locations
                WHERE is_active = TRUE
                ORDER BY location_name
                """
            )
        ).mappings().all()

        events = conn.execute(
            text(
                """
                SELECT *
                FROM events
                WHERE is_active = TRUE
                ORDER BY event_name
                """
            )
        ).mappings().all()

    return categories, purposes, locations, events


def build_report_data(conn, report_type):
    report_results = []
    report_columns = []
    report_title = "Reports"

    if report_type == "inventory_by_category":
        report_title = "Active Bins by Category"
        report_results = conn.execute(
            text(
                """
                SELECT
                    c.category_name,
                    COUNT(il.inventory_lot_id) AS bin_count
                FROM categories c
                LEFT JOIN inventory_lots il
                    ON c.category_id = il.category_id
                   AND il.status = 'active'
                GROUP BY c.category_id, c.category_name
                ORDER BY c.category_name
                """
            )
        ).mappings().all()
        report_columns = ["category_name", "bin_count"]

    elif report_type == "inventory_by_location":
        report_title = "Active Bins by Location"
        report_results = conn.execute(
            text(
                """
                SELECT
                    l.location_name,
                    COALESCE(il.warehouse_quadrant, '') AS warehouse_quadrant,
                    COUNT(il.inventory_lot_id) AS bin_count
                FROM locations l
                LEFT JOIN inventory_lots il
                    ON l.location_id = il.current_location_id
                   AND il.status = 'active'
                GROUP BY l.location_id, l.location_name, il.warehouse_quadrant
                ORDER BY l.location_name, il.warehouse_quadrant
                """
            )
        ).mappings().all()
        report_columns = ["location_name", "warehouse_quadrant", "bin_count"]

    elif report_type == "inventory_by_storage_purpose":
        report_title = "Active Bins by Storage Purpose"
        report_results = conn.execute(
            text(
                """
                SELECT
                    sp.purpose_name,
                    COUNT(il.inventory_lot_id) AS bin_count
                FROM storage_purposes sp
                LEFT JOIN inventory_lots il
                    ON sp.storage_purpose_id = il.storage_purpose_id
                   AND il.status = 'active'
                GROUP BY sp.storage_purpose_id, sp.purpose_name
                ORDER BY sp.purpose_name
                """
            )
        ).mappings().all()
        report_columns = ["purpose_name", "bin_count"]

    elif report_type == "event_inventory":
        report_title = "Active Event Bins"
        report_results = conn.execute(
            text(
                """
                SELECT
                    e.event_name,
                    COUNT(il.inventory_lot_id) AS bin_count
                FROM events e
                LEFT JOIN inventory_lots il
                    ON e.event_id = il.event_id
                   AND il.status = 'active'
                GROUP BY e.event_id, e.event_name
                ORDER BY e.event_name
                """
            )
        ).mappings().all()
        report_columns = ["event_name", "bin_count"]

    elif report_type == "status_summary":
        report_title = "Bin Status Summary"
        report_results = conn.execute(
            text(
                """
                SELECT
                    status,
                    COUNT(*) AS bin_count
                FROM inventory_lots
                GROUP BY status
                ORDER BY status
                """
            )
        ).mappings().all()
        report_columns = ["status", "bin_count"]

    elif report_type == "transaction_history":
        report_title = "Transaction History"
        report_results = conn.execute(
            text(
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
                """
            )
        ).mappings().all()
        report_columns = [
            "transaction_datetime",
            "transaction_type",
            "bin_number",
            "category_name",
            "from_location",
            "to_location",
            "reason_note",
        ]

    return report_title, report_columns, report_results


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


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def dashboard():
    with get_connection() as conn:
        summary = conn.execute(
            text(
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
        ).mappings().first()

    categories, purposes, locations, events = get_quick_bin_lookups()

    return render_template(
        "dashboard.html",
        summary=summary,
        next_bin_number=generate_next_bin_number(),
        categories=categories,
        storage_purposes=purposes,
        locations=locations,
        events=events,
    )


@app.route("/inventory/quick-add", methods=["POST"])
def quick_add_inventory():
    bin_number = request.form.get("bin_number")
    category_id = request.form.get("category_id")
    storage_purpose_id = request.form.get("storage_purpose_id")
    location_id = request.form.get("current_location_id")
    event_id = request.form.get("event_id") or None

    with engine.begin() as conn:
        location_name = get_location_name(conn, location_id)
        warehouse_quadrant = normalize_quadrant(
            location_name, request.form.get("warehouse_quadrant")
        )

        if location_name == "Warehouse" and warehouse_quadrant is None:
            return "Warehouse quadrant is required for Warehouse bins.", 400

        result = conn.execute(
            text(
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
                VALUES (
                    :bin_number,
                    :category_id,
                    :storage_purpose_id,
                    :current_location_id,
                    :warehouse_quadrant,
                    :event_id,
                    1,
                    'active'
                )
                RETURNING inventory_lot_id
                """
            ),
            {
                "bin_number": bin_number,
                "category_id": category_id,
                "storage_purpose_id": storage_purpose_id,
                "current_location_id": location_id,
                "warehouse_quadrant": warehouse_quadrant,
                "event_id": event_id,
            },
        ).mappings().first()

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
                "reason_note": f"Bin {bin_number} created from dashboard",
            },
        )

    return redirect(url_for("dashboard"))


@app.route("/inventory")
def inventory():
    with get_connection() as conn:
        summary = conn.execute(
            text(
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
        ).mappings().first()

    return render_template("inventory.html", inventory_summary=summary)


@app.route("/inventory/list", methods=["GET", "POST"])
def inventory_list():
    search = (request.args.get("search") or "").strip()

    if request.method == "POST":
        action = request.form.get("action")
        selected_bins = request.form.getlist("selected_bins")
        search = (request.form.get("search") or "").strip()

        if selected_bins:
            with engine.begin() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT inventory_lot_id, bin_number, current_location_id
                        FROM inventory_lots
                        WHERE CAST(inventory_lot_id AS TEXT) = ANY(:selected_bins)
                        """
                    ),
                    {"selected_bins": selected_bins},
                ).mappings().all()

                if action == "deplete":
                    conn.execute(
                        text(
                            """
                            UPDATE inventory_lots
                            SET status = 'depleted',
                                updated_at = CURRENT_TIMESTAMP
                            WHERE CAST(inventory_lot_id AS TEXT) = ANY(:selected_bins)
                            """
                        ),
                        {"selected_bins": selected_bins},
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
                                    'deplete',
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
                                "from_location_id": row["current_location_id"],
                                "reason_note": f"Bin {row['bin_number']} marked depleted",
                            },
                        )

                elif action == "delete":
                    conn.execute(
                        text(
                            """
                            UPDATE inventory_lots
                            SET status = 'deleted',
                                updated_at = CURRENT_TIMESTAMP
                            WHERE CAST(inventory_lot_id AS TEXT) = ANY(:selected_bins)
                            """
                        ),
                        {"selected_bins": selected_bins},
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
                                    'delete',
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
                                "from_location_id": row["current_location_id"],
                                "reason_note": f"Bin {row['bin_number']} deleted",
                            },
                        )

                elif action == "move":
                    to_location_id = request.form.get("to_location_id")
                    if to_location_id:
                        destination_name = get_location_name(conn, to_location_id)
                        warehouse_quadrant = normalize_quadrant(
                            destination_name,
                            request.form.get("warehouse_quadrant"),
                        )

                        if destination_name == "Warehouse" and warehouse_quadrant is None:
                            return "Warehouse quadrant is required when moving into Warehouse.", 400

                        conn.execute(
                            text(
                                """
                                UPDATE inventory_lots
                                SET current_location_id = :to_location_id,
                                    warehouse_quadrant = :warehouse_quadrant,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE CAST(inventory_lot_id AS TEXT) = ANY(:selected_bins)
                                """
                            ),
                            {
                                "to_location_id": to_location_id,
                                "warehouse_quadrant": warehouse_quadrant,
                                "selected_bins": selected_bins,
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

        return redirect(url_for("inventory_list", search=search))

    with get_connection() as conn:
        if search:
            lots = conn.execute(
                text(
                    """
                    SELECT
                        il.inventory_lot_id,
                        il.bin_number,
                        c.category_name,
                        sp.purpose_name,
                        l.location_name,
                        il.warehouse_quadrant,
                        e.event_name,
                        il.status,
                        il.date_added
                    FROM inventory_lots il
                    JOIN categories c ON il.category_id = c.category_id
                    JOIN storage_purposes sp ON il.storage_purpose_id = sp.storage_purpose_id
                    JOIN locations l ON il.current_location_id = l.location_id
                    LEFT JOIN events e ON il.event_id = e.event_id
                    WHERE il.status = 'active'
                      AND (
                          il.bin_number ILIKE :term
                          OR c.category_name ILIKE :term
                          OR sp.purpose_name ILIKE :term
                          OR COALESCE(e.event_name, '') ILIKE :term
                      )
                    ORDER BY CAST(il.bin_number AS INTEGER)
                    """
                ),
                {"term": f"%{search}%"},
            ).mappings().all()
        else:
            lots = conn.execute(
                text(
                    """
                    SELECT
                        il.inventory_lot_id,
                        il.bin_number,
                        c.category_name,
                        sp.purpose_name,
                        l.location_name,
                        il.warehouse_quadrant,
                        e.event_name,
                        il.status,
                        il.date_added
                    FROM inventory_lots il
                    JOIN categories c ON il.category_id = c.category_id
                    JOIN storage_purposes sp ON il.storage_purpose_id = sp.storage_purpose_id
                    JOIN locations l ON il.current_location_id = l.location_id
                    LEFT JOIN events e ON il.event_id = e.event_id
                    WHERE il.status = 'active'
                    ORDER BY CAST(il.bin_number AS INTEGER)
                    """
                )
            ).mappings().all()

        locations = conn.execute(
            text(
                """
                SELECT *
                FROM locations
                WHERE is_active = TRUE
                ORDER BY location_name
                """
            )
        ).mappings().all()

    return render_template(
        "inventory_list.html",
        inventory_lots=lots,
        locations=locations,
        search=search,
    )

@app.route("/inventory/add", methods=["GET", "POST"])
def add_inventory():
    if request.method == "POST":
        bin_number = request.form.get("bin_number")
        category_id = request.form.get("category_id")
        storage_purpose_id = request.form.get("storage_purpose_id")
        location_id = request.form.get("current_location_id")
        event_id = request.form.get("event_id") or None

        with engine.begin() as conn:
            location_name = get_location_name(conn, location_id)
            warehouse_quadrant = normalize_quadrant(
                location_name, request.form.get("warehouse_quadrant")
            )

            if location_name == "Warehouse" and warehouse_quadrant is None:
                return "Warehouse quadrant is required for Warehouse bins.", 400

            result = conn.execute(
                text(
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
                    VALUES (
                        :bin_number,
                        :category_id,
                        :storage_purpose_id,
                        :current_location_id,
                        :warehouse_quadrant,
                        :event_id,
                        1,
                        'active'
                    )
                    RETURNING inventory_lot_id
                    """
                ),
                {
                    "bin_number": bin_number,
                    "category_id": category_id,
                    "storage_purpose_id": storage_purpose_id,
                    "current_location_id": location_id,
                    "warehouse_quadrant": warehouse_quadrant,
                    "event_id": event_id,
                },
            ).mappings().first()

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
                    "reason_note": f"Bin {bin_number} created",
                },
            )

        return redirect(url_for("inventory_list"))

    categories, purposes, locations, events = get_quick_bin_lookups()

    return render_template(
        "add_inventory.html",
        next_bin_number=generate_next_bin_number(),
        categories=categories,
        storage_purposes=purposes,
        locations=locations,
        events=events,
    )


@app.route("/inventory/move", methods=["GET", "POST"])
def move_inventory():
    if request.method == "POST":
        lot_id = request.form.get("inventory_lot_id")
        to_location_id = request.form.get("to_location_id")

        with engine.begin() as conn:
            lot = conn.execute(
                text(
                    """
                    SELECT inventory_lot_id, current_location_id, bin_number
                    FROM inventory_lots
                    WHERE inventory_lot_id = :lot_id
                    """
                ),
                {"lot_id": lot_id},
            ).mappings().first()

            destination_name = get_location_name(conn, to_location_id)
            warehouse_quadrant = normalize_quadrant(
                destination_name, request.form.get("warehouse_quadrant")
            )

            if destination_name == "Warehouse" and warehouse_quadrant is None:
                return "Warehouse quadrant is required when moving into Warehouse.", 400

            conn.execute(
                text(
                    """
                    UPDATE inventory_lots
                    SET current_location_id = :to_location_id,
                        warehouse_quadrant = :warehouse_quadrant,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE inventory_lot_id = :lot_id
                    """
                ),
                {
                    "to_location_id": to_location_id,
                    "warehouse_quadrant": warehouse_quadrant,
                    "lot_id": lot_id,
                },
            )

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
                    "inventory_lot_id": lot_id,
                    "from_location_id": lot["current_location_id"],
                    "to_location_id": to_location_id,
                    "reason_note": f"Bin {lot['bin_number']} moved",
                },
            )

        return redirect(url_for("inventory_list"))

    with get_connection() as conn:
        lots = conn.execute(
            text(
                """
                SELECT il.inventory_lot_id, il.bin_number, c.category_name, l.location_name
                FROM inventory_lots il
                JOIN categories c ON il.category_id = c.category_id
                JOIN locations l ON il.current_location_id = l.location_id
                WHERE il.status = 'active'
                ORDER BY CAST(il.bin_number AS INTEGER)
                """
            )
        ).mappings().all()

        locations = conn.execute(
            text(
                """
                SELECT *
                FROM locations
                WHERE is_active = TRUE
                ORDER BY location_name
                """
            )
        ).mappings().all()

    return render_template("move_inventory.html", inventory_lots=lots, locations=locations)


@app.route("/inventory/deploy", methods=["GET", "POST"])
def deploy_inventory():
    if "deploy_bins" not in session:
        session["deploy_bins"] = []

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_bin":
            bin_number = (request.form.get("bin_number") or "").strip()

            if bin_number:
                with get_connection() as conn:
                    row = conn.execute(
                        text(
                            """
                            SELECT bin_number, status
                            FROM inventory_lots
                            WHERE bin_number = :bin_number
                            """
                        ),
                        {"bin_number": bin_number},
                    ).mappings().first()

                if row and row["status"] == "active":
                    queued = session.get("deploy_bins", [])
                    if bin_number not in queued:
                        queued.append(bin_number)
                        session["deploy_bins"] = queued

            return redirect(url_for("deploy_inventory"))

        if action == "submit_deploy":
            queued = session.get("deploy_bins", [])

            if queued:
                with engine.begin() as conn:
                    rows = conn.execute(
                        text(
                            """
                            SELECT inventory_lot_id, bin_number, current_location_id
                            FROM inventory_lots
                            WHERE bin_number = ANY(:queued)
                            """
                        ),
                        {"queued": queued},
                    ).mappings().all()

                    conn.execute(
                        text(
                            """
                            UPDATE inventory_lots
                            SET status = 'depleted',
                                updated_at = CURRENT_TIMESTAMP
                            WHERE bin_number = ANY(:queued)
                            """
                        ),
                        {"queued": queued},
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
                                    'deploy',
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
                                "from_location_id": row["current_location_id"],
                                "reason_note": f"Bin {row['bin_number']} deployed",
                            },
                        )

            session["deploy_bins"] = []
            return redirect(url_for("inventory_list"))

        if action == "clear_list":
            session["deploy_bins"] = []
            return redirect(url_for("deploy_inventory"))

    queued_bins = session.get("deploy_bins", [])

    with get_connection() as conn:
        if queued_bins:
            queued_bin_rows = conn.execute(
                text(
                    """
                    SELECT
                        il.bin_number,
                        c.category_name,
                        l.location_name,
                        il.status
                    FROM inventory_lots il
                    JOIN categories c ON il.category_id = c.category_id
                    JOIN locations l ON il.current_location_id = l.location_id
                    WHERE il.bin_number = ANY(:queued)
                    ORDER BY CAST(il.bin_number AS INTEGER)
                    """
                ),
                {"queued": queued_bins},
            ).mappings().all()
        else:
            queued_bin_rows = []

    return render_template("deploy_inventory.html", queued_bins=queued_bin_rows)


@app.route("/inventory/delete/<int:lot_id>", methods=["POST"])
def delete_inventory(lot_id):
    with engine.begin() as conn:
        lot = conn.execute(
            text(
                """
                SELECT inventory_lot_id, bin_number, current_location_id
                FROM inventory_lots
                WHERE inventory_lot_id = :lot_id
                """
            ),
            {"lot_id": lot_id},
        ).mappings().first()

        if not lot:
            return redirect(url_for("inventory_list"))

        conn.execute(
            text(
                """
                UPDATE inventory_lots
                SET status = 'deleted',
                    updated_at = CURRENT_TIMESTAMP
                WHERE inventory_lot_id = :lot_id
                """
            ),
            {"lot_id": lot_id},
        )

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
                    'delete',
                    1,
                    :from_location_id,
                    NULL,
                    NULL,
                    :reason_note
                )
                """
            ),
            {
                "inventory_lot_id": lot_id,
                "from_location_id": lot["current_location_id"],
                "reason_note": f"Bin {lot['bin_number']} deleted",
            },
        )

    return redirect(url_for("inventory_list"))


@app.route("/events")
def events():
    with get_connection() as conn:
        summary_row = conn.execute(
            text(
                """
                SELECT COUNT(CASE WHEN is_active = TRUE THEN 1 END) AS active_events
                FROM events
                """
            )
        ).mappings().first()

        totals_row = conn.execute(
            text(
                """
                SELECT
                    COUNT(il.inventory_lot_id) AS total_event_bins
                FROM inventory_lots il
                WHERE il.event_id IS NOT NULL
                  AND il.status = 'active'
                """
            )
        ).mappings().first()

        tallies = conn.execute(
            text(
                """
                SELECT
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
        ).mappings().all()

        events_list = conn.execute(
            text(
                """
                SELECT *
                FROM events
                ORDER BY event_name
                """
            )
        ).mappings().all()

    event_summary = {
        "active_events": summary_row["active_events"],
        "total_event_bins": totals_row["total_event_bins"],
    }

    return render_template(
        "events.html",
        event_summary=event_summary,
        event_tallies=tallies,
        events=events_list,
    )


@app.route("/events/add", methods=["GET", "POST"])
def add_event():
    if request.method == "POST":
        name = request.form.get("event_name")
        start_date = request.form.get("start_date") or None
        end_date = request.form.get("end_date") or None
        notes = request.form.get("notes") or ""
        is_active = request.form.get("is_active", "1") == "1"

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO events (event_name, start_date, end_date, notes, is_active)
                    VALUES (:event_name, :start_date, :end_date, :notes, :is_active)
                    """
                ),
                {
                    "event_name": name,
                    "start_date": start_date,
                    "end_date": end_date,
                    "notes": notes,
                    "is_active": is_active,
                },
            )

        return redirect(url_for("events"))

    return render_template("add_event.html")


@app.route("/reports")
def reports():
    with get_connection() as conn:
        report_summary = conn.execute(
            text(
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
        ).mappings().first()

        total_transactions = conn.execute(
            text(
                """
                SELECT COUNT(*) AS total_transactions
                FROM inventory_transactions
                """
            )
        ).mappings().first()

        report_summary = dict(report_summary)
        report_summary["total_transactions"] = total_transactions["total_transactions"]

        report_type = request.args.get("report_type")
        report_title = "Reports"
        report_columns = []
        report_results = []

        if report_type:
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
        report_summary = conn.execute(
            text(
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
        ).mappings().first()

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
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf",
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)