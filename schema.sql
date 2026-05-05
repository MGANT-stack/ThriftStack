DROP TABLE IF EXISTS inventory_transactions;
DROP TABLE IF EXISTS inventory_lots;
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS locations;
DROP TABLE IF EXISTS storage_purposes;
DROP TABLE IF EXISTS categories;

CREATE TABLE categories (
    category_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category_name TEXT NOT NULL UNIQUE,
    department TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE storage_purposes (
    storage_purpose_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    purpose_name TEXT NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE locations (
    location_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    location_name TEXT NOT NULL UNIQUE,
    location_type TEXT,
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE events (
    event_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_name TEXT NOT NULL UNIQUE,
    start_date DATE,
    end_date DATE,
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE inventory_lots (
    inventory_lot_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bin_number TEXT NOT NULL UNIQUE,
    category_id INTEGER NOT NULL,
    storage_purpose_id INTEGER NOT NULL,
    current_location_id INTEGER NOT NULL,
    warehouse_quadrant TEXT,
    event_id INTEGER,
    quantity_on_hand INTEGER NOT NULL DEFAULT 1 CHECK (quantity_on_hand >= 0),
    status TEXT NOT NULL DEFAULT 'active',
    date_added TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(category_id),
    FOREIGN KEY (storage_purpose_id) REFERENCES storage_purposes(storage_purpose_id),
    FOREIGN KEY (current_location_id) REFERENCES locations(location_id),
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    CHECK (warehouse_quadrant IN ('A', 'B', 'C', 'D', 'E', 'F') OR warehouse_quadrant IS NULL)
);

CREATE TABLE inventory_transactions (
    transaction_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    inventory_lot_id INTEGER NOT NULL,
    transaction_type TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    from_location_id INTEGER,
    to_location_id INTEGER,
    event_id INTEGER,
    reason_note TEXT,
    transaction_datetime TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (inventory_lot_id) REFERENCES inventory_lots(inventory_lot_id),
    FOREIGN KEY (from_location_id) REFERENCES locations(location_id),
    FOREIGN KEY (to_location_id) REFERENCES locations(location_id),
    FOREIGN KEY (event_id) REFERENCES events(event_id)
);

CREATE INDEX idx_inventory_lots_bin_number
    ON inventory_lots(bin_number);

CREATE INDEX idx_inventory_lots_status
    ON inventory_lots(status);

CREATE INDEX idx_inventory_lots_quadrant
    ON inventory_lots(warehouse_quadrant);

CREATE INDEX idx_inventory_transactions_lot
    ON inventory_transactions(inventory_lot_id);