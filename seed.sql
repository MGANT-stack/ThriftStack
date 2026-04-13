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

