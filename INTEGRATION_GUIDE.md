# 🔧 INTEGRATION GUIDE - User Management System

**Step-by-step guide to integrate the new user management system into your Flask app**

---

## 📍 Location: `app.py`

### Step 1: Add Imports at the Top

After your existing imports, add these lines:

```python
# ===== USER MANAGEMENT IMPORTS =====
from user_management import UserManager, RoleManager, DashboardManager
from user_routes import register_user_management_routes
```

### Step 2: Register the Blueprint

After your Flask app initialization (after `app = Flask(__name__)`), add:

```python
# ===== BLUEPRINT REGISTRATION =====
# Register user management routes
register_user_management_routes(app)
```

**Example placement in app.py:**

```python
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import mysql.connector
from datetime import datetime
import logging

# ===== USER MANAGEMENT IMPORTS =====
from user_management import UserManager, RoleManager, DashboardManager
from user_routes import register_user_management_routes

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# ===== BLUEPRINT REGISTRATION =====
# Register user management routes
register_user_management_routes(app)

# Now define your other routes...
@app.route('/login', methods=['GET', 'POST'])
def login():
    # existing code...
```

---

## 🎯 Available Routes After Integration

### Admin User Management Routes

| Method | Route | Purpose | Requires Role |
|--------|-------|---------|---------------| 
| GET | `/admin/users` | List all users | SUPER_ADMIN |
| GET | `/admin/users/create` | Show create user form | SUPER_ADMIN |
| POST | `/admin/users/create` | Create new user | SUPER_ADMIN |
| GET | `/admin/users/<user_id>` | View user details | SUPER_ADMIN |
| POST | `/admin/users/<user_id>/role` | Update user role | SUPER_ADMIN |
| POST | `/admin/users/<user_id>/deactivate` | Deactivate user | SUPER_ADMIN |
| POST | `/admin/users/<user_id>/reactivate` | Reactivate user | SUPER_ADMIN |
| POST | `/admin/users/<user_id>/reset-login` | Reset failed logins | SUPER_ADMIN |
| GET | `/admin/roles` | List all roles | SUPER_ADMIN |
| GET | `/admin/roles/<role_id>` | View role details | SUPER_ADMIN |

### Dashboard Routes

| Method | Route | Purpose | Returns |
|--------|-------|---------|---------|
| GET | `/admin/dashboard` | Role-specific dashboard HTML | HTML page |
| GET | `/admin/dashboard/data` | Dashboard data as JSON | JSON data |

---

## 📋 Database Schema Requirements

Make sure your database has these tables from **rbac_schema.sql**:

### ✅ Required Tables

1. **Users_RBAC** (Existing)
   ```sql
   CREATE TABLE Users_RBAC (
       id INT PRIMARY KEY AUTO_INCREMENT,
       username VARCHAR(100) UNIQUE NOT NULL,
       email VARCHAR(100) UNIQUE NOT NULL,
       password_hash VARCHAR(255) NOT NULL,
       role_id INT NOT NULL,
       hospital_id INT,
       is_active BOOLEAN DEFAULT TRUE,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       created_by INT,
       last_login TIMESTAMP NULL,
       failed_login_attempts INT DEFAULT 0,
       FOREIGN KEY (role_id) REFERENCES Roles(id),
       FOREIGN KEY (hospital_id) REFERENCES Hospitals(id),
       FOREIGN KEY (created_by) REFERENCES Users_RBAC(id)
   );
   ```

2. **Roles** (Existing)
   ```sql
   CREATE TABLE Roles (
       id INT PRIMARY KEY AUTO_INCREMENT,
       role_name VARCHAR(50) UNIQUE NOT NULL,
       description TEXT,
       is_active BOOLEAN DEFAULT TRUE
   );
   ```

3. **Role_Permissions** (Existing)
   ```sql
   CREATE TABLE Role_Permissions (
       id INT PRIMARY KEY AUTO_INCREMENT,
       role_id INT NOT NULL,
       permission_id INT NOT NULL,
       FOREIGN KEY (role_id) REFERENCES Roles(id),
       FOREIGN KEY (permission_id) REFERENCES Permissions(id)
   );
   ```

4. **Permissions** (Existing)
   ```sql
   CREATE TABLE Permissions (
       id INT PRIMARY KEY AUTO_INCREMENT,
       permission_name VARCHAR(100) UNIQUE NOT NULL,
       description TEXT
   );
   ```

5. **Hospitals** (Existing)
   ```sql
   CREATE TABLE Hospitals (
       id INT PRIMARY KEY AUTO_INCREMENT,
       name VARCHAR(150) NOT NULL,
       address TEXT,
       contact VARCHAR(20),
       email VARCHAR(100)
   );
   ```

---

## 🚀 Testing the Integration

### Test 1: Access User Management

1. Login as SUPER_ADMIN
2. Navigate to: `http://localhost:5000/admin/users`
3. Should see list of users

### Test 2: Create New User

1. Click "Create New User" button
2. Fill in the form:
   - Username: `test_staff`
   - Email: `test@blood.local`
   - Password: `TestPass123`
   - Role: `STAFF_MEMBER`
   - Hospital: Leave blank

3. Click "Create User"
4. Should see success message

### Test 3: View Dashboard as Different Roles

1. Create test users for each role:
   ```
   Admin: blood_admin / AdminPass123
   Staff: blood_staff / StaffPass123
   Hospital: hosp_user / HospitalPass123
   ```

2. Login as each role
3. Navigate to `/admin/dashboard`
4. Verify role-specific dashboard displays

### Test 4: Deactivate User

1. Go to `/admin/users`
2. Click on a user
3. Click "Deactivate User"
4. That user can no longer login

---

## 🔌 API Endpoints for Developers

### Create User (Programmatic)

```javascript
// JavaScript fetch example
const response = await fetch('/admin/users/create', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    username: 'new_user',
    email: 'new@blood.local',
    password: 'Password123',
    role_id: 3,  // STAFF_MEMBER
    hospital_id: null
  })
});

const result = await response.json();
// result.success, result.message, result.user_id
```

### Get Dashboard Data (Programmatic)

```javascript
const response = await fetch('/admin/dashboard/data');
const dashboardData = await response.json();

// Returns role-specific data:
// dashboardData.role
// dashboardData.inventory
// dashboardData.pending_requests
// etc.
```

### Update User Role

```javascript
const response = await fetch('/admin/users/5/role', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    role_id: 2  // BLOOD_BANK_ADMIN
  })
});
```

---

## 🛡️ Security Configuration

The user management system uses the existing permission system from `rbac.py`:

### Permission Enforcement

All SUPER_ADMIN routes check this permission:
```python
@permission_required('admin:manage')
```

This means only users with `admin:manage` permission can access these endpoints.

### Password Hashing

Passwords are hashed using `werkzeug.security`:
```python
from werkzeug.security import generate_password_hash, check_password_hash

hashed = generate_password_hash('password123')
is_valid = check_password_hash(hashed, 'password123')
```

---

## 📊 Dashboard Data Structure

Each role receives different data from `/admin/dashboard/data`:

### SUPER_ADMIN
```json
{
  "role": "SUPER_ADMIN",
  "total_users": 5,
  "total_hospitals": 3,
  "total_donors": 150,
  "total_inventory": 500,
  "pending_approvals": 2,
  "low_stock_alerts": [...],
  "users_by_role": {...},
  "recent_audit_logs": [...]
}
```

### BLOOD_BANK_ADMIN
```json
{
  "role": "BLOOD_BANK_ADMIN",
  "inventory": [...],
  "pending_requests": [...],
  "low_stock_alerts": [...],
  "recent_donations": [...],
  "request_stats": {...}
}
```

### STAFF_MEMBER
```json
{
  "role": "STAFF_MEMBER",
  "total_donors": 150,
  "eligible_donors": 45,
  "donations_today": 10,
  "pending_requests_count": 2,
  "recent_donors": [...],
  "donations_today_list": [...],
  "inventory": [...]
}
```

### HOSPITAL_USER
```json
{
  "role": "HOSPITAL_USER",
  "hospital_name": "City Hospital",
  "blood_availability": {...},
  "pending_count": 2,
  "approved_count": 5,
  "rejected_count": 0,
  "your_requests": [...]
}
```

### DONOR
```json
{
  "role": "DONOR",
  "blood_group": "O+",
  "total_donations": 3,
  "last_donation_date": "2024-01-10",
  "is_eligible": true,
  "next_eligible_date": null,
  "donation_history": [...],
  "lives_saved": 9
}
```

---

## 🚨 Common Issues & Solutions

### Issue 1: Permission Denied When Creating User
**Solution**: Verify logged-in user has `admin:manage` permission
```python
# Check user permissions
from rbac import get_user_permissions
perms = get_user_permissions(session['user_id'])
# Should contain 'admin:manage'
```

### Issue 2: Hospital Dropdown is Empty
**Solution**: Ensure Hospitals table has data and HOSPITAL_USER role is assigned
```sql
SELECT * FROM Hospitals;  -- Should not be empty
```

### Issue 3: Dashboard Shows No Data
**Solution**: Check that user's role_id is correct in database
```sql
SELECT id, username, role_id FROM Users_RBAC WHERE email = 'user@blood.local';
```

### Issue 4: "User Already Exists"
**Solution**: Email and username must be unique
```python
# Use timestamps to make them unique
import time
username = f"staff_{int(time.time())}"
email = f"user_{int(time.time())}@blood.local"
```

---

## 📝 Template Variables Available

All dashboard templates have access to:

```jinja2
{{ dashboard_data }}          {# Complete dashboard data dict #}
{{ user_id }}                 {# Current logged-in user ID #}
{{ user_name }}               {# Current logged-in user name #}
{{ user_role }}               {# Current logged-in user role #}
{{ hospital_name }}           {# Hospital name (if applicable) #}
```

---

## 🎨 Customization Guide

### Modify Dashboard Styling

Edit template files in: `templates/dashboard/`

Each template uses Bootstrap classes:
```html
<!-- Edit colors -->
<div class="card border-danger">
    <div class="card-header bg-danger text-white">
```

### Add New Dashboard Sections

Edit the DashboardManager in `user_management.py`:

```python
def get_custom_dashboard(self, user_id, role_name):
    # Add your custom data retrieval logic
    custom_data = {
        'custom_field': 'value'
    }
    return custom_data
```

### Extend User Creation Form

Edit `/admin/users/create` route in `user_routes.py`:

```python
@user_mgmt_bp.route('/users/create', methods=['POST'])
def create_user():
    # Add custom fields
    custom_field = request.form.get('custom_field')
```

---

## ✅ Verification Checklist

After integration, verify:

- [ ] `app.py` has both imports (UserManager/RoleManager/DashboardManager and register_user_management_routes)
- [ ] Blueprint registered with `register_user_management_routes(app)`
- [ ] `user_management.py` exists in project root
- [ ] `user_routes.py` exists in project root
- [ ] All dashboard templates exist in `templates/dashboard/`
- [ ] Database schema run successfully
- [ ] SUPER_ADMIN user exists with id=1
- [ ] At least one role exists with 'admin:manage' permission
- [ ] `/admin/users` is accessible when logged in as SUPER_ADMIN
- [ ] Dashboard loads with role-specific data

---

## 🆘 Getting Help

If something doesn't work:

1. **Check app.py imports** - Make sure both lines added
2. **Check file paths** - Verify user_management.py and user_routes.py exist in root
3. **Check database** - Verify Users_RBAC table has all columns
4. **Check browser console** - Look for JavaScript errors
5. **Check Flask logs** - Look for Python exceptions

---

## 📚 Next Steps

1. ✅ Copy user_management.py to project root
2. ✅ Copy user_routes.py to project root
3. ✅ Copy dashboard templates to templates/dashboard/
4. **→ Edit app.py** with imports and blueprint registration
5. **→ Test user creation flow**
6. **→ Test login with different roles**
7. **→ Verify dashboards display correct data**

