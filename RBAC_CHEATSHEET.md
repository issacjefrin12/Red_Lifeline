# 🔐 RBAC Security Cheat Sheet

## Quick Reference - Permission Matrix

```
User Role          | Can Create | Can Approve | Can View All | Data Entry | Audit
                   | Requests   | Requests    | Requests     | Authority  | Logs
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUPER_ADMIN        | ✅ ALL         | ✅ ALL         | ✅ YES        | ✅ YES     | ✅ FULL
BLOOD_BANK_ADMIN   | ❌ OTHER's     | ✅ ANY         | ✅ YES        | ✅ YES     | ✅ FULL
HOSPITAL_USER      | ✅ OWN ONLY    | ❌ NO ALL      | ❌ OWN ONLY   | ❌ NO      | ✅ SELF
STAFF_MEMBER       | ❌ NO          | ❌ NO          | ❌ NO         | ✅ YES     | ✅ SELF
DONOR              | ❌ NO          | ❌ NO          | ❌ NO         | ❌ NO      | ✅ SELF
```

---

## Code Snippets for Common Tasks

### 1. Protect Route by Permission

```python
@app.route('/approve-request/<int:id>')
@permission_required('request:approve')
def approve_request_route(id):
    """Auto-denies if user lacks permission"""
    success, msg, changes = update_request_status_secure(id, 'Approved')
    flash(msg, 'success' if success else 'danger')
    return redirect(url_for('view_requests'))
```

### 2. Check Permission in Code

```python
from rbac import user_has_permission

user_id = session.get('user_id')

if user_has_permission(user_id, 'request:approve'):
    # Perform action
    approve_request(request_id)
else:
    # Deny
    flash('Permission denied', 'danger')
```

### 3. Enforce Business Logic

```python
from rbac import can_approve_blood_request

# Check both permission AND business rule
can_approve, reason = can_approve_blood_request(user_id, request_id)

if can_approve:
    update_status(request_id, 'Approved')
else:
    # Examples of reasons:
    # "Missing permission: request:approve"
    # "Cannot approve request from your own hospital"
    # "Request is already Approved"
    flash(reason, 'danger')
```

### 4. Hospital User Views Own Data Only

```python
user_info = get_current_user_info()

if user_info['role_name'] == 'HOSPITAL_USER':
    hospital_id = user_info['hospital_id']
    cursor.execute("""
        SELECT * FROM Blood_Requests 
        WHERE hospital_id = %s
    """, (hospital_id,))
else:
    # Admin sees all
    cursor.execute("SELECT * FROM Blood_Requests")
```

### 5. Log Audit Event

```python
from rbac import log_audit_event

log_audit_event(
    user_id=session.get('user_id'),
    action='APPROVE_REQUEST',
    resource_type='BloodRequest',
    resource_id=request_id,
    old_value={'status': 'Pending'},
    new_value={'status': 'Approved'},
    status='Success'
)
```

### 6. Log Denied Access

```python
log_audit_event(
    user_id=user_id,
    action='APPROVE_REQUEST_DENIED',
    resource_type='BloodRequest',
    resource_id=request_id,
    status='Denied',
    reason_if_denied='Conflict of Interest: Cannot approve own hospital'
)
```

### 7. Get User's Permissions

```python
from rbac import get_user_permissions

user_id = session.get('user_id')
permissions = get_user_permissions(user_id)

# permissions = ['donor:create', 'donation:create', 'inventory:read', ...]

# Check if user has specific permission
if 'request:approve' in permissions:
    # Can approve
else:
    # Cannot approve
```

### 8. Create User with Role

```
SQL:
INSERT INTO Users_RBAC 
(username, email, password_hash, full_name, role_id, hospital_id)
SELECT 'john_doe', 'john@hospital.com', 'HASH_HERE', 'John Doe', id, 2
FROM Roles WHERE role_name = 'HOSPITAL_USER';
```

---

## Critical Business Rules

### Rule 1: Conflict of Interest
```
❌ FORBIDDEN: Hospital approves own blood request
✅ REQUIRED: Only Blood Bank Admin can approve

Code Check:
if user_hospital_id == request_hospital_id:
    return False, "Cannot approve own hospital's request"
```

### Rule 2: Read-Only Access
```
❌ FORBIDDEN: Hospital User requests info sees other hospitals
✅ REQUIRED: Hospital User only sees own requests

Code Check:
WHERE hospital_id = user_hospital_id
```

### Rule 3: No Approval Without Permission
```
❌ FORBIDDEN: Staff Member approves request
✅ REQUIRED: Only BLOOD_BANK_ADMIN or SUPER_ADMIN

Code Check:
@permission_required('request:approve')
```

### Rule 4: Data Entry Authority
```
✅ ALLOWED: Staff Member records donations
❌ FORBIDDEN: Staff Member approves requests

Code Check:
permissions = ['donation:create']  # Yes
permissions = ['request:approve']  # No
```

---

## Testing Checklist

- [ ] Hospital User cannot access other hospitals' requests
- [ ] Hospital User cannot approve own request
- [ ] Staff Member cannot approve any request
- [ ] Blood Bank Admin can approve any request
- [ ] Super Admin can override all rules
- [ ] All actions are audited to Audit_Logs
- [ ] Denied attempts are logged with reason
- [ ] User cannot create donation with invalid age
- [ ] User cannot request more than max units (50)
- [ ] Inventory decreases on request approval
- [ ] Donor's last_donation_date updates on donation
- [ ] Account locks after 5 failed login attempts
- [ ] Session expires after configured time

---

## Database Queries for Verification

### Check User's Full Permissions
```sql
SELECT DISTINCT p.permission_name, p.resource, p.action
FROM Users_RBAC u
JOIN Roles r ON u.role_id = r.id
JOIN Role_Permissions rp ON r.id = rp.role_id
JOIN Permissions p ON rp.permission_id = p.id
WHERE u.username = 'john_doe'
ORDER BY p.resource, p.action;
```

### Check All Denied Access Attempts
```sql
SELECT u.username, al.action, al.reason_if_denied, al.created_at
FROM Audit_Logs al
LEFT JOIN Users_RBAC u ON al.user_id = u.id
WHERE al.status = 'Denied'
ORDER BY al.created_at DESC
LIMIT 50;
```

### Check Who Approved a Request
```sql
SELECT br.id, br.status, u.username as approved_by, 
       br.approval_date, br.created_at
FROM Blood_Requests br
LEFT JOIN Users_RBAC u ON br.approved_by = u.id
WHERE br.id = 123;
```

### Check Request Timeline
```sql
SELECT al.action, u.username, al.created_at, al.status
FROM Audit_Logs al
LEFT JOIN Users_RBAC u ON al.user_id = u.id
WHERE al.resource_type = 'BloodRequest' AND al.resource_id = 123
ORDER BY al.created_at ASC;
```

### Check Hospital User's Hospital Assignment
```sql
SELECT u.username, h.name as hospital_name, u.is_active
FROM Users_RBAC u
LEFT JOIN Hospitals h ON u.hospital_id = h.id
WHERE u.role_id = (SELECT id FROM Roles WHERE role_name = 'HOSPITAL_USER');
```

---

## Common Errors & Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| 403 Permission Denied | Missing permission | Add permission to user's role |
| Conflict of Interest error | User from same hospital | ✅ CORRECT - prevents fraud |
| Can't see requests | Wrong hospital_id | Verify `Users_RBAC.hospital_id` matches `Hospitals.id` |
| Request not found | Wrong request_id | Check `Blood_Requests` exists |
| Insufficient inventory | Not enough blood units | Check `Blood_Inventory.quantity_units` |
| Account locked | 5 failed login attempts | Admin must unlock in `Users_RBAC` |

---

## Permission Names Reference

### Donor Operations
- `donor:create` - Create new donor record
- `donor:read` - View all donors
- `donor:read_self` - View own profile  
- `donor:update` - Update donor info
- `donor:delete` - Delete donor

### Donation Operations
- `donation:create` - Record donation
- `donation:read` - View all donations
- `donation:read_self` - View own donations
- `donation:update` - Update donation
- `donation:delete` - Delete donation

### Blood Request Operations
- `request:create` - Create blood request
- `request:read` - View all requests
- `request:read_self` - View own requests
- `request:approve` - Approve request
- `request:reject` - Reject request
- `request:update_status` - Admin override

### Inventory Operations
- `inventory:read` - View inventory
- `inventory:update` - Update units
- `inventory:manage` - Full management

### Hospital Operations
- `hospital:create` - Register hospital
- `hospital:read` - View hospitals
- `hospital:update` - Update hospital
- `hospital:approve` - Approve registration
- `hospital:delete` - Delete hospital

### Audit & Administration
- `audit:read` - View all audit logs
- `audit:read_self` - View own logs
- `users:create` - Create users
- `users:read` - View users
- `users:update` - Update users
- `users:delete` - Delete users
- `users:assign_role` - Assign roles
- `system:config` - System configuration

---

## Decorator Reference

### By Permission (RECOMMENDED)
```python
@permission_required('request:approve')
def approve_request():
    # Only users with this permission can access
```

### By Role
```python
@role_required('BLOOD_BANK_ADMIN', 'SUPER_ADMIN')
def admin_function():
    # Only users with these roles can access
```

### No Decorator (PUBLIC)
```python
@app.route('/login')
def login():
    # No decorator = publicly accessible
```

---

**Quick Copy-Paste Examples:**

```python
# Example 1: Protect donation creation
@app.route('/donation/create', methods=['POST'])
@permission_required('donation:create')
def create_donation():
    user_id = session['user_id']
    log_audit_event(user_id, 'CREATE_DONATION', 'Donation', None)
    # ... implementation ...

# Example 2: Hospital self-service with validation
@app.route('/request/create', methods=['POST'])
@permission_required('request:create')
def hospital_request():
    user_info = get_current_user_info()
    hospital_id = user_info['hospital_id']  # Only their hospital
    blood_group = request.form['blood_group']
    units = int(request.form['units'])
    
    success, req_id, msg = create_blood_request_hospital(
        hospital_id, blood_group, units, session['user_id']
    )
    flash(msg, 'success' if success else 'danger')
    return redirect(url_for('view_requests'))

# Example 3: Admin approval with conflict check
@app.route('/request/<id>/approve')
@permission_required('request:approve')
def approve():
    user_id = session['user_id']
    can_approve, reason = can_approve_blood_request(user_id, request_id)
    
    if not can_approve:
        log_audit_event(user_id, 'APPROVE', 'BloodRequest', request_id,
                       status='Denied', reason_if_denied=reason)
        flash(reason, 'danger')
        return redirect(url_for('view_requests'))
    
    success, msg, _ = update_request_status_secure(request_id, 'Approved')
    flash(msg, 'success' if success else 'danger')
    return redirect(url_for('view_requests'))
```

---

**Version:** 1.0  
**Status:** Production Ready ✅
