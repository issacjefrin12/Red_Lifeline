-- Blood Bank Management System - Database Schema
-- MySQL Database

-- Create Database
CREATE DATABASE IF NOT EXISTS blood_bank_db;
USE blood_bank_db;

-- 1. Donors Table
CREATE TABLE IF NOT EXISTS Donors (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    age INT NOT NULL CHECK (age > 18),
    gender ENUM('Male', 'Female', 'Other') NOT NULL,
    blood_group ENUM('O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-') NOT NULL,
    phone VARCHAR(15) UNIQUE NOT NULL,
    last_donation_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM('Active', 'Inactive') DEFAULT 'Active'
);

-- 2. Blood_Inventory Table
CREATE TABLE IF NOT EXISTS Blood_Inventory (
    blood_group ENUM('O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-') PRIMARY KEY,
    quantity_units INT DEFAULT 0 CHECK (quantity_units >= 0),
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 3. Hospitals Table
CREATE TABLE IF NOT EXISTS Hospitals (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL,
    contact VARCHAR(15) NOT NULL,
    address VARCHAR(255) NOT NULL,
    email VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Blood_Requests Table
CREATE TABLE IF NOT EXISTS Blood_Requests (
    id INT PRIMARY KEY AUTO_INCREMENT,
    hospital_id INT NOT NULL,
    blood_group ENUM('O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-') NOT NULL,
    units_required INT NOT NULL CHECK (units_required > 0),
    status ENUM('Pending', 'Approved', 'Rejected') DEFAULT 'Pending',
    request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approval_date DATETIME,
    FOREIGN KEY (hospital_id) REFERENCES Hospitals(id) ON DELETE CASCADE,
    FOREIGN KEY (blood_group) REFERENCES Blood_Inventory(blood_group)
);

-- 5. Donations Table
CREATE TABLE IF NOT EXISTS Donations (
    id INT PRIMARY KEY AUTO_INCREMENT,
    donor_id INT NOT NULL,
    units INT NOT NULL CHECK (units > 0),
    donation_date DATE NOT NULL,
    blood_group ENUM('O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-') NOT NULL,
    health_status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (donor_id) REFERENCES Donors(id) ON DELETE CASCADE,
    FOREIGN KEY (blood_group) REFERENCES Blood_Inventory(blood_group)
);

-- 6. Blood Batches Table (batch-based inventory)
CREATE TABLE IF NOT EXISTS blood_batches (
    id INT AUTO_INCREMENT PRIMARY KEY,
    blood_group VARCHAR(10) NOT NULL,
    units_total INT NOT NULL,
    units_remaining INT NOT NULL,
    donation_date DATE NOT NULL,
    expiry_date DATE NOT NULL,
    donor_id INT NOT NULL,
    status VARCHAR(20) DEFAULT 'Active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (donor_id) REFERENCES Donors(id) ON DELETE CASCADE
);

-- Initialize Blood_Inventory with all blood groups
INSERT INTO Blood_Inventory (blood_group, quantity_units) VALUES
('O+', 0),
('O-', 0),
('A+', 0),
('A-', 0),
('B+', 0),
('B-', 0),
('AB+', 0),
('AB-', 0);

-- TRIGGERS

-- Inventory and request status updates are handled in application code (app.py).
-- Drop legacy triggers to avoid double inventory updates when this schema is re-run.
DROP TRIGGER IF EXISTS update_donor_last_donation;
DROP TRIGGER IF EXISTS increase_inventory_on_donation;
DROP TRIGGER IF EXISTS decrease_inventory_on_approval;

-- STORED PROCEDURES

-- Procedure 1: Handle Blood Requests (Check inventory and approve/reject)
DELIMITER //
CREATE PROCEDURE handle_blood_request(
    IN p_request_id INT
)
BEGIN
    DECLARE p_blood_group VARCHAR(5);
    DECLARE p_units_required INT;
    DECLARE p_available_units INT;
    
    SELECT blood_group, units_required INTO p_blood_group, p_units_required
    FROM Blood_Requests WHERE id = p_request_id;
    
    SELECT quantity_units INTO p_available_units 
    FROM Blood_Inventory WHERE blood_group = p_blood_group;
    
    IF p_available_units >= p_units_required THEN
        UPDATE Blood_Requests SET status = 'Approved' WHERE id = p_request_id;
    ELSE
        UPDATE Blood_Requests SET status = 'Rejected' WHERE id = p_request_id;
    END IF;
END //
DELIMITER ;

-- Procedure 2: Get inventory summary for all blood groups
DELIMITER //
CREATE PROCEDURE get_inventory_summary()
BEGIN
    SELECT blood_group, quantity_units FROM Blood_Inventory ORDER BY blood_group;
END //
DELIMITER ;

-- Procedure 3: Get donor donation history
DELIMITER //
CREATE PROCEDURE get_donor_history(IN p_donor_id INT)
BEGIN
    SELECT d.id, d.donation_date, d.units, d.blood_group, d.health_status
    FROM Donations d
    WHERE d.donor_id = p_donor_id
    ORDER BY d.donation_date DESC;
END //
DELIMITER ;

-- INDEXES for better query performance
CREATE INDEX idx_donor_phone ON Donors(phone);
CREATE INDEX idx_donor_blood_group ON Donors(blood_group);
CREATE INDEX idx_donation_donor ON Donations(donor_id);
CREATE INDEX idx_donation_date ON Donations(donation_date);
CREATE INDEX idx_request_hospital ON Blood_Requests(hospital_id);
CREATE INDEX idx_request_status ON Blood_Requests(status);
CREATE INDEX idx_request_date ON Blood_Requests(request_date);
