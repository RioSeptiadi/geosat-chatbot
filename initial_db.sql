CREATE DATABASE IF NOT EXISTS geosat_db;
USE geosat_db;

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    whatsapp_number VARCHAR(15) UNIQUE NOT NULL,
    name VARCHAR(100)
);

CREATE TABLE ships (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    name VARCHAR(100) NOT NULL,
    prefix VARCHAR(10),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE ship_positions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ship_id INT,
    latitude DECIMAL(10, 5),
    longitude DECIMAL(10, 5),
    speed_knots DECIMAL(5, 2),
    heading_degrees INT,
    reported_at DATETIME,
    FOREIGN KEY (ship_id) REFERENCES ships(id)
);

CREATE TABLE ship_sensors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ship_id INT,
    rpm_engine1 INT, fuel_liters DECIMAL(6,2), fuel_capacity DECIMAL(6,2),
    temp_engine DECIMAL(5,2), voltage DECIMAL(5,2),
    reported_at DATETIME,
    FOREIGN KEY (ship_id) REFERENCES ships(id)
);

CREATE TABLE chat_contexts (
    user_id INT PRIMARY KEY,
    last_ship_id INT,
    pending_intent VARCHAR(50),
    updated_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Data Dummy
INSERT INTO users (whatsapp_number, name) VALUES ('628123456789', 'Budi Pemilik Kapal');
INSERT INTO ships (user_id, name, prefix) VALUES (1, 'Bahari Jaya', 'KM'), (1, 'Samudra Indah', 'KM');

INSERT INTO ship_positions (ship_id, latitude, longitude, speed_knots, heading_degrees, reported_at) 
VALUES 
(1, -6.10234, 106.81234, 7.50, 85, NOW() - INTERVAL 10 MINUTE),
(2, -5.98120, 106.90455, 0.20, 12, NOW() - INTERVAL 5 MINUTE);

INSERT INTO ship_sensors (ship_id, rpm_engine1, fuel_liters, fuel_capacity, temp_engine, voltage, reported_at) 
VALUES (1, 1250, 820.00, 1500.00, 41.00, 12.60, NOW() - INTERVAL 10 MINUTE);