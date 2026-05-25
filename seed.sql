-- STORAGE PURPOSES
INSERT INTO storage_purposes (purpose_name) VALUES
('Event'),
('Carryover');


-- LOCATIONS
INSERT INTO locations (location_name, location_type, notes) VALUES
('Warehouse', 'Storage', ''),
('Backroom', 'Storage', ''),
('STS', 'Staging', ''),
('LTS', 'Storage', '');


-- CATEGORIES
INSERT INTO categories (category_name, department) VALUES
('Closet Staples', 'Clothing'),
('Boutique', 'Clothing'),
('Boutique Accessories', 'Accessories'),
('Home and Office', 'Home'),
('Puzzles and Games', 'Media'),
('Fresh Fits', 'Clothing'),
('Winter', 'Seasonal'),
('Spring/Summer', 'Seasonal');

-- EVENTS
INSERT INTO events (event_name, is_active) VALUES
('Winter', TRUE),
('Fall', TRUE),
('Christmas', TRUE);

INSERT INTO inventory_lots (
    bin_number,
    category_id,
    storage_purpose_id,
    current_location_id,
    warehouse_zone,
    event_id,
    quantity_on_hand,
    status,
    date_added
)
VALUES
(
    '000001',
    (SELECT category_id FROM categories WHERE category_name = 'Fresh Fits'),
    (SELECT storage_purpose_id FROM storage_purposes WHERE purpose_name = 'Carryover'),
    (SELECT location_id FROM locations WHERE location_name = 'Warehouse'),
    'A',
    (SELECT event_id FROM events WHERE event_name = 'Winter'),
    1,
    'active',
    '2026-04-16 22:59:11'
),
(
    '000002',
    (SELECT category_id FROM categories WHERE category_name = 'Fresh Fits'),
    (SELECT storage_purpose_id FROM storage_purposes WHERE purpose_name = 'Carryover'),
    (SELECT location_id FROM locations WHERE location_name = 'Warehouse'),
    'A',
    (SELECT event_id FROM events WHERE event_name = 'Winter'),
    1,
    'active',
    '2026-04-16 22:59:27'
),
(
    '000003',
    (SELECT category_id FROM categories WHERE category_name = 'Closet Staples'),
    (SELECT storage_purpose_id FROM storage_purposes WHERE purpose_name = 'Carryover'),
    (SELECT location_id FROM locations WHERE location_name = 'Warehouse'),
    'A',
    (SELECT event_id FROM events WHERE event_name = 'Winter'),
    1,
    'active',
    '2026-04-17 13:12:09'
),
(
    '000004',
    (SELECT category_id FROM categories WHERE category_name = 'Home and Office'),
    (SELECT storage_purpose_id FROM storage_purposes WHERE purpose_name = 'Event'),
    (SELECT location_id FROM locations WHERE location_name = 'Warehouse'),
    'A',
    (SELECT event_id FROM events WHERE event_name = 'Fall'),
    1,
    'active',
    '2026-04-17 14:13:14'
),
(
    '000005',
    (SELECT category_id FROM categories WHERE category_name = 'Home and Office'),
    (SELECT storage_purpose_id FROM storage_purposes WHERE purpose_name = 'Event'),
    (SELECT location_id FROM locations WHERE location_name = 'Warehouse'),
    'A',
    (SELECT event_id FROM events WHERE event_name = 'Christmas'),
    1,
    'active',
    '2026-04-17 14:57:33'
),
(
    '000006',
    (SELECT category_id FROM categories WHERE category_name = 'Closet Staples'),
    (SELECT storage_purpose_id FROM storage_purposes WHERE purpose_name = 'Carryover'),
    (SELECT location_id FROM locations WHERE location_name = 'Warehouse'),
    'A',
    (SELECT event_id FROM events WHERE event_name = 'Winter'),
    1,
    'active',
    '2026-04-20 13:01:12'
),
(
    '000007',
    (SELECT category_id FROM categories WHERE category_name = 'Boutique'),
    (SELECT storage_purpose_id FROM storage_purposes WHERE purpose_name = 'Carryover'),
    (SELECT location_id FROM locations WHERE location_name = 'Warehouse'),
    'A',
    (SELECT event_id FROM events WHERE event_name = 'Winter'),
    1,
    'active',
    '2026-04-21 16:51:46'
),
(
    '000008',
    (SELECT category_id FROM categories WHERE category_name = 'Boutique'),
    (SELECT storage_purpose_id FROM storage_purposes WHERE purpose_name = 'Carryover'),
    (SELECT location_id FROM locations WHERE location_name = 'Warehouse'),
    'A',
    (SELECT event_id FROM events WHERE event_name = 'Winter'),
    1,
    'active',
    '2026-04-21 16:52:11'
),
(
    '000009',
    (SELECT category_id FROM categories WHERE category_name = 'Boutique'),
    (SELECT storage_purpose_id FROM storage_purposes WHERE purpose_name = 'Carryover'),
    (SELECT location_id FROM locations WHERE location_name = 'Warehouse'),
    'A',
    (SELECT event_id FROM events WHERE event_name = 'Winter'),
    1,
    'active',
    '2026-04-21 16:52:37'
),
(
    '000010',
    (SELECT category_id FROM categories WHERE category_name = 'Boutique'),
    (SELECT storage_purpose_id FROM storage_purposes WHERE purpose_name = 'Carryover'),
    (SELECT location_id FROM locations WHERE location_name = 'Warehouse'),
    'A',
    (SELECT event_id FROM events WHERE event_name = 'Winter'),
    1,
    'active',
    '2026-04-21 16:53:11'
),
(
    '000011',
    (SELECT category_id FROM categories WHERE category_name = 'Boutique'),
    (SELECT storage_purpose_id FROM storage_purposes WHERE purpose_name = 'Carryover'),
    (SELECT location_id FROM locations WHERE location_name = 'Warehouse'),
    'A',
    (SELECT event_id FROM events WHERE event_name = 'Winter'),
    1,
    'active',
    '2026-04-21 16:53:40'
),
(
    '000012',
    (SELECT category_id FROM categories WHERE category_name = 'Boutique'),
    (SELECT storage_purpose_id FROM storage_purposes WHERE purpose_name = 'Carryover'),
    (SELECT location_id FROM locations WHERE location_name = 'Warehouse'),
    'A',
    (SELECT event_id FROM events WHERE event_name = 'Winter'),
    1,
    'active',
    '2026-04-21 16:54:11'
),
(
    '000013',
    (SELECT category_id FROM categories WHERE category_name = 'Boutique'),
    (SELECT storage_purpose_id FROM storage_purposes WHERE purpose_name = 'Carryover'),
    (SELECT location_id FROM locations WHERE location_name = 'Warehouse'),
    'A',
    (SELECT event_id FROM events WHERE event_name = 'Winter'),
    1,
    'active',
    '2026-04-21 16:58:33'
),
(
    '000014',
    (SELECT category_id FROM categories WHERE category_name = 'Boutique'),
    (SELECT storage_purpose_id FROM storage_purposes WHERE purpose_name = 'Carryover'),
    (SELECT location_id FROM locations WHERE location_name = 'Warehouse'),
    'A',
    (SELECT event_id FROM events WHERE event_name = 'Winter'),
    1,
    'active',
    '2026-04-21 16:59:08'
),
(
    '000015',
    (SELECT category_id FROM categories WHERE category_name = 'Boutique Accessories'),
    (SELECT storage_purpose_id FROM storage_purposes WHERE purpose_name = 'Carryover'),
    (SELECT location_id FROM locations WHERE location_name = 'Warehouse'),
    'A',
    (SELECT event_id FROM events WHERE event_name = 'Winter'),
    1,
    'active',
    '2026-04-22 14:15:56'
),
(
    '000016',
    (SELECT category_id FROM categories WHERE category_name = 'Closet Staples'),
    (SELECT storage_purpose_id FROM storage_purposes WHERE purpose_name = 'Carryover'),
    (SELECT location_id FROM locations WHERE location_name = 'Warehouse'),
    'A',
    (SELECT event_id FROM events WHERE event_name = 'Winter'),
    1,
    'active',
    '2026-04-22 14:58:41'
),
(
    '000017',
    (SELECT category_id FROM categories WHERE category_name = 'Closet Staples'),
    (SELECT storage_purpose_id FROM storage_purposes WHERE purpose_name = 'Carryover'),
    (SELECT location_id FROM locations WHERE location_name = 'Warehouse'),
    'A',
    (SELECT event_id FROM events WHERE event_name = 'Winter'),
    1,
    'active',
    '2026-04-22 15:23:00'
);

