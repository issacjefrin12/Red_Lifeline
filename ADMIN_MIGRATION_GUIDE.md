# 🔐 Admin Account Migration Guide

**Migrate your existing admin account to the new Users_RBAC system**

---

## 📋 What This Does

Takes your existing admin account:
```
Username: admin
Password: admin123
```

And creates it as a **SUPER_ADMIN** in the new `Users_RBAC` table with:
- ✅ Password hashing (bcrypt)
- ✅ Role assignment (SUPER_ADMIN = id 1)
- ✅ Email: admin@blood.local
- ✅ Full permissions

---

## 🚀 Option 1: Use Python Script (Recommended)

### Step 1: Update Database Config
Edit `migrate_admin.py` with your database credentials:

```python
DB_CONFIG = {
    'host': 'localhost',           # Your MySQL host
    'user': 'root',                # Your MySQL user
    'password': 'your_password',   # YOUR PASSWORD HERE ⚠️
    'database': 'blood_bank'       # Your database name
}
```

### Step 2: Run Migration Script
```bash
cd d:\BBMS
python migrate_admin.py
```

### Step 3: Follow Prompts
```
Database Configuration:
  Host:     localhost
  User:     root
  Database: blood_bank

Continue with migration? (yes/no): yes

🔄 Starting admin migration...
✓ Password hashed: admin123
✓ New admin account created in Users_RBAC

✅ Migration successful!

📋 Admin Account Details:
   Username: admin
   Email:    admin@blood.local
   Password: admin123
   Role:     SUPER_ADMIN (id=1)
```

---

## 🛠️ Option 2: Use SQL Script (Manual)

### Step 1: Generate Password Hash
Run in Python (or Python terminal):

```python
from werkzeug.security import generate_password_hash
hash_val = generate_password_hash('admin123', method='pbkdf2:sha256')
print(hash_val)
```

**Output**: A long hash string (starts with `pbkdf2:sha256:...`)

### Step 2: Copy Hash to SQL Script
Edit `migrate_admin.sql` and replace `PASTE_YOUR_HASH_HERE` with the hash from Step 1

### Step 3: Run SQL Script
```bash
mysql -u root -p blood_bank < migrate_admin.sql
```

Or in MySQL Workbench/Command Line:
1. Open `migrate_admin.sql`
2. Find the INSERT or UPDATE statement
3. Replace `PASTE_YOUR_HASH_HERE` with your hash
4. Execute the statement

### Step 4: Verify
```sql
SELECT id, username, email, role_id, is_active FROM Users_RBAC WHERE username = 'admin';
```

Expected result:
```
id | username | email               | role_id | is_active
1  | admin    | admin@blood.local   | 1       | 1
```

---

## ✅ Verification Steps

### After Migration, Verify:

1. **Check user exists in database**
   ```sql
   SELECT * FROM Users_RBAC WHERE username = 'admin';
   ```

2. **Check user has SUPER_ADMIN role**
   ```sql
   SELECT u.username, r.role_name 
   FROM Users_RBAC u
   JOIN Roles r ON u.role_id = r.id
   WHERE u.username = 'admin';
   ```

3. **Check user has admin:manage permission**
   ```sql
   SELECT rp.role_id, p.permission_name
   FROM Role_Permissions rp
   JOIN Permissions p ON rp.permission_id = p.id
   WHERE rp.role_id = 1;
   ```
   (Should show: `1 | admin:manage`)

4. **Test login**
   - Go to: `http://localhost:5000/login`
   - Username: `admin`
   - Password: `admin123`
   - Should redirect to `/admin/dashboard`

5. **Test admin functions**
   - Go to: `http://localhost:5000/admin/users`
   - Should see list of users
   - Should be able to create new users
   - Should see SUPER_ADMIN dashboard (system overview)

---

## 🆘 Troubleshooting

### "Connection refused" Error
**Problem**: Can't connect to MySQL database  
**Solution**:
1. Verify MySQL is running: `mysql -u root -p`
2. Check database credentials in script
3. Verify database name is correct

### "Table doesn't exist" Error
**Problem**: Users_RBAC table not found  
**Solution**:
1. Run database setup script first: `python setup_database.py`
2. Check database: `SHOW TABLES;`
3. Verify you're using correct database

### "Login fails with 'admin / admin123'"
**Problem**: User created but password doesn't work  
**Solution**:
1. Verify password hash is correct
2. Check hash starts with `pbkdf2:sha256:`
3. Try regenerating hash using Python
4. Verify is_active = 1 in database

### "'admin' already exists"
**Problem**: Admin user already in Users_RBAC table  
**Solution**:
1. Run UPDATE instead of INSERT
2. Check what role they currently have: `SELECT role_id FROM Users_RBAC WHERE username = 'admin';`
3. If role_id ≠ 1, update it: `UPDATE Users_RBAC SET role_id = 1 WHERE username = 'admin';`

---

## 📝 Quick Reference

| Item | Value |
|------|-------|
| Username | admin |
| Email | admin@blood.local |
| Password | admin123 |
| Role | SUPER_ADMIN (is=1) |
| Permission | admin:manage |
| Table | Users_RBAC |
| Dashboard URL | /admin/dashboard |
| User List URL | /admin/users |

---

## ✨ After Migration

Your admin account is now:
- ✅ In the new Users_RBAC table
- ✅ SUPER_ADMIN role (full access)
- ✅ Can create/manage other users
- ✅ Can assign roles
- ✅ Can deactivate/reactivate users
- ✅ Can view audit logs

**Ready to manage the entire system!** 🚀

---

## 📞 Need Help?

**Error during migration?**
1. Check the error message above
2. Verify database credentials
3. Ensure Users_RBAC table exists
4. Run: `SHOW TABLES;` in MySQL to verify

**Can't login after migration?**
1. Verify user in database: `SELECT * FROM Users_RBAC WHERE username='admin';`
2. Check is_active = 1
3. Check role_id = 1
4. Try resetting password

**Have questions?**
1. Read INTEGRATION_GUIDE.md
2. Check flask error logs
3. Review user_management.py code

---

**Status**: Ready to migrate 🔄

Choose:
- **Option 1 (Recommended)**: Run `python migrate_admin.py`
- **Option 2**: Run `migrate_admin.sql` with hash
