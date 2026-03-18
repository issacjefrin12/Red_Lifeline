-- ========================================
-- BLOOD BANK MANAGEMENT SYSTEM - RBAC SCHEMA
-- Role-Based Access Control Implementation
-- ========================================

USE blood_bank_db;

-- ==================== ROLE MANAGEMENT ====================

-- 1. Roles Table - Define system roles
CREATE TABLE IF NOT EXISTS Roles (
    id INT PRIMARY KEY AUTO_INCREMENT,
    role_name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    INDEX idx_role_name (role_name)
);

-- 2. Permissions Table - Define granular permissions
CREATE TABLE IF NOT EXISTS Permissions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    permission_name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    resource VARCHAR(50) NOT NULL,        -- e.g., 'donors', 'requests', 'inventory'
    action VARCHAR(50) NOT NULL,           -- e.g., 'create', 'read', 'update', 'approve'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_permission_name (permission_name),
    INDEX idx_resource_action (resource, action)
);

-- 3. Role_Permissions Junction Table - Many-to-many relationship
CREATE TABLE IF NOT EXISTS Role_Permissions (
    role_id INT NOT NULL,
    permission_id INT NOT NULL,
    PRIMARY KEY (role_id, permission_id),
    FOREIGN KEY (role_id) REFERENCES Roles(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES Permissions(id) ON DELETE CASCADE
);

-- ==================== USER MANAGEMENT ====================

-- 4. Enhanced Users Table - Now linked to roles
CREATE TABLE IF NOT EXISTS Users_RBAC (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role_id INT NOT NULL,
    hospital_id INT,                       -- For Hospital Users (links to hospital)
    is_active BOOLEAN DEFAULT TRUE,
    is_locked BOOLEAN DEFAULT FALSE,
    failed_login_attempts INT DEFAULT 0,
    last_login DATETIME,
    password_changed_at DATETIME,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (role_id) REFERENCES Roles(id),
    FOREIGN KEY (hospital_id) REFERENCES Hospitals(id) ON DELETE SET NULL,
    INDEX idx_username (username),
    INDEX idx_email (email),
    INDEX idx_role_id (role_id),
    INDEX idx_hospital_id (hospital_id),
    INDEX idx_is_active (is_active)
);

-- ==================== AUDIT & SECURITY ====================

-- 5. Audit Log Table - Track all critical actions
CREATE TABLE IF NOT EXISTS Audit_Logs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,   -- e.g., 'BloodRequest', 'Donation', 'User'
    resource_id INT,
    old_value JSON,
    new_value JSON,
    ip_address VARCHAR(45),
    user_agent VARCHAR(255),
    status ENUM('Success', 'Denied', 'Failed') DEFAULT 'Success',
    reason_if_denied TEXT,                 -- Why permission was denied
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users_RBAC(id) ON DELETE SET NULL,
    INDEX idx_user_id (user_id),
    INDEX idx_action (action),
    INDEX idx_resource_type (resource_type),
    INDEX idx_created_at (created_at),
    INDEX idx_status (status)
);

-- 6. Enhanced Blood_Requests Table - Add created_by and approved_by
ALTER TABLE Blood_Requests ADD COLUMN IF NOT EXISTS created_by INT;
ALTER TABLE Blood_Requests ADD COLUMN IF NOT EXISTS approved_by INT;
ALTER TABLE Blood_Requests ADD COLUMN IF NOT EXISTS rejection_reason TEXT;
ALTER TABLE Blood_Requests ADD FOREIGN KEY (created_by) REFERENCES Users_RBAC(id) ON DELETE SET NULL;
ALTER TABLE Blood_Requests ADD FOREIGN KEY (approved_by) REFERENCES Users_RBAC(id) ON DELETE SET NULL;
ALTER TABLE Blood_Requests ADD INDEX idx_created_by (created_by);
ALTER TABLE Blood_Requests ADD INDEX idx_approved_by (approved_by);

-- ==================== SEED DATA ====================

-- Insert Roles with descriptions
INSERT INTO Roles (role_name, description, is_active) VALUES
('SUPER_ADMIN', 'Full system override. Manages users, approves hospitals, views full audit logs.', TRUE),
('BLOOD_BANK_ADMIN', 'Daily operator. Manages inventory, adds donors/donations, approves/rejects requests.', TRUE),
('HOSPITAL_USER', 'Can create blood requests and view inventory (read-only). Cannot approve own requests.', TRUE),
('STAFF_MEMBER', 'Data entry role. Can record donations and donors. No approval authority.', TRUE),
('DONOR', 'Individual profile to view donation history and toggle availability.', TRUE);

-- Insert Permissions (granular permission matrix)
-- DONORS
INSERT INTO Permissions (permission_name, description, resource, action) VALUES
('donor:create', 'Create new donor record', 'donors', 'create'),
('donor:read', 'View donor records', 'donors', 'read'),
('donor:read_self', 'View own donor profile', 'donors', 'read_self'),
('donor:update', 'Update donor information', 'donors', 'update'),
('donor:delete', 'Delete donor record', 'donors', 'delete');

-- DONATIONS
INSERT INTO Permissions (permission_name, description, resource, action) VALUES
('donation:create', 'Record new donation', 'donations', 'create'),
('donation:read', 'View donation records', 'donations', 'read'),
('donation:read_self', 'View own donation history', 'donations', 'read_self'),
('donation:update', 'Update donation record', 'donations', 'update'),
('donation:delete', 'Delete donation record', 'donations', 'delete');

-- BLOOD REQUESTS
INSERT INTO Permissions (permission_name, description, resource, action) VALUES
('request:create', 'Create blood request', 'requests', 'create'),
('request:read', 'View blood requests', 'requests', 'read'),
('request:read_self', 'View own blood requests', 'requests', 'read_self'),
('request:approve', 'Approve blood request', 'requests', 'approve'),
('request:reject', 'Reject blood request', 'requests', 'reject'),
('request:update_status', 'Update request status (ADMIN ONLY)', 'requests', 'update_status');

-- INVENTORY
INSERT INTO Permissions (permission_name, description, resource, action) VALUES
('inventory:read', 'View blood inventory', 'inventory', 'read'),
('inventory:update', 'Update blood inventory', 'inventory', 'update'),
('inventory:manage', 'Full inventory management', 'inventory', 'manage');

-- HOSPITALS
INSERT INTO Permissions (permission_name, description, resource, action) VALUES
('hospital:create', 'Register new hospital', 'hospitals', 'create'),
('hospital:read', 'View hospital records', 'hospitals', 'read'),
('hospital:update', 'Update hospital information', 'hospitals', 'update'),
('hospital:approve', 'Approve hospital registration', 'hospitals', 'approve'),
('hospital:delete', 'Delete hospital record', 'hospitals', 'delete');

-- AUDIT & USER MANAGEMENT
INSERT INTO Permissions (permission_name, description, resource, action) VALUES
('audit:read', 'View audit logs', 'audit', 'read'),
('audit:read_self', 'View own activity logs', 'audit', 'read_self'),
('admin:manage', 'Full admin access to manage users and roles', 'admin', 'manage'),
('users:create', 'Create new user account', 'users', 'create'),
('users:read', 'View user information', 'users', 'read'),
('users:update', 'Update user information', 'users', 'update'),
('users:delete', 'Delete user account', 'users', 'delete'),
('users:assign_role', 'Assign roles to users', 'users', 'assign_role'),
('system:config', 'System configuration access', 'system', 'config');

-- ==================== ASSIGN PERMISSIONS TO ROLES ====================

-- SUPER_ADMIN: Full permissions
INSERT INTO Role_Permissions (role_id, permission_id)
SELECT r.id, p.id FROM Roles r, Permissions p 
WHERE r.role_name = 'SUPER_ADMIN';

-- BLOOD_BANK_ADMIN: Manage inventory, donations, approve requests (NOT hospitals)
INSERT INTO Role_Permissions (role_id, permission_id)
SELECT r.id, p.id FROM Roles r, Permissions p 
WHERE r.role_name = 'BLOOD_BANK_ADMIN' AND p.permission_name IN (
    'donor:create', 'donor:read', 'donor:update',
    'donation:create', 'donation:read', 'donation:update',
    'request:read', 'request:approve', 'request:reject',
    'request:update_status',
    'inventory:read', 'inventory:manage',
    'hospital:read',
    'audit:read'
);

-- HOSPITAL_USER: Create requests, view inventory (read-only)
INSERT INTO Role_Permissions (role_id, permission_id)
SELECT r.id, p.id FROM Roles r, Permissions p 
WHERE r.role_name = 'HOSPITAL_USER' AND p.permission_name IN (
    'request:create', 'request:read_self',
    'inventory:read',
    'hospital:read',
    'audit:read_self'
);

-- STAFF_MEMBER: Data entry only (donors and donations)
INSERT INTO Role_Permissions (role_id, permission_id)
SELECT r.id, p.id FROM Roles r, Permissions p 
WHERE r.role_name = 'STAFF_MEMBER' AND p.permission_name IN (
    'donor:create', 'donor:read', 'donor:update',
    'donation:create', 'donation:read',
    'inventory:read',
    'audit:read_self'
);

-- DONOR: View own profile only
INSERT INTO Role_Permissions (role_id, permission_id)
SELECT r.id, p.id FROM Roles r, Permissions p 
WHERE r.role_name = 'DONOR' AND p.permission_name IN (
    'donor:read_self',
    'donation:read_self',
    'inventory:read',
    'audit:read_self'
);

COMMIT;

-- ==================== VERIFICATION QUERIES ====================
-- Run these to verify RBAC setup:

-- View role-permission matrix
-- SELECT r.role_name, GROUP_CONCAT(p.permission_name) as permissions
-- FROM Roles r
-- LEFT JOIN Role_Permissions rp ON r.id = rp.role_id
-- LEFT JOIN Permissions p ON rp.permission_id = p.id
-- GROUP BY r.id, r.role_name;

-- View users and their roles
-- SELECT u.username, u.email, r.role_name, u.is_active
-- FROM Users_RBAC u
-- JOIN Roles r ON u.role_id = r.id;
