-- =========================================================
-- Admin Migration Script - SQL Version
-- Migrate existing admin to new Users_RBAC table
-- =========================================================

-- BEFORE RUNNING THIS SCRIPT:
-- 1. Update the password hash below (see instructions below)
-- 2. Ensure Users_RBAC table exists
-- 3. Ensure Roles table has id=1 for SUPER_ADMIN

-- =========================================================
-- STEP 1: Generate Password Hash
-- =========================================================
-- Your current password: admin123
-- Run this Python code to generate the hash:
/*
python3
from werkzeug.security import generate_password_hash
hash_val = generate_password_hash('admin123', method='pbkdf2:sha256')
print(hash_val)
*/

-- Copy the hash value and replace 'PASTE_YOUR_HASH_HERE' below
-- Example hash: pbkdf2:sha256:260000$xxxxx...

-- =========================================================
-- STEP 2: Insert or Update Admin User
-- =========================================================

-- Check if admin already exists
SELECT COUNT(*) as admin_count FROM Users_RBAC WHERE username = 'admin';

-- If admin_count = 0, run INSERT (uncomment below):
/*
INSERT INTO Users_RBAC (
    username,
    email,
    password_hash,
    role_id,
    is_active,
    created_at,
    created_by
) VALUES (
    'admin',
    'admin@blood.local',
    'PASTE_YOUR_HASH_HERE',  -- <-- REPLACE WITH ACTUAL HASH
    1,                        -- SUPER_ADMIN role
    TRUE,
    NOW(),
    1
);
*/

-- If admin already exists, run UPDATE (uncomment below):
/*
UPDATE Users_RBAC
SET
    email = 'admin@blood.local',
    password_hash = 'PASTE_YOUR_HASH_HERE',  -- <-- REPLACE WITH ACTUAL HASH
    role_id = 1,              -- SUPER_ADMIN role
    is_active = TRUE
WHERE username = 'admin';
*/

-- =========================================================
-- STEP 3: Verify Migration
-- =========================================================
-- Run this to verify the migration was successful:
SELECT id, username, email, role_id, is_active, created_at 
FROM Users_RBAC 
WHERE username = 'admin';

-- Expected output:
-- id | username | email                | role_id | is_active | created_at
-- 1  | admin    | admin@blood.local    | 1       | 1         | 2026-02-18 ...

-- =========================================================
-- ADDITIONAL: Grant Admin Permissions
-- =========================================================
-- Ensure admin has 'admin:manage' permission
-- First, check if permission exists:
SELECT id FROM Permissions WHERE permission_name = 'admin:manage';

-- If it doesn't exist, create it:
/*
INSERT INTO Permissions (permission_name, description, resource, action)
VALUES ('admin:manage', 'Full admin access to manage users and roles', 'admin', 'manage');
*/

-- Then assign permission to SUPER_ADMIN role:
-- (This assumes role_id=1 is SUPER_ADMIN and permission_id is correct)
/*
INSERT INTO Role_Permissions (role_id, permission_id)
VALUES (1, (SELECT id FROM Permissions WHERE permission_name = 'admin:manage'))
ON DUPLICATE KEY UPDATE role_id = role_id;
*/

-- Verify permissions:
SELECT rp.role_id, p.permission_name 
FROM Role_Permissions rp
JOIN Permissions p ON rp.permission_id = p.id
WHERE rp.role_id = 1;

-- Expected: admin:manage permission for role_id 1

-- =========================================================
-- DONE!
-- =========================================================
-- Your admin account has been migrated to the new system
-- Login with:
--   Email: admin@blood.local (or username: admin)
--   Password: admin123
-- Role: SUPER_ADMIN
