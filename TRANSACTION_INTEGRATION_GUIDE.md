-- ========================================
-- TRANSACTION LOCKING - INTEGRATION GUIDE
-- ========================================

# blood Bank Management System - Transaction Locking Integration

## Overview

This guide provides step-by-step instructions for integrating the **Transaction Locking System** with **pessimistic locking** into your Blood Bank Management System.

**Previous Work**: You already have the RBAC system in place with role-based access control.  
**New Addition**: Transaction system adds concurrency safety with pessimistic locking to prevent race conditions.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Files Created](#2-files-created)
3. [Database Setup](#3-database-setup)
4. [Code Integration into app.py](#4-code-integration-into-apppy)
5. [Testing the Implementation](#5-testing-the-implementation)
6. [Recovery & Debugging](#6-recovery--debugging)
7. [Performance Tuning](#7-performance-tuning)
8. [Common Issues & Solutions](#8-common-issues--solutions)
9. [Deployment Checklist](#9-deployment-checklist)

---

## 1. Architecture Overview

### Problem Solved: Race Conditions

**Scenario**: Two admins simultaneously approve the same blood request

```
Timeline:
─────────────────────────────────────────────────────── time →

Admin A: Reads request (Pending)
                                Admin B: Reads request (Pending)
Admin A: Locks inventory → Checks stock (100 units)
Admin A: Deducts 10 units → Updates status to Approved ✅

                                Admin B: Locks inventory → Checks... (too late!)
                                Admin B: Stock now 90, but tries to deduct 15
                                Admin B: Inventory goes to 75 (should be 85!)
```

**Without pessimistic locking**: Double approval possible, inventory corrupted.

### Solution: Pessimistic Locking with SELECT...FOR UPDATE

```
Timeline with Pessimistic Locking:
──────────────────────────────────────────────────────

Admin A: SELECT ... FOR UPDATE (LOCKS row)
                                Admin B: SELECT ... (BLOCKED! Waiting for lock)
Admin A: Checks stock → Deducts → Updates → COMMITS (releases lock)

                                Admin B: Lock acquired! But status now = 'Approved'
                                Admin B: Detects already processed → ERROR ✅

Result: Double approval prevented! Inventory never corrupted!
```

### Architecture Diagram

```
┌──────────────────────────────────────────────────────────┐
│                    Flask HTTP Request                     │
│              POST /api/requests/<id>/approve              │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│        transaction_routes.py (HTTP Handler)              │
│  ✓ Check authentication (session)                        │
│  ✓ Check permissions (@permission_required)             │
│  ✓ Validate conflict of interest (can_approve...)        │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│    transaction_lock_handler.py (Transaction Manager)     │
│                                                          │
│  approve_request_multi_retry():                         │
│    START TRANSACTION                                    │
│    ├─ 1. SELECT Blood_Requests FOR UPDATE              │
│    │      (LOCK request row)                            │
│    │                                                    │
│    ├─ 2. IF status != 'Pending' → ABORT ✅             │
│    │      (Detect double approval)                      │
│    │                                                    │
│    ├─ 3. SELECT Blood_Inventory FOR UPDATE             │
│    │      (LOCK inventory row)                          │
│    │                                                    │
│    ├─ 4. IF stock < required → ABORT ✅                │
│    │      (Detect insufficient stock)                   │
│    │                                                    │
│    ├─ 5. UPDATE Blood_Inventory SET quantity -= units   │
│    │      (Deduct from stock)                           │
│    │                                                    │
│    ├─ 6. UPDATE Blood_Requests SET status = 'Approved'  │
│    │      (Mark as approved)                            │
│    │                                                    │
│    ├─ 7. INSERT INTO Transaction_Log {}                 │
│    │      (Audit trail)                                 │
│    │                                                    │
│    └─ COMMIT (All changes atomic)                       │
│                                                          │
│  Error Handling:                                         │
│    • DeadlockError: Retry transaction                   │
│    • LockTimeoutError: Return 408 Timeout               │
│    • InsufficientStockError: Return 400 Bad Request     │
│    • AlreadyProcessedError: Return 409 Conflict         │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│              MySQL Database (InnoDB)                     │
│  ✓ ISOLATION LEVEL = REPEATABLE READ                    │
│  ✓ Blood_Requests (row-level lock)                      │
│  ✓ Blood_Inventory (row-level lock)                     │
│  ✓ Transaction_Log (audit trail)                        │
└──────────────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│              HTTP Response (JSON)                         │
│                                                          │
│  Success (200):                                         │
│  {                                                       │
│    "success": true,                                      │
│    "message": "Request approved",                        │
│    "data": {                                             │
│      "request_id": 123,                                  │
│      "units": 10,                                        │
│      "new_stock": 25                                     │
│    }                                                     │
│  }                                                       │
│                                                          │
│  Error (409 Conflict):                                  │
│  {                                                       │
│    "success": false,                                     │
│    "error_type": "AlreadyProcessedError",               │
│    "message": "Request already Approved"                 │
│  }                                                       │
└──────────────────────────────────────────────────────────┘
```

---

## 2. Files Created

### Core Implementation Files

| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| `transaction_lock_handler.py` | 450+ | Transaction management with pessimistic locking | ✅ Ready |
| `transaction_routes.py` | 400+ | Flask HTTP endpoints for transaction operations | ✅ Ready |
| `transaction_schema.sql` | 600+ | Database schema with InnoDB transaction support | ✅ Ready |

### File Relationships

```
Files Dependency Graph:
=======================

app.py (main Flask app)
  │
  ├── imports: rbac.py (@permission_required decorator)
  │
  └── imports: transaction_routes.py (HTTP endpoints)
       │
       └── imports: transaction_lock_handler.py (transaction mgmt)
            │
            └── uses: mysql.connector (database)
                 │
                 └── operates on: Blood_Requests, Blood_Inventory tables
                      │
                      └── defined in: transaction_schema.sql
```

---

## 3. Database Setup

### Step 1: Create Tables

Run the transaction schema to create necessary tables:

```bash
# Using MySQL command line
mysql -u root -p blood_bank_db < transaction_schema.sql

# Or using Python
import mysql.connector
conn = mysql.connector.connect(host='localhost', user='root', password='jefrin', database='blood_bank_db')
cursor = conn.cursor()
with open('transaction_schema.sql', 'r') as f:
    for statement in f.read().split(';'):
        if statement.strip():
            cursor.execute(statement)
conn.commit()
cursor.close()
conn.close()
```

### Step 2: Verify Tables Created

```sql
-- Check transaction tables
SHOW TABLES LIKE '%Inventory%';
SHOW TABLES LIKE 'Blood_Requests';
SHOW TABLES LIKE 'Transaction_Log';

-- Output should show:
-- ├── Blood_Inventory ✓
-- ├── Blood_Requests ✓
-- ├── Transaction_Log ✓
-- └── Lock_Monitor ✓
```

### Step 3: Verify Table Structure

```sql
-- Check Blood_Inventory columns
DESC Blood_Inventory;
-- Expected columns:
-- blood_group (PRIMARY KEY, ENUM)
-- quantity_units INT
-- last_updated TIMESTAMP
-- critical_threshold INT

-- Check Blood_Requests columns  
DESC Blood_Requests;
-- Expected columns:
-- id (INT PRIMARY KEY AUTO_INCREMENT)
-- hospital_id INT
-- blood_group ENUM
-- units_required INT
-- status ENUM ('Pending', 'Approved', 'Rejected')
-- created_by INT
-- approved_by INT
-- approval_date DATETIME
-- rejection_reason TEXT
```

### Step 4: Initialize Blood Stock

```sql
-- Check initial stock
SELECT * FROM Blood_Inventory;

-- Output should show:
-- O+: 50 units
-- O-: 30 units
-- A+: 40 units
-- etc.

-- If empty, insert:
INSERT INTO Blood_Inventory (blood_group, quantity_units) VALUES
('O+', 50), ('O-', 30), ('A+', 40), ('A-', 20),
('B+', 35), ('B-', 15), ('AB+', 25), ('AB-', 10);
```

### Step 5: Verify InnoDB Engine

```sql
-- CRITICAL: Pessimistic locking requires InnoDB
SHOW CREATE TABLE Blood_Inventory\G
-- Look for: ENGINE=InnoDB

-- If using different engine, CONVERT:
ALTER TABLE Blood_Inventory ENGINE=InnoDB;
ALTER TABLE Blood_Requests ENGINE=InnoDB;
ALTER TABLE Blood_Inventory ENGINE=InnoDB;
```

**Why InnoDB?**
- ✅ Supports row-level locking (FOR UPDATE)
- ✅ Supports transactions (ACID)
- ❌ MyISAM: No locking, no transactions
- ❌ Memory: No durability

---

## 4. Code Integration into app.py

### Step 1: Update requirements.txt

The transaction system uses `mysql-connector-python`:

```bash
# Check if installed
pip list | grep mysql-connector

# Install if missing
pip install mysql-connector-python==8.0.33

# Or update requirements.txt
echo "mysql-connector-python==8.0.33" >> requirements.txt
pip install -r requirements.txt
```

### Step 2: Import Transaction Routes in app.py

Add at the **top** of `app.py` (after Flask imports):

```python
# ==================== IMPORTS ====================

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
import MySQLdb.cursors
import re
from functools import wraps

# Import RBAC system
from rbac import (
    permission_required, 
    role_required, 
    get_user_permissions,
    can_approve_blood_request,
    log_audit_event
)

# ✅ ADD THESE IMPORTS FOR TRANSACTIONS
from transaction_routes import register_transaction_routes
from transaction_lock_handler import approve_blood_request

# ==================== CONFIGURATION ====================

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
mysql = MySQL(app)

# ✅ REGISTER TRANSACTION ROUTES
register_transaction_routes(app)

# ==================== EXISTING ROUTES ====================
# (all your existing routes)

if __name__ == '__main__':
    app.run(debug=True)
```

### Step 3: Replace Old Request Approval Route

**BEFORE** (old request update without locking):

```python
@app.route('/requests/<int:id>/update_status', methods=['POST'])
@permission_required('request:approve')
def update_request_status(id):
    # OLD APPROACH (NO LOCKING - RACE CONDITIONS!)
    action = request.form.get('status')
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM Blood_Requests WHERE id = %s", (id,))
    req = cursor.fetchone()
    
    if action == 'approve':
        # Check stock WITHOUT LOCK (race condition!)
        cursor.execute("SELECT quantity FROM Blood_Inventory WHERE blood_group = %s", (req['blood_group'],))
        stock = cursor.fetchone()
        
        if stock['quantity'] < req['units']:
            return jsonify({'success': False, 'message': 'Insufficient stock'})
        
        # Two updates without atomicity (race condition!)
        cursor.execute("UPDATE Blood_Inventory SET quantity = quantity - %s WHERE blood_group = %s",
                      (req['units'], req['blood_group']))
        cursor.execute("UPDATE Blood_Requests SET status = 'Approved' WHERE id = %s", (id,))
    
    mysql.connection.commit()
    cursor.close()
    return jsonify({'success': True})
```

**AFTER** (new approach with transaction locking):

```python
# Remove the old route entirely!
# All blood request approval now goes through:
#   POST /api/requests/<id>/approve (newer endpoint with locking)
# Defined in transaction_routes.py and registered above
```

### Step 4: Add Convenience Endpoint (Optional)

If you want an endpoint similar to the old interface but with transaction safety:

```python
@app.route('/requests/<int:request_id>/update', methods=['POST'])
@permission_required('request:approve')
def update_request_safe(request_id):
    """
    Convenience endpoint for backward compatibility.
    Internally uses transaction locking.
    """
    user_id = session.get('user_id')
    action = request.form.get('status')  # 'approve' or 'reject'
    reason = request.form.get('reason', '')
    
    # Use transaction handler
    result = approve_blood_request(
        request_id=request_id,
        action=action,
        user_id=user_id,
        rejection_reason=reason if action == 'reject' else None
    )
    
    if result['success']:
        return jsonify({'success': True, 'message': result['message']})
    else:
        return jsonify({
            'success': False, 
            'message': result['message'],
            'error_type': result.get('error_type')
        }), result.get('status_code', 400)
```

### Step 5: Verify Integration

Check that app.py starts without errors:

```bash
# Start app
python app.py

# In another terminal, check routes
curl http://localhost:5000/api/requests/pending
# Should return JSON with list of pending requests
```

---

## 5. Testing the Implementation

### Test 1: Single Request Approval (Normal Case)

```python
# test_transaction_normal.py

import requests
import json

BASE_URL = 'http://localhost:5000'

# Log in as blood bank admin
session = requests.Session()
response = session.post(f'{BASE_URL}/login', data={
    'email': 'bank_admin@blood.local',
    'password': 'AdminPass123'
})
print(f"Login: {response.status_code}")

# Approve a request
response = session.post(f'{BASE_URL}/api/requests/1/approve')
result = response.json()

print(f"\nApprove Request 1:")
print(f"  Status: {response.status_code}")
print(f"  Success: {result['success']}")
print(f"  Message: {result['message']}")
if 'data' in result:
    print(f"  Blood Group: {result['data'].get('blood_group')}")
    print(f"  Units: {result['data'].get('units_approved')}")
    print(f"  New Stock: {result['data'].get('new_stock')}")

# Expected: 200 OK, success=true
```

**Run:**
```bash
python test_transaction_normal.py
```

### Test 2: Race Condition Test (Concurrent Approvals)

```python
# test_transaction_race.py

import requests
import threading
import time

BASE_URL = 'http://localhost:5000'

# Log in as two admins
admin1_session = requests.Session()
admin2_session = requests.Session()

admin1_session.post(f'{BASE_URL}/login', data={
    'email': 'admin1@blood.local',
    'password': 'AdminPass123'
})

admin2_session.post(f'{BASE_URL}/login', data={
    'email': 'admin2@blood.local',
    'password': 'AdminPass123'
})

# Target same request
REQUEST_ID = 2

results = {}

def approve_request(session_name, session):
    """Try to approve same request"""
    print(f"\n[{session_name}] Starting approval...")
    start = time.time()
    
    response = session.post(f'{BASE_URL}/api/requests/{REQUEST_ID}/approve')
    result = response.json()
    
    elapsed = time.time() - start
    results[session_name] = {
        'status_code': response.status_code,
        'success': result.get('success'),
        'error_type': result.get('error_type'),
        'timestamp': elapsed
    }
    
    print(f"[{session_name}] ({elapsed:.2f}s) → {result.get('error_type', 'Success')}")

# Launch concurrent requests
t1 = threading.Thread(target=approve_request, args=('Admin1', admin1_session))
t2 = threading.Thread(target=approve_request, args=('Admin2', admin2_session))

t1.start()
t2.start()

t1.join()
t2.join()

# Print results
print("\n" + "="*50)
print("RACE CONDITION TEST RESULTS:")
print("="*50)

approvals = sum(1 for r in results.values() if r['success'])
conflicts = sum(1 for r in results.values() if r['error_type'] == 'AlreadyProcessedError')

print(f"\nAdmin1: {results['Admin1']}")
print(f"Admin2: {results['Admin2']}")
print(f"\nSuccessful approvals: {approvals}")
print(f"Conflict errors: {conflicts}")

if approvals == 1 and conflicts == 1:
    print("\n✅ PASS: Pessimistic locking prevented double approval!")
else:
    print("\n❌ FAIL: Race condition detected!")
```

**Run:**
```bash
python test_transaction_race.py
```

**Expected Output:**
```
==================================================
RACE CONDITION TEST RESULTS:
==================================================

Admin1: {'status_code': 200, 'success': True, 'error_type': None, 'timestamp': 0.45}
Admin2: {'status_code': 409, 'success': False, 'error_type': 'AlreadyProcessedError', 'timestamp': 0.48}

Successful approvals: 1
Conflict errors: 1

✅ PASS: Pessimistic locking prevented double approval!
```

### Test 3: Insufficient Stock Test

```python
# test_transaction_stock.py

import requests

BASE_URL = 'http://localhost:5000'

session = requests.Session()
session.post(f'{BASE_URL}/login', data={
    'email': 'bank_admin@blood.local',
    'password': 'AdminPass123'
})

# Create request for more units than available
# (Assume AB- has only 10 units)
response = session.post(f'{BASE_URL}/api/requests/10/approve')
result = response.json()

if result['error_type'] == 'InsufficientStockError':
    print("✅ PASS: Insufficient stock detected correctly")
    print(f"   Requested: {result['data']['requested']}")
    print(f"   Available: {result['data']['available']}")
else:
    print(f"❌ FAIL: Expected InsufficientStockError, got {result['error_type']}")
```

### Test 4: Correct Blood Group Deduction

```python
# test_transaction_inventory.py

import mysql.connector

conn = mysql.connector.connect(
    host='localhost',
    user='root',
    password='jefrin',
    database='blood_bank_db'
)
cursor = conn.cursor(dictionary=True)

# Check initial stock
cursor.execute("SELECT quantity_units FROM Blood_Inventory WHERE blood_group = 'O+'")
before = cursor.fetchone()['quantity_units']

print(f"O+ Stock Before: {before} units")

# Approve request for 10 O+ units via HTTP request
# ... (make request) ...

# Check stock after
cursor.execute("SELECT quantity_units FROM Blood_Inventory WHERE blood_group = 'O+'")
after = cursor.fetchone()['quantity_units']

print(f"O+ Stock After: {after} units")
print(f"Deducted: {before - after} units")

if (before - after) == 10:
    print("✅ PASS: Correct amount deducted from inventory")
else:
    print(f"❌ FAIL: Expected 10 units deducted, got {before - after}")

cursor.close()
conn.close()
```

---

## 6. Recovery & Debugging

### Deadlock Recovery

**When you see**: `ERROR 1213: Deadlock found when trying to get a lock`

**Action**: Automatic retry is built in!

```python
# transaction_lock_handler.py has deadlock retry logic:
for attempt in range(max_retries):
    try:
        # Try transaction
        break
    except DeadlockError:
        if attempt < max_retries - 1:
            # Automatically retry
            continue
        else:
            raise
```

**Manual recovery**:

```bash
# Check for deadlocks
mysql> SHOW ENGINE INNODB STATUS\G
# Look for "LATEST DETECTED DEADLOCK" section

# Kill long-running transaction if stuck
SHOW PROCESSLIST;
KILL QUERY <process_id>;
```

### Lock Timeout Issues

**When you see**: `ERROR 1205: Lock wait timeout exceeded`

**Reason**: Another transaction held the lock too long (> lock_wait_timeout)

**Solutions**:

```sql
-- Increase lock wait timeout (default 50 seconds)
SET SESSION innodb_lock_wait_timeout = 120;  -- 2 minutes

-- Or global setting
SET GLOBAL innodb_lock_wait_timeout = 120;

-- Check current setting
SHOW VARIABLES LIKE 'innodb_lock_wait_timeout';
```

### Monitor Active Locks

```sql
-- See what locks are active
SELECT * FROM INFORMATION_SCHEMA.INNODB_LOCKS;

-- See what's waiting for locks
SELECT * FROM INFORMATION_SCHEMA.INNODB_LOCK_WAITS;

-- View our custom lock monitor
SELECT * FROM Lock_Monitor WHERE released_at IS NULL;  -- Active locks
SELECT * FROM Lock_Monitor WHERE duration_seconds > 5;  -- Long locks
```

### Debug Transaction Handler Logs

```python
# Add detailed logging in transaction_lock_handler.py

import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Then logs will show:
# DEBUG: Acquiring lock for request 123
# DEBUG: Lock acquired, checking stock
# DEBUG: Stock check passed: 50 >= 10
# DEBUG: Deducting 10 units
# DEBUG: Updating request status
# DEBUG: Transaction committed successfully
```

### Check Audit Trail

```sql
-- See all transaction operations
SELECT * FROM Transaction_Log ORDER BY initiated_at DESC LIMIT 10;

-- See failed attempts
SELECT * FROM Transaction_Log WHERE status = 'failed';

-- See approvals by admin
SELECT * FROM Transaction_Log
WHERE action = 'approve'
  AND initiated_by = <user_id>
  AND DATE(initiated_at) = CURDATE();
```

---

## 7. Performance Tuning

### Add Missing Indexes (Critical!)

```sql
-- These indexes speed up the FOR UPDATE lock acquisition
ALTER TABLE Blood_Requests ADD INDEX idx_status_blood (status, blood_group);
ALTER TABLE Blood_Inventory ADD INDEX idx_recheck (blood_group, quantity_units);

-- Verify indexes created
SHOW INDEXES FROM Blood_Requests;
SHOW INDEXES FROM Blood_Inventory;
```

### Monitor Lock Contention

```sql
-- Check for hot spots (frequently locked rows)
SELECT blood_group, COUNT(*) as lock_attempts
FROM Lock_Monitor
WHERE acquired_at > DATE_SUB(NOW(), INTERVAL 1 HOUR)
GROUP BY blood_group
ORDER BY lock_attempts DESC;

-- If one blood group heavily contended, consider:
-- 1. Investigating why (validation error?)
-- 2. Caching stock in memory
-- 3. Sharding by blood group
```

### Query Optimization

Before updating transaction_lock_handler.py for performance:

```python
# SLOW: No index for blood_group lookup
cursor.execute("""
    SELECT quantity_units FROM Blood_Inventory
    WHERE blood_group = %s FOR UPDATE
""", (blood_group,))

# FAST: With index on blood_group (PRIMARY KEY)
cursor.execute("""
    SELECT quantity_units FROM Blood_Inventory
    WHERE blood_group = %s FOR UPDATE
""", (blood_group,))
# Already fast because blood_group is PRIMARY KEY!
```

### Connection Pool Configuration

```python
# Set up connection pooling for better performance
import mysql.connector.pooling

dbconfig = {
    "host": "localhost",
    "user": "root",
    "password": "jefrin",
    "database": "blood_bank_db"
}

pool = mysql.connector.pooling.MySQLConnectionPool(
    pool_name="blood_bank_pool",
    pool_size=10,  # Number of connections to maintain
    **dbconfig
)

# Then reuse connections:
conn = pool.get_connection()
# ... use connection ...
conn.close()  # Returns to pool
```

---

## 8. Common Issues & Solutions

### Issue 1: "Deadlock found when trying to get a lock"

| Symptom | `ERROR 1213` in logs every few minutes |
|---------|---|
| Cause | Lock order inconsistent (requesting request then inventory in one transaction, inventory then request in another) |
| Solution | ALWAYS lock in same order: Request first, then Inventory |
| Verification | Review all code acquiring multiple locks, ensure order identical |

**Fix:**
```python
# WRONG - Different order in different functions
def approve():
    # Locks request first
    cursor.execute("SELECT ... FROM Blood_Requests FOR UPDATE")
    cursor.execute("SELECT ... FROM Blood_Inventory FOR UPDATE")

def reject():
    # Locks inventory first (DEADLOCK RISK!)
    cursor.execute("SELECT ... FROM Blood_Inventory FOR UPDATE")
    cursor.execute("SELECT ... FROM Blood_Requests FOR UPDATE")

# CORRECT - Same order everywhere
def approve():
    cursor.execute("SELECT ... FROM Blood_Requests FOR UPDATE")
    cursor.execute("SELECT ... FROM Blood_Inventory FOR UPDATE")

def reject():
    cursor.execute("SELECT ... FROM Blood_Requests FOR UPDATE")
    # Don't need inventory for reject, skip it
```

### Issue 2: "Lock wait timeout exceeded"

| Symptom | Transaction hangs for 50+ seconds, returns `ERROR 1205` |
|---------|---|
| Cause | Another transaction holding lock on same row, timeout expired |
| Solution | Increase timeout or investigate blocking transaction |
| Verification | `SHOW PROCESSLIST;` to find long-running queries |

**Fix:**
```sql
SET SESSION innodb_lock_wait_timeout = 120;  -- Increase to 2 minutes

-- Or find and kill blocking query
SHOW PROCESSLIST;
-- Look for row with high TIME value
KILL QUERY <process_id>;
```

### Issue 3: "Request not found" errors

| Symptom | Approving valid request IDs returns 404 |
|---------|---|
| Cause | Request created with wrong status or wrong table |
| Solution | Verify request exists in Blood_Requests table |
| Verification | `SELECT * FROM Blood_Requests WHERE id = <id>;` |

### Issue 4: Inventory goes negative

| Symptom | Blood stock shows negative units |
|---------|---|
| Cause | Race condition: stock check and deduction not atomic |
| Solution | Ensure pessimistic locking in place: FOR UPDATE on inventory |
| Verification | Review transaction_lock_handler.py FOR UPDATE on Blood_Inventory |

### Issue 5: App crashes on "mysql.connector.Error: No module named mysql"

| Symptom | ImportError when app starts |
|---------|---|
| Cause | mysql-connector-python not installed |
| Solution | `pip install mysql-connector-python==8.0.33` |
| Verification | `pip list | grep mysql-connector` should show 8.0.33 |

### Issue 6: Permissions deny approval (403 Forbidden)

| Symptom | Response: `403 Forbidden - Insufficient permissions` |
|---------|---|
| Cause | User missing 'request:approve' permission |
| Solution | Assign user to BLOOD_BANK_ADMIN role |
| Verification | Check Roles_Permissions table has `request:approve` for used role |

**Fix:**
```sql
-- Check user's role
SELECT ur.role_id FROM Users_RBAC u
JOIN User_Roles ur ON u.id = ur.user_id
WHERE u.id = <user_id>;

-- Check role has permission
SELECT p.permission_name FROM Permissions p
JOIN Role_Permissions rp ON p.id = rp.permission_id
WHERE rp.role_id = <role_id> AND p.permission_name = 'request:approve';

-- If missing, add:
INSERT INTO Role_Permissions (role_id, permission_id)
SELECT <role_id>, id FROM Permissions WHERE permission_name = 'request:approve';
```

---

## 9. Deployment Checklist

### Pre-Deployment

- [ ] **Database Backup**: `mysqldump -u root -p blood_bank_db > backup.sql`
- [ ] **Test Environment**: Run all 4 tests (normal, race condition, stock, inventory)
- [ ] **RBAC Setup**: Verify SUPER_ADMIN user exists with all permissions
- [ ] **Dependencies**: `pip install mysql-connector-python==8.0.33`
- [ ] **Import Verified**: `python -c "from transaction_lock_handler import approve_blood_request; print('OK')"`
- [ ] **Routes Verified**: `python -c "from transaction_routes import register_transaction_routes; print('OK')"`

### Deployment Steps

1. **Update requirements.txt**:
   ```bash
   echo "mysql-connector-python==8.0.33" >> requirements.txt
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run Database Schema**:
   ```bash
   mysql -u root -p blood_bank_db < transaction_schema.sql
   ```

4. **Copy Files**:
   ```bash
   cp transaction_lock_handler.py /path/to/blood_bank_app/
   cp transaction_routes.py /path/to/blood_bank_app/
   ```

5. **Update app.py**:
   - Add imports (see Section 4, Step 2)
   - Register transaction routes (see Section 4, Step 2)

6. **Test Start**:
   ```bash
   python app.py
   # Check no ImportError or other errors
   ```

7. **Smoke Tests**:
   ```bash
   # Test 1: List pending requests
   curl http://localhost:5000/api/requests/pending
   # Should return 200 JSON
   
   # Test 2: Try approval (may fail with auth, that's OK)
   curl -X POST http://localhost:5000/api/requests/1/approve
   # Should return 401 (not authenticated) - proves endpoint exists
   ```

8. **Full Test Suite**:
   ```bash
   python test_transaction_normal.py
   python test_transaction_race.py
   python test_transaction_stock.py
   ```

### Post-Deployment

- [ ] **Monitor Logs**: Watch app logs for transaction errors
- [ ] **Test Approvals**: Test with real admins approving real requests
- [ ] **Check Inventory**: Verify stock decreases correctly after approvals
- [ ] **Monitor Locks**: Query `Lock_Monitor` for contention issues
- [ ] **Verify Audit**: Check `Transaction_Log` for all operations
- [ ] **Set Alerts**: Alert on failed approvals or deadlocks

### Rollback Plan

If issues occur:

```bash
# 1. Stop app
# Ctrl+C on running app

# 2. Restore old routes in app.py
# Remove: from transaction_routes import register_transaction_routes
# Remove: register_transaction_routes(app)
# Restore old @app.route('/requests/<id>/update_status')

# 3. Restart with old code
python app.py

# 4. Database (if needed)
mysql -u root -p blood_bank_db < backup.sql
```

---

## Summary

You now have a **production-ready transaction locking system** with:

✅ **Pessimistic Locking**: Prevents race conditions on blood requests  
✅ **Row-Level Locks**: Only locks specific request/inventory, not entire table  
✅ **Atomic Transactions**: All-or-nothing updates across multiple tables  
✅ **ACID Compliance**: Ensures data consistency  
✅ **Error Handling**: Specific error types for deadlocks, timeouts, conflicts  
✅ **Audit Trail**: Every transaction logged  
✅ **RBAC Integration**: Works with existing permission system  
✅ **HTTP API**: RESTful endpoints for approvals  

**Key Files**:
- [transaction_lock_handler.py](transaction_lock_handler.py) - Core transaction logic
- [transaction_routes.py](transaction_routes.py) - HTTP endpoints
- [transaction_schema.sql](transaction_schema.sql) - Database tables

**Next Steps**:
1. Run database schema setup
2. Update app.py with imports and registration
3. Run test suite
4. Deploy to production
5. Monitor for issues

For issues or questions, check **Section 6: Recovery & Debugging**.
