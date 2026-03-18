-- BBMS Cleanup Migration (idempotent)
-- Apply after pulling latest code to align database behavior and permissions.

USE blood_bank_db;

-- 1) Prevent double-inventory updates by removing legacy triggers.
DROP TRIGGER IF EXISTS update_donor_last_donation;
DROP TRIGGER IF EXISTS increase_inventory_on_donation;
DROP TRIGGER IF EXISTS decrease_inventory_on_approval;

-- 2) Ensure admin:manage permission exists for routes guarded by @permission_required('admin:manage').
INSERT INTO Permissions (permission_name, description, resource, action)
SELECT 'admin:manage', 'Full admin access to manage users and roles', 'admin', 'manage'
WHERE NOT EXISTS (
    SELECT 1 FROM Permissions WHERE permission_name = 'admin:manage'
);

-- 3) Ensure SUPER_ADMIN has admin:manage permission.
INSERT INTO Role_Permissions (role_id, permission_id)
SELECT r.id, p.id
FROM Roles r
JOIN Permissions p ON p.permission_name = 'admin:manage'
WHERE r.role_name = 'SUPER_ADMIN'
  AND NOT EXISTS (
      SELECT 1
      FROM Role_Permissions rp
      WHERE rp.role_id = r.id AND rp.permission_id = p.id
  );
