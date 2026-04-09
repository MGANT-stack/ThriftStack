from flask import Flask, render_template, request, redirect, url_for, session
from utils.db import get_connection
from datetime import timedelta

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-key-change-later"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=5)


# -----------------------------
# AUTH / SESSION
# -----------------------------

@app.before_request
def check_login():
    session.permanent = True
    if request.endpoint not in ("login", "static") and not session.get("logged_in"):
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        session["logged_in"] = True
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -----------------------------
# DASHBOARD
# -----------------------------

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


# -----------------------------
# INVENTORY HUB
# -----------------------------

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


# -----------------------------
# INVENTORY LIST
# -----------------------------

@app.route("/inventory/list")
def inventory_list():
    conn = get_connection()

    lots = conn.execute(
        """
        SELECT
            il.inventory_lot_id,
            c.category_name,
            sp.purpose_name,
            l.location_name,
            e.event_name,
            il.quantity_on_hand,
            il.status,
            il.date_added
        FROM inventory_lots il
        JOIN categories c ON il.category_id = c.category_id
        JOIN storage_purposes sp ON il.storage_purpose_id = sp.storage_purpose_id
        JOIN locations l ON il.current_location_id = l.location_id
        LEFT JOIN events e ON il.event_id = e.event_id
        ORDER BY il.inventory_lot_id DESC
        """
    ).fetchall()

    conn.close()

    return render_template("inventory_list.html", inventory_lots=lots)


# -----------------------------
# CREATE BIN
# -----------------------------

@app.route("/inventory/add", methods=["GET", "POST"])
def add_inventory():
    conn = get_connection()

    if request.method == "POST":
        category_id = request.form.get("category_id")
        storage_purpose_id = request.form.get("storage_purpose_id")
        location_id = request.form.get("current_location_id")
        event_id = request.form.get("event_id") or None
        quantity = int(request.form.get("quantity_on_hand"))
        status = request.form.get("status") or "active"

        conn.execute(
            """
            INSERT INTO inventory_lots (
                category_id,
                storage_purpose_id,
                current_location_id,
                event_id,
                quantity_on_hand,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                category_id,
                storage_purpose_id,
                location_id,
                event_id,
                quantity,
                status
            )
        )

        conn.commit()
        conn.close()

        return redirect(url_for("inventory_list"))

    categories = conn.execute("SELECT * FROM categories").fetchall()
    purposes = conn.execute("SELECT * FROM storage_purposes").fetchall()
    locations = conn.execute("SELECT * FROM locations").fetchall()
    events = conn.execute("SELECT * FROM events WHERE is_active = 1").fetchall()

    conn.close()

    return render_template(
        "add_inventory.html",
        categories=categories,
        storage_purposes=purposes,
        locations=locations,
        events=events
    )


# -----------------------------
# MOVE BIN
# -----------------------------

@app.route("/inventory/move", methods=["GET", "POST"])
def move_inventory():
    conn = get_connection()

    if request.method == "POST":
        lot_id = request.form.get("inventory_lot_id")
        to_location_id = request.form.get("to_location_id")

        lot = conn.execute(
            "SELECT current_location_id FROM inventory_lots WHERE inventory_lot_id = ?",
            (lot_id,)
        ).fetchone()

        conn.execute(
            """
            UPDATE inventory_lots
            SET current_location_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE inventory_lot_id = ?
            """,
            (to_location_id, lot_id)
        )

        conn.commit()
        conn.close()

        return redirect(url_for("inventory_list"))

    lots = conn.execute(
        """
        SELECT il.inventory_lot_id, il.quantity_on_hand, c.category_name
        FROM inventory_lots il
        JOIN categories c ON il.category_id = c.category_id
        WHERE il.status = 'active'
        """
    ).fetchall()

    locations = conn.execute("SELECT * FROM locations").fetchall()

    conn.close()

    return render_template("move_inventory.html", inventory_lots=lots, locations=locations)


# -----------------------------
# DEPLOY INVENTORY
# -----------------------------

@app.route("/inventory/deploy", methods=["GET", "POST"])
def deploy_inventory():
    conn = get_connection()

    if request.method == "POST":
        lot_id = request.form.get("inventory_lot_id")
        quantity = int(request.form.get("quantity"))

        lot = conn.execute(
            "SELECT quantity_on_hand FROM inventory_lots WHERE inventory_lot_id = ?",
            (lot_id,)
        ).fetchone()

        new_quantity = lot["quantity_on_hand"] - quantity
        new_status = "depleted" if new_quantity == 0 else "active"

        conn.execute(
            """
            UPDATE inventory_lots
            SET quantity_on_hand = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE inventory_lot_id = ?
            """,
            (new_quantity, new_status, lot_id)
        )

        conn.commit()
        conn.close()

        return redirect(url_for("inventory_list"))

    lots = conn.execute(
        "SELECT inventory_lot_id, quantity_on_hand FROM inventory_lots WHERE status = 'active'"
    ).fetchall()

    locations = conn.execute("SELECT * FROM locations").fetchall()

    conn.close()

    return render_template("deploy_inventory.html", inventory_lots=lots, locations=locations)


# -----------------------------
# ADJUST INVENTORY
# -----------------------------

@app.route("/inventory/adjust", methods=["GET", "POST"])
def adjust_inventory():
    conn = get_connection()

    if request.method == "POST":
        lot_id = request.form.get("inventory_lot_id")
        adjustment_type = request.form.get("adjustment_type")
        quantity = int(request.form.get("quantity"))

        lot = conn.execute(
            "SELECT quantity_on_hand FROM inventory_lots WHERE inventory_lot_id = ?",
            (lot_id,)
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
            (new_quantity, new_status, lot_id)
        )

        conn.commit()
        conn.close()

        return redirect(url_for("inventory_list"))

    lots = conn.execute(
        "SELECT inventory_lot_id, quantity_on_hand FROM inventory_lots WHERE status = 'active'"
    ).fetchall()

    conn.close()

    return render_template("adjust_inventory.html", inventory_lots=lots)


# -----------------------------
# EVENTS
# -----------------------------

@app.route("/events")
def events():
    conn = get_connection()
    events = conn.execute("SELECT * FROM events").fetchall()
    conn.close()
    return render_template("events.html", events=events)


@app.route("/events/add", methods=["GET", "POST"])
def add_event():
    conn = get_connection()

    if request.method == "POST":
        name = request.form.get("event_name")

        conn.execute(
            "INSERT INTO events (event_name) VALUES (?)",
            (name,)
        )

        conn.commit()
        conn.close()

        return redirect(url_for("events"))

    conn.close()
    return render_template("add_event.html")


# -----------------------------
# REPORTS
# -----------------------------

@app.route("/reports")
def reports():
    conn = get_connection()

    summary = conn.execute(
        """
        SELECT
            COUNT(*) AS total_bins,
            COALESCE(SUM(quantity_on_hand), 0) AS total_units
        FROM inventory_lots
        """
    ).fetchone()

    conn.close()

    return render_template("reports.html", report_summary=summary)


# -----------------------------

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)