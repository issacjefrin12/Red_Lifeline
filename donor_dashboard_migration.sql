-- Donor Dashboard / Donor Management schema alignment
-- Safe to run multiple times on MySQL 8+

USE blood_bank_db;

ALTER TABLE Donors
    ADD COLUMN IF NOT EXISTS email VARCHAR(255) NULL,
    ADD COLUMN IF NOT EXISTS availability VARCHAR(20) DEFAULT 'Available',
    ADD COLUMN IF NOT EXISTS last_active_at DATETIME NULL;

ALTER TABLE Users_RBAC
    ADD COLUMN IF NOT EXISTS donor_id INT NULL;
