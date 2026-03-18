# 🔐 RBAC Integration Guide - Blood Bank Management System

## Overview

This guide explains how to integrate the Role-Based Access Control (RBAC) system into your existing Blood Bank Management System (BBMS).

**What You've Received:**
1. `rbac_schema.sql` - Enhanced database schema with roles, permissions, and audit tables
2. `rbac.py` - RBAC middleware, decorators, and permission helpers
3. `rbac_routes.py` - Secure route handlers (drop-in replacements)
4. This integration guide

---

## Step 1: Database Migration

### 1.1 Create New RBAC Tables

Run this in your MySQL client:

```bash
mysql -u root -p blood_bank_db < rbac_schema.sql
```

Or copy-paste the contents of `rbac_schema.sql` into MySQL client.

**What Gets Created:**
- `Roles` - System roles (SUPER_ADMIN, BLOOD_BANK_ADMIN, HOSPITAL_USER, STAFF_MEMBER, DONOR)
- `Permissions` - Granular permissions (50+ permissions)
- `Role_Permissions` - Role-permission mapping
- `Users_RBAC` - Enhanced users table with role links
- `Audit_Logs` - Complete audit trail
- Sample data for all roles and permissions

**Important:** The old `Users` table remains. Gradually migrate user data to `Users_RBAC`.

### 1.2 Verify Installation

```sql
-- Check roles
SELECT * FROM Roles;

-- Check role-permission matrix
SELECT r.role_name, COUNT(p.permission_name) as permission_count
FROM Roles r
LEFT JOIN Role_Permissions rp ON r.id = rp.role_id
LEFT JOIN Permissions p ON rp.permission_id = p.id
GROUP BY r.role_name;

-- Check audit logs
SELECT COUNT(*) FROM Audit_Logs;
```

---

## Step 2: Update app.py

### 2.1 Add Imports

Add these imports at the top of your `app.py`:

```python
from rbac import (
    permission_required, role_required, log_audit_event,
    get_user_permissions, get_current_user_info,
    can_approve_blood_request, can_create_blood_request,
    verify_request_ownership, get_audit_logs,
    invalidate_permission_cache, user_has_permission
)
```

### 2.2 Update Database Configuration

Ensure `rbac.py` has correct DB credentials:

```python
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'your_password',  # CHANGE THIS
    'database': 'blood_bank_db',
    'port': 3306
}
```

### 2.3 Register RBAC Routes

Add this line after creating your Flask app:

```python
app = Flask(__name__)
# ... config setup ...

# Import and register RBAC routes
from rbac_routes import register_secure_routes
register_secure_routes(app)
```

---

## Step 3: Understand the Permission Model

### Permission Naming Convention

```
resource:action

Examples:
- donor:create        (Create a donor)
- request:approve     (Approve blood request)
- request:read_self   (View own requests)
- inventory:manage    (Manage inventory)
- audit:read           (View all audit logs)
- audit:read_self     (View own logs)
```

### Role-Permission Matrix

| Permission | SUPER_ADMIN | BLOOD_BANK_ADMIN | HOSPITAL_USER | STAFF_MEMBER | DONOR |
|---|---|---|---|---|---|
| donor:create | ✅ | ✅ | ❌ | ✅ | ❌ |
| donation:create | ✅ | ✅ | ❌ | ✅ | ❌ |
| request:create | ✅ | ✅ | ✅ | ❌ | ❌ |
| request:approve | ✅ | ✅ | ❌ | ❌ | ❌ |
| inventory:manage | ✅ | ✅ | ❌ | ❌ | ❌ |
| audit:read | ✅ | ✅ | ❌ | ❌ | ❌ |
| audit:read_self | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## Step 4: Securing Routes

### 4.1 Basic Decorator Usage

**Option A: Check by Role**
```python
@app.route('/admin-dashboard')
@role_required('SUPER_ADMIN', 'BLOOD_BANK_ADMIN')
def admin_dashboard():
    """Only admins can view this"""
    return render_template('admin.html')
```

**Option B: Check by Permission (RECOMMENDED)**
```python
@app.route('/approve-request')
@permission_required('request:approve')
def approve_request():
    """Only users with this permission can access"""
    return render_template('approve.html')
```

### 4.2 Protecting POST Endpoints

```python
@app.route('/api/donation', methods=['POST'])
@permission_required('donation:create')
def api_create_donation():
    """Record donation - Staff only"""
    user_id = session.get('user_id')
    # ... implementation ...
    log_audit_event(user_id, 'CREATE_DONATION', 'Donation', donation_id)
```

---

## Step 5: Implementing Business Logic with Security

### 5.1 Example: Request Approval

```python
# BEFORE (Insecure)
@app.route('/approve/<int:request_id>')
def approve_request(request_id):
    # Anyone can approve!
    update_status(request_id, 'Approved')

# AFTER (Secure with RBAC)
@app.route('/approve/<int:request_id>')
@permission_required('request:approve')
def approve_request(request_id):
    user_id = session.get('user_id')
    
    # Check business rules (separation of concerns)
    can_approve, reason = can_approve_blood_request(user_id, request_id)
    
    if not can_approve:
        # Audit the failed attempt
        log_audit_event(user_id, 'APPROVE_REQUEST', 'BloodRequest', request_id,
                       status='Denied', reason_if_denied=reason)
        flash(reason, 'danger')
        return redirect(url_for('view_requests'))
    
    # Update status
    update_request_status_secure(request_id, 'Approved')
    
    return redirect(url_for('view_requests'))
```

### 5.2 Example: Hospital Self-Service Requests

```python
@app.route('/request-blood', methods=['POST'])
@permission_required('request:create')
def create_request():
    """Hospital creates own request - cannot approve it"""
    user_id = session.get('user_id')
    user_info = get_current_user_info()
    
    blood_group = request.form.get('blood_group')
    units = int(request.form.get('units'))
    
    # Critical: Can only create for own hospital
    if user_info['hospital_id'] is None:
        flash('Not assigned to a hospital', 'danger')
        return redirect(url_for('index'))
    
    # Audit the action
    log_audit_event(user_id, 'CREATE_REQUEST', 'BloodRequest', None,
                   new_value={'hospital': user_info['hospital_id'], 
                             'blood_group': blood_group, 'units': units})
    
    # Save to database
    # ...
```

---

## Step 6: Creating New Users with RBAC

### 6.1 Add User Function

```python
def create_user_with_role(username, email, password, full_name, role_name, hospital_id=None):
    """
    Create user with assigned role
    
    Args:
        username: Unique username
        email: User email
        password: Plain password (HASH in production!)
        full_name: User's full name
        role_name: Role name (e.g., 'BLOOD_BANK_ADMIN')
        hospital_id: For hospital users, their assigned hospital
    """
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        # Get role ID
        cursor.execute("SELECT id FROM Roles WHERE role_name = %s", (role_name,))
        role = cursor.fetchone()
        
        if not role:
            return False, f"Role '{role_name}' not found"
        
        # Create user
        cursor.execute("""
            INSERT INTO Users_RBAC 
            (username, email, password_hash, full_name, role_id, hospital_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (username, email, password, full_name, role['id'], hospital_id))
        
        user_id = cursor.lastrowid
        conn.commit()
        
        # Audit
        log_audit_event(session.get('user_id'), 'CREATE_USER', 'User', user_id,
                       new_value={'username': username, 'role': role_name})
        
        cursor.close()
        conn.close()
        
        return True, f"User '{username}' created with role '{role_name}'"
        
    except Exception as e:
        return False, str(e)
```

### 6.2 Test Users to Create

```sql
-- Super Admin
INSERT INTO Users_RBAC (username, email, password_hash, full_name, role_id, is_active)
SELECT 'super_admin', 'admin@hospital.com', 'admin123', 'Super Administrator', id, TRUE
FROM Roles WHERE role_name = 'SUPER_ADMIN';

-- Blood Bank Admin
INSERT INTO Users_RBAC (username, email, password_hash, full_name, role_id, is_active)
SELECT 'bank_admin', 'bankadmin@hospital.com', 'admin123', 'Blood Bank Administrator', id, TRUE
FROM Roles WHERE role_name = 'BLOOD_BANK_ADMIN';

-- Hospital User (needs hospital_id)
INSERT INTO Users_RBAC (username, email, password_hash, full_name, role_id, hospital_id, is_active)
SELECT 'hospital_user', 'hospital@hospital.com', 'user123', 'Hospital Staff', id, 1, TRUE
FROM Roles WHERE role_name = 'HOSPITAL_USER';

-- Staff Member
INSERT INTO Users_RBAC (username, email, password_hash, full_name, role_id, is_active)
SELECT 'staff', 'staff@hospital.com', 'staff123', 'Data Entry Staff', id, TRUE
FROM Roles WHERE role_name = 'STAFF_MEMBER';
```

---

## Step 7: Audit Logging

### 7.1 Automatic Logging

Every protected action is automatically logged:

```python
# This automatically logs the action
@permission_required('request:approve')
def approve_request(request_id):
    # Action is logged by update_request_status_secure()
    update_request_status_secure(request_id, 'Approved')
```

### 7.2 Manual Audit Logging

Log custom events manually:

```python
# Log a custom action
log_audit_event(
    user_id=session.get('user_id'),
    action='EXPORT_DATA',
    resource_type='Report',
    resource_id=None,
    old_value=None,
    new_value={'format': 'PDF', 'records': 1000},
    status='Success'
)
```

### 7.3 View Audit Logs

```python
@app.route('/audit-logs')
@permission_required('audit:read')
def view_all_audit_logs():
    """Super Admin and Blood Bank Admin see all logs"""
    logs = get_audit_logs(user_id=None, days=90, limit=500)
    return render_template('audit_logs.html', logs=logs)

@app.route('/my-audit-logs')
def view_my_audit_logs():
    """All users can see their own logs"""
    user_id = session.get('user_id')
    logs = get_audit_logs(user_id=user_id, days=30, limit=100)
    return render_template('my_audit_logs.html', logs=logs)
```

---

## Step 8: Security Best Practices

### 8.1 Password Hashing (CRITICAL!)

**Current Implementation (DEMO ONLY):**
```python
# NOT SECURE - plain text comparison
if user['password_hash'] != password:
    # ...
```

**Production Implementation (Use bcrypt):**
```python
import bcrypt

# When creating user
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

# When checking password
def verify_password(password, hash):
    return bcrypt.checkpw(password.encode('utf-8'), hash)

# In login
if verify_password(password, user['password_hash']):
    # Login successful
```

### 8.2 Session Security

```python
app.config['SESSION_COOKIE_SECURE'] = True      # HTTPS only (production)
app.config['SESSION_COOKIE_HTTPONLY'] = True    # No JS access
app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'  # CSRF protection
app.config['PERMANENT_SESSION_LIFETIME'] = 1800 # 30 minutes
```

### 8.3 Input Validation

```python
@app.route('/create-donor', methods=['POST'])
@permission_required('donor:create')
def create_donor():
    # Validate input
    name = request.form.get('name', '').strip()
    age = int(request.form.get('age', 0))
    
    if not name or len(name) < 2:
        flash('Invalid name', 'danger')
        return redirect(url_for('add_donor'))
    
    if age < 18 or age > 120:
        flash('Age must be between 18 and 120', 'danger')
        return redirect(url_for('add_donor'))
```

### 8.4 Conflict of Interest Prevention

```python
# Hospital CANNOT approve their own request
def can_approve_blood_request(user_id, request_id):
    # ... gets user's hospital ...
    # ... gets request's hospital ...
    
    # CRITICAL CHECK
    if user_hospital_id == request_hospital_id:
        return False, "Conflict of Interest: Cannot approve own request"
```

---

## Step 9: Testing Your RBAC Implementation

### 9.1 Test Case 1: Hospital Cannot Approve Own Request

```
1. Login as: hospital_user (HOSPITAL_USER role)
2. Go to: /request-blood
3. Create a blood request
4. Try to approve it
   → EXPECTED: ❌ Permission Denied (can't approve own request)
5. Verify audit log shows denial reason
```

### 9.2 Test Case 2: Admin Can Approve Any Request

```
1. Login as: bank_admin (BLOOD_BANK_ADMIN role)
2. Go to: /requests
3. Approve a request from any hospital
   → EXPECTED: ✅ Success
4. Audit log shows "REQUEST_APPROVED" by bank_admin
5. Inventory decreases by requested units
```

### 9.3 Test Case 3: Staff Cannot Approve

```
1. Login as: staff (STAFF_MEMBER role)
2. Try to access: /update-request/1/Approved
   → EXPECTED: ❌ 403 Forbidden (Permission Denied)
3. Audit log shows "PERMISSION_DENIED" attempt
```

### 9.4 Test Case 4: Audit Trail Verification

```
1. Login as: super_admin (SUPER_ADMIN role)
2. Go to: /audit-logs
3. See all actions by all users
4. Filter by action: "REQUEST_APPROVED"
5. Verify fields:
   - user_id: Who approved
   - old_value: Status before
   - new_value: Status after
   - created_at: When approved
```

---

## Step 10: Common Implementation Patterns

### Pattern 1: Admin Override (With Logging)

```python
@app.route('/force-approve/<int:request_id>')
@role_required('SUPER_ADMIN')  # Only super admin
def force_approve(request_id):
    """Super admin can override normal rules"""
    user_id = session.get('user_id')
    
    # Log the override action explicitly
    log_audit_event(
        user_id=user_id,
        action='FORCE_APPROVE_REQUEST',  # Different action name
        resource_type='BloodRequest',
        resource_id=request_id,
        status='Success',
        reason_if_denied=None  # Success, no denial reason
    )
    
    # Perform the action
    update_status(request_id, 'Approved')
```

### Pattern 2: Read-Only Access for Higher Roles

```python
def view_donations():
    user_id = session.get('user_id')
    user_info = get_current_user_info()
    
    if user_info['role_name'] in ['SUPER_ADMIN', 'BLOOD_BANK_ADMIN']:
        # See all donations
        query = "SELECT * FROM Donations ORDER BY donation_date DESC"
        can_edit = True
    elif user_info['role_name'] == 'DONOR':
        # See only own donations
        query = """
            SELECT * FROM Donations 
            WHERE donor_id = (
                SELECT id FROM Donors WHERE user_id = %s
            )
        """
        can_edit = False
    
    # ... execute and render ...
```

### Pattern 3: Automatic User-to-Hospital Binding

```python
def view_my_requests():
    """Hospital user sees only their hospital's requests"""
    user_id = session.get('user_id')
    user_info = get_current_user_info()
    
    # Enforce hospital filter
    cursor.execute("""
        SELECT * FROM Blood_Requests br
        WHERE br.hospital_id = %s
        AND br.hospital_id = (
            SELECT hospital_id FROM Users_RBAC WHERE id = %s
        )
    """, (user_info['hospital_id'], user_id))
```

---

## Troubleshooting

### Issue: "Permission Denied" on every protected route

**Cause:** User doesn't have permission in Roles/Permissions tables

**Solution:**
```sql
-- Check user's role
SELECT u.username, r.role_name 
FROM Users_RBAC u
JOIN Roles r ON u.role_id = r.id
WHERE u.id = 1;

-- Check role's permissions
SELECT p.permission_name
FROM Roles r
JOIN Role_Permissions rp ON r.id = rp.role_id
JOIN Permissions p ON rp.permission_id = p.id
WHERE r.role_name = 'BLOOD_BANK_ADMIN';
```

### Issue: Audit logs not appearing

**Cause:** Error in log_audit_event() function

**Solution:**
```python
# Check error logs
tail -f /var/log/flask.log

# Test manually
from rbac import log_audit_event
log_audit_event(1, 'TEST_ACTION', 'TestResource', 1, status='Success')
```

### Issue: "Conflict of Interest" error on request approval

**Cause:** User is from the hospital requesting blood

**Solution:** This is CORRECT BEHAVIOR! Hospitals cannot approve their own requests. Only Blood Bank Admin can.

---

## Performance Optimization

### 1. Permission Caching

Permissions are cached in memory to reduce database queries:

```python
# Cache is automatically populated on first access
permissions = get_user_permissions(user_id)  # DB query

# Second access uses cache
permissions = get_user_permissions(user_id)  # Memory (fast)

# Invalidate cache when permissions change
invalidate_permission_cache(user_id=1)
```

### 2. Use Redis for Distributed Systems

For production with multiple servers:

```python
import redis
cache = redis.Redis(host='localhost', port=6379)

def get_user_permissions_cached(user_id):
    key = f"user:{user_id}:permissions"
    permissions = cache.get(key)
    
    if not permissions:
        permissions = get_user_permissions_from_db(user_id)
        cache.setex(key, 3600, json.dumps(permissions))  # Cache 1 hour
    
    return json.loads(permissions)
```

---

## FAQ

**Q: Can a user have multiple roles?**
A: Currently, each user has ONE role. For multiple roles, modify `Users_RBAC` to have `role_id` as a foreign key to a junction table.

**Q: How do I change a user's permission?**
A: Modify role permissions, don't change individual user permissions:
```sql
-- Add permission to role
INSERT INTO Role_Permissions (role_id, permission_id)
SELECT r.id, p.id FROM Roles r, Permissions p
WHERE r.role_name = 'STAFF_MEMBER' AND p.permission_name = 'request:read';

-- Remove permission from role
DELETE FROM Role_Permissions
WHERE role_id = (SELECT id FROM Roles WHERE role_name = 'STAFF_MEMBER')
AND permission_id = (SELECT id FROM Permissions WHERE permission_name = 'request:read');
```

**Q: How long are audit logs kept?**
A: Forever (not auto-deleted). Implement your own retention policy:
```sql
-- Delete logs older than 1 year
DELETE FROM Audit_Logs WHERE created_at < DATE_SUB(NOW(), INTERVAL 1 YEAR);
```

**Q: Can I see who tried unauthorized actions?**
A: Yes! Query audit logs with status='Denied':
```sql
SELECT * FROM Audit_Logs WHERE status = 'Denied' ORDER BY created_at DESC LIMIT 100;
```

---

## Summary

You now have:
✅ 5 user roles with clear responsibilities
✅ 50+ granular permissions
✅ RBAC decorators for route protection
✅ Business logic with separation of concerns
✅ Complete audit trail
✅ Conflict-of-interest prevention
✅ Session security
✅ Permission caching

**Next Steps:**
1. Run `rbac_schema.sql` to create tables
2. Update `app.py` imports
3. Register RBAC routes
4. Test with provided test cases
5. Implement password hashing
6. Deploy to production

---

**Version:** 1.0  
**Last Updated:** February 2026  
**Status:** Production Ready ✅
