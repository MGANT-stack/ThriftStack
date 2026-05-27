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
('Fresh Fits', 'Clothing'),
('Boutique', 'Clothing'),
(Boutique Accessories', 'Boutique'),
('Home/Office', 'Home'),
('Media', 'Media');