-- Create Blood Bank Management System Database

-- Create Database
CREATE DATABASE IF NOT EXISTS blood_bank_db;
USE blood_bank_db;

-- Users Table
CREATE TABLE Users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    email VARCHAR(100),
    full_name VARCHAR(100),
    role VARCHAR(20) DEFAULT 'staff',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Donors Table
CREATE TABLE Donors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    age INT NOT NULL CHECK(age > 18),
    gender VARCHAR(10),
    blood_group VARCHAR(5) NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
    last_donation_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'Active'
);

-- Blood Inventory Table
CREATE TABLE Blood_Inventory (
    blood_group VARCHAR(5) PRIMARY KEY,
    quantity_units INT DEFAULT 0
);

-- Hospitals Table
CREATE TABLE Hospitals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    contact VARCHAR(20) NOT NULL,
    address VARCHAR(255) NOT NULL,
    email VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Blood Requests Table
CREATE TABLE Blood_Requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    hospital_id INT NOT NULL,
    blood_group VARCHAR(5) NOT NULL,
    units_required INT NOT NULL CHECK(units_required > 0),
    status VARCHAR(20) DEFAULT 'Pending',
    request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approval_date DATETIME,
    FOREIGN KEY(hospital_id) REFERENCES Hospitals(id)
);

-- Donations Table
CREATE TABLE Donations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    donor_id INT NOT NULL,
    units INT NOT NULL CHECK(units > 0),
    donation_date DATE NOT NULL,
    blood_group VARCHAR(5) NOT NULL,
    health_status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(donor_id) REFERENCES Donors(id)
);

-- Blood Batches Table (batch-based inventory)
CREATE TABLE blood_batches (
    id INT AUTO_INCREMENT PRIMARY KEY,
    blood_group VARCHAR(10) NOT NULL,
    units_total INT NOT NULL,
    units_remaining INT NOT NULL,
    donation_date DATE NOT NULL,
    expiry_date DATE NOT NULL,
    donor_id INT NOT NULL,
    status VARCHAR(20) DEFAULT 'Active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (donor_id) REFERENCES Donors(id)
);

-- Insert Blood Groups
INSERT INTO Blood_Inventory (blood_group, quantity_units) VALUES 
('O+', 0), ('O-', 0), ('A+', 0), ('A-', 0), 
('B+', 0), ('B-', 0), ('AB+', 0), ('AB-', 0);

-- Insert Default Users
INSERT INTO Users (username, password, email, full_name, role) VALUES 
('admin', 'admin123', 'admin@redlifeline.com', 'Admin User', 'admin'),
('staff', 'staff123', 'staff@redlifeline.com', 'Staff Member', 'staff'),
('doctor', 'doctor123', 'doctor@redlifeline.com', 'Doctor', 'doctor');

-- Create indexes for better performance
CREATE INDEX idx_donor_blood_group ON Donors(blood_group);
CREATE INDEX idx_request_status ON Blood_Requests(status);
CREATE INDEX idx_donation_date ON Donations(donation_date);
