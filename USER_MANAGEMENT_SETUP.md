# 🚀 USER MANAGEMENT & ROLE-BASED DASHBOARD SETUP GUIDE

**Complete implementation guide for creating and managing users with role-specific dashboards**

---

## 📋 What You Now Have

### Files Created
1. **user_management.py** (450+ lines)
   - UserManager class - User creation and lifecycle management
   - RoleManager class - Role and permission management  
   - DashboardManager class - Role-specific dashboard data

2. **user_routes.py** (400+ lines)
   - Admin routes for user management
   - Role-based dashboard routes
   - User creation endpoints

3. **Dashboard Templates** (HTML)
   - super_admin_dashboard.html - System overview
   - (Other role dashboards - ready to create)

---

## 🎯 SUPER ADMIN - How to Create Users

### Step 1: Login as SUPER_ADMIN

First user (bootstrap):
```
Email: super_admin@blood.local
Password: SuperAdminPass123
```

### Step 2: Go to User Management

```
URL: http://localhost:5000/admin/users
Button: Create New User
```

### Step 3: Fill User Creation Form

```
Username: blood_bank_admin1
Email: bank_admin@blood.local
Password: AdminPass123
Role: BLOOD_BANK_ADMIN
Hospital: (leave blank for non-hospital roles)
```

### Step 4: User Created!

The user can now login with:
```
Email: bank_admin@blood.local
Password: AdminPass123
```

---

## 🔐 5 ROLES & THEIR DASHBOARDS

### 1️⃣ SUPER_ADMIN 👑
**What they see:**
- Total users, hospitals, donors, inventory
- Pending approvals count
- Low stock alerts
- Users by role breakdown
- Recent audit logs
- User management interface

**What they can do:**
```
✅ Create users
✅ Assign roles
✅ Deactivate users
✅ View audit logs
✅ System analytics
```

**URL:** `/admin/dashboard`

**Create from:** Auto-created in database setup

---

### 2️⃣ BLOOD_BANK_ADMIN 🏥
**What they see:**
- Current blood inventory (exact numbers)
- Pending blood requests
- Low stock alerts
- Recent donations
- Request statistics

**What they can do:**
```
✅ Approve blood requests
✅ Reject blood requests
✅ View donor database
✅ View hospital requests
✅ Generate reports
```

**URL:** `/admin/dashboard`

**Create:** SUPER_ADMIN @ /admin/users/create

```
Role: BLOOD_BANK_ADMIN
Hospital: Leave blank (blood bank staff, not hospital-specific)
```

---

### 3️⃣ STAFF_MEMBER 🩺
**What they see:**
- Donor list (all)
- Register new donors form
- Record donation form
- Donations recorded today
- Blood inventory (read-only)
- Pending requests (read-only)
- Eligible donors count

**What they can do:**
```
✅ Register donors
✅ Record donations  
✅ Update donor details
❌ Cannot approve requests
❌ Cannot modify inventory
```

**URL:** `/admin/dashboard`

**Create:** SUPER_ADMIN @ /admin/users/create

```
Role: STAFF_MEMBER
Hospital: Leave blank (blood bank employee)
```

---

### 4️⃣ HOSPITAL_USER 🏨
**What they see:**
- Blood availability (generic: Adequate/Low/Critical)
- Their hospital's requests only
- Request status history
- Cannot see other hospitals' data
- Cannot see exact inventory numbers

**What they can do:**
```
✅ Create blood request
✅ Edit request (only if Pending)
✅ Cancel request (only if Pending)
✅ View request history
❌ Cannot approve
❌ Cannot see exact inventory
❌ Cannot see other hospitals
```

**URL:** `/admin/dashboard`

**Create:** SUPER_ADMIN @ /admin/users/create

```
Role: HOSPITAL_USER
Hospital: Select a hospital (REQUIRED)
```

---

### 5️⃣ DONOR 🩸
**What they see:**
- Their personal profile
- Last donation date
- Total donations made
- Donation history
- Eligible to donate date
- Emergency alerts

**What they can do:**
```
✅ Update contact info
✅ Mark availability
✅ View donation history
❌ Cannot view other donors
❌ Cannot modify anything else
```

**URL:** `/admin/dashboard`

**Create:** Not typically created via admin panel (use donor registration form)

---

## 📝 Step-by-Step User Creation

### For BLOOD_BANK_ADMIN

```
1. Login as: super_admin@blood.local / SuperAdminPass123
2. Go to: /admin/users/create
3. Fill form:
   - Username: blood_bank_admin
   - Email: admin@blood.local
   - Password: AdminPass123 (they should change this)
   - Role: BLOOD_BANK_ADMIN
   - Hospital: Leave blank
4. Click: Create User
5. They login with: admin@blood.local / AdminPass123
6. Their dashboard: /admin/dashboard → Shows inventory, requests
```

### For STAFF_MEMBER

```
1. Login as: super_admin@blood.local / SuperAdminPass123
2. Go to: /admin/users/create
3. Fill form:
   - Username: staff_john
   - Email: john@bloodbank.local
   - Password: StaffPass123
   - Role: STAFF_MEMBER
   - Hospital: Leave blank
4. Click: Create User
5. They login with: john@bloodbank.local / StaffPass123
6. Their dashboard: /admin/dashboard → Shows donors, donations
```

### For HOSPITAL_USER

```
1. Login as: super_admin@blood.local / SuperAdminPass123
2. Go to: /admin/users/create
3. Fill form:
   - Username: hospital_request_user
   - Email: requests@cityhosp.local
   - Password: HospitalPass123
   - Role: HOSPITAL_USER
   - Hospital: City Hospital (SELECT FROM LIST)
4. Click: Create User
5. They login with: requests@cityhosp.local / HospitalPass123
6. Their dashboard: /admin/dashboard → Shows their requests only
```

---

## 🔑 API ENDPOINTS for User Management

### Create User (SUPER_ADMIN only)
```
POST /admin/users/create
Content-Type: application/json

{
  "username": "blood_admin",
  "email": "admin@blood.local",
  "password": "SecurePassword123",
  "role_id": 2,
  "hospital_id": null
}

Response:
{
  "success": true,
  "message": "User 'blood_admin' created successfully",
  "user_id": 5
}
```

### List All Users
```
GET /admin/users

Response:
{
  "success": true,
  "users": [
    {
      "id": 1,
      "username": "super_admin",
      "email": "super_admin@blood.local",
      "role_name": "SUPER_ADMIN",
      "hospital_name": null,
      "is_active": true,
      "created_at": "2024-01-01T10:00:00"
    },
    ...
  ],
  "total": 5
}
```

### Get User Details
```
GET /admin/users/5

Response:
{
  "success": true,
  "user": {
    "id": 5,
    "username": "blood_admin",
    "email": "admin@blood.local",
    "role_id": 2,
    "role_name": "BLOOD_BANK_ADMIN",
    "hospital_id": null,
    "hospital_name": null,
    "is_active": true,
    "created_at": "2024-01-15T14:30:00",
    "last_login": "2024-01-15T15:00:00"
  }
}
```

### Update User Role
```
POST /admin/users/5/role
Content-Type: application/json

{
  "role_id": 3
}

Response:
{
  "success": true,
  "message": "User role updated successfully"
}
```

### Deactivate User
```
POST /admin/users/5/deactivate

Response:
{
  "success": true,
  "message": "User deactivated successfully"
}
```

### Get Dashboard Data
```
GET /admin/dashboard/data

Response:
{
  "role": "BLOOD_BANK_ADMIN",
  "inventory": [
    {"blood_group": "O+", "quantity_units": 50, "critical_threshold": 5},
    ...
  ],
  "pending_requests": [
    {
      "id": 1,
      "hospital_name": "City Hospital",
      "blood_group": "O+",
      "units_required": 10,
      "request_date": "2024-01-15T09:00:00"
    },
    ...
  ],
  "low_stock_alerts": [...]
}
```

---

## 🔧 Integration with app.py

Add to your **app.py**:

```python
# At the top with other imports
from user_routes import register_user_management_routes
from user_management import UserManager, RoleManager, DashboardManager

# After app = Flask(__name__):
app = Flask(__name__)
app.secret_key = 'your-secret-key'

# Register user management routes
register_user_management_routes(app)

# Then your other route registrations...
```

---

## 📊 Dashboard URLs

After login, users are redirected to their role-specific dashboard:

| Role | URL | Shows |
|------|-----|-------|
| SUPER_ADMIN | `/admin/dashboard` | System overview, user management |
| BLOOD_BANK_ADMIN | `/admin/dashboard` | Inventory, pending requests |
| STAFF_MEMBER | `/admin/dashboard` | Donors, donations, add new |
| HOSPITAL_USER | `/admin/dashboard` | My hospital's requests, availability |
| DONOR | `/admin/dashboard` | My profile, donation history |

---

## ✅ Testing User Creation and Login

### Test 1: Create BLOOD_BANK_ADMIN

```bash
# Using curl to create user
curl -X POST http://localhost:5000/admin/users/create \
  -H "Content-Type: application/json" \
  -b "session_cookie" \
  -d '{
    "username": "test_admin",
    "email": "test@blood.local",
    "password": "TestPass123",
    "role_id": 2,
    "hospital_id": null
  }'

# Expected response:
{
  "success": true,
  "message": "User 'test_admin' created successfully",
  "user_id": 6
}
```

### Test 2: Login as New User

```
Email: test@blood.local
Password: TestPass123
```

### Test 3: Check Dashboard

Navigate to `/admin/dashboard`
Should see BLOOD_BANK_ADMIN specific dashboard

---

## 🎨 Role-Based Dashboard Features

### SUPER_ADMIN Gets:
- User management interface at `/admin/users`
- User creation form at `/admin/users/create`
- Role management at `/admin/roles`
- System statistics
- User activity audit logs

### BLOOD_BANK_ADMIN Gets:
- Full inventory list (exact numbers)
- Pending requests list
- Low stock alerts
- Donation records
- Approval buttons on requests

### STAFF_MEMBER Gets:
- Donor registration form
- Donation recording form
- List of all donors
- Today's donations
- Inventory (read-only)

### HOSPITAL_USER Gets:
- Blood availability (generic: Low/Adequate)
- Their hospital's requests only
- Request creation form
- Current request status

### DONOR Gets:
- Personal profile
- Donation history
- Next eligible donation date
- Update contact information

---

## 🔐 Permissions Enforced

```
SUPER_ADMIN:
  ✅ user:create
  ✅ user:edit
  ✅ user:deactivate
  ✅ admin:manage
  ✅ audit:read

BLOOD_BANK_ADMIN:
  ✅ request:approve
  ✅ request:reject
  ✅ inventory:view
  ✅ donation:view

STAFF_MEMBER:
  ✅ donor:create
  ✅ donation:record
  ✅ donation:view

HOSPITAL_USER:
  ✅ request:create
  ✅ request:view_own

DONOR:
  ✅ profile:view
  ✅ profile:edit
  ✅ donation:history:view
```

---

## 🐛 Troubleshooting

### "User creation failed"
- Check email doesn't already exist
- Verify role_id is valid
- Check database connection

### "Can't login after creation"
- Verify email correct
- Check password didn't change
- Verify user is_active = TRUE

### "Wrong dashboard showing"
- Check user's role_id in database
- Verify role is active

### "Can't create users"
- Verify logged in as SUPER_ADMIN
- Check permission: admin:manage

---

## 📚 Complete File List

1. **Core Files**:
   - user_management.py (450 lines) - Core logic
   - user_routes.py (400 lines) - Flask routes

2. **Templates** (Create these):
   - templates/admin/user_list.html
   - templates/admin/create_user.html
   - templates/admin/user_detail.html
   - templates/admin/role_list.html
   - templates/dashboard/super_admin_dashboard.html
   - templates/dashboard/blood_bank_admin_dashboard.html
   - templates/dashboard/staff_member_dashboard.html
   - templates/dashboard/hospital_user_dashboard.html
   - templates/dashboard/donor_dashboard.html

3. **Modified Files**:
   - app.py (add imports and register routes)
   - rbac_schema.sql (already has Users_RBAC table)

---

## 🚀 Next Steps

1. **Copy user_management.py** to project
2. **Copy user_routes.py** to project
3. **Update app.py** to register routes
4. **Create dashboard templates** (HTML files)
5. **Test user creation** via `/admin/users/create`
6. **Test login** with different roles
7. **Verify dashboards** show correct data

---

## 💡 Quick Tips

- **Passwords**: Use bcrypt hashing (werkzeug.security.generate_password_hash)
- **Sessions**: Flask sessions store user_id
- **Permissions**: @permission_required decorator enforces access
- **Audit**: All user creation logged
- **Hospitals**: Required for HOSPITAL_USER, optional for others

---

**Status**: ✅ Ready to implement  
**Estimated setup time**: 1-2 hours  
**No changes to existing code needed** - Just add new files and register routes
