-- ============================================================
-- GEOSAT - Sistem Reporting Satelit Kapal via WhatsApp
-- Skema database (SRS 6.2) + data dummy
-- ============================================================

CREATE DATABASE IF NOT EXISTS mygeosat
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE mygeosat;

-- ------------------------------------------------------------
-- Tabel users: nomor WhatsApp yang terdaftar
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Tabel ships: kapal milik user (1 user bisa punya banyak kapal)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ships (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    ship_name VARCHAR(100) NOT NULL,
    call_sign VARCHAR(20) DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ships_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_ships_user (user_id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Tabel ship_positions: posisi terakhir tiap kapal
-- (1 baris terbaru per kapal; riwayat disimpan)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ship_positions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ship_id INT NOT NULL,
    latitude DECIMAL(10,7) NOT NULL,
    longitude DECIMAL(10,7) NOT NULL,
    speed_knots DECIMAL(5,2) NOT NULL DEFAULT 0,
    heading INT NOT NULL DEFAULT 0,
    reported_at DATETIME NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_positions_ship FOREIGN KEY (ship_id) REFERENCES ships(id) ON DELETE CASCADE,
    INDEX idx_positions_ship_time (ship_id, reported_at DESC)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Tabel ship_sensors: data sensor mesin/perangkat kapal
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ship_sensors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ship_id INT NOT NULL,
    rpm_engine_1 INT NOT NULL DEFAULT 0,
    rpm_engine_2 INT NOT NULL DEFAULT 0,
    fuel_level_l INT NOT NULL DEFAULT 0,
    fuel_capacity_l INT NOT NULL DEFAULT 0,
    engine_temp_c DECIMAL(5,2) NOT NULL DEFAULT 0,
    device_temp_c DECIMAL(5,2) NOT NULL DEFAULT 0,
    voltage_v DECIMAL(5,2) NOT NULL DEFAULT 0,
    current_a DECIMAL(5,2) NOT NULL DEFAULT 0,
    recorded_at DATETIME NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_sensors_ship FOREIGN KEY (ship_id) REFERENCES ships(id) ON DELETE CASCADE,
    INDEX idx_sensors_ship_time (ship_id, recorded_at DESC)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Tabel chat_contexts: konteks percakapan (TTL 15 menit, SRS 6.2)
-- Menyimpan pending intent saat user harus memilih kapal.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_contexts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL UNIQUE,
    pending_intent VARCHAR(50) DEFAULT NULL,
    pending_payload TEXT DEFAULT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_context_phone (phone_number)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Tabel request_logs: log permintaan dengan nomor tersamarkan
-- (SRS-FR-24)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS request_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    phone_masked VARCHAR(30) NOT NULL,
    message_in TEXT NOT NULL,
    intent VARCHAR(50) DEFAULT NULL,
    ship_name VARCHAR(100) DEFAULT NULL,
    message_out TEXT DEFAULT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'success',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_logs_created (created_at)
) ENGINE=InnoDB;

-- ============================================================
-- DATA DUMMY: 1 user dengan 3 kapal
-- ============================================================

INSERT INTO users (phone_number, name) VALUES
    ('6281234567890', 'Kapten Andi');

INSERT INTO ships (user_id, ship_name, call_sign) VALUES
    (1, 'KM Bahari Jaya', 'YB1234'),
    (1, 'KM Samudra Makmur', 'YB5678'),
    (1, 'KM Nusantara', 'YB9012');

-- Posisi (koordinat pakai titik desimal; waktu dalam WIB)
INSERT INTO ship_positions (ship_id, latitude, longitude, speed_knots, heading, reported_at) VALUES
    (1, -6.1234567, 106.7890123, 12.50, 270, '2026-11-10 14:05:00'),
    (2, -7.2567890, 112.7456789, 8.30,  90, '2026-11-10 13:48:00'),
    (3, -5.1456789, 119.4123456, 0.00,   0, '2026-11-10 12:30:00');

-- Sensor
INSERT INTO ship_sensors (ship_id, rpm_engine_1, rpm_engine_2, fuel_level_l, fuel_capacity_l,
                          engine_temp_c, device_temp_c, voltage_v, current_a, recorded_at) VALUES
    (1, 1450, 1430, 3200, 5000, 78.50, 42.30, 24.10, 8.50, '2026-11-10 14:05:00'),
    (2, 1200, 0,    2100, 4000, 74.20, 40.10, 23.80, 7.20, '2026-11-10 13:48:00'),
    (3, 0,    0,    1500, 3000, 35.00, 38.50, 24.00, 2.10, '2026-11-10 12:30:00');
