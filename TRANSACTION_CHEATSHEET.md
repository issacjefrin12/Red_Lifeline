# TRANSACTION LOCKING - QUICK REFERENCE GUIDE

## Overview
Pessimistic locking prevents race conditions in blood request approvals using `SELECT...FOR UPDATE`.

---

## API Endpoints

### 1. Approve Blood Request
```
POST /api/requests/<request_id>/approve

Response (Success):
{
  "success": true,
  "message": "Request 123 approved successfully",
  "data": {
    "request_id": 123,
    "blood_group": "O+",
    "units_approved": 10,
    "new_stock": 25
  },
  "status_code": 200
}

Response (Already Approved):
{
  "success": false,
  "message": "Request already Approved",
  "error_type": "AlreadyProcessedError",
  "status_code": 409
}

Response (Insufficient Stock):
{
  "success": false,
  "message": "Insufficient O- blood. Available: 8, Required: 15",
  "error_type": "InsufficientStockError",
  "status_code": 400,
  "data": {
    "blood_group": "O-",
    "available": 8,
    "requested": 15
  }
}

Response (Lock Timeout):
{
  "success": false,
  "message": "Could not acquire database lock. Try again.",
  "error_type": "LockTimeoutError",
  "status_code": 408
}

Response (Deadlock):
{
  "success": false,
  "message": "Database deadlock. Request will be retried.",
  "error_type": "DeadlockError",
  "status_code": 409
}

Response (Unauthorized):
{
  "success": false,
  "message": "Conflict of interest: Cannot approve request from your hospital",
  "error_type": "ConflictOfInterest",
  "status_code": 403
}
```

### 2. Reject Blood Request
```
POST /api/requests/<request_id>/reject
Content-Type: application/json

Request Body:
{
  "reason": "Stock reserved for critical case"
}

Response (Success):
{
  "success": true,
  "message": "Request 123 rejected",
  "data": {
    "request_id": 123,
    "rejection_reason": "Stock reserved for critical case"
  },
  "status_code": 200
}
```

### 3. List Pending Requests
```
GET /api/requests/pending?blood_group=O+&hospital_id=1&limit=50&page=1

Response:
{
  "success": true,
  "message": "Retrieved 3 pending requests",
  "data": {
    "total": 3,
    "page": 1,
    "limit": 50,
    "requests": [
      {
        "request_id": 123,
        "hospital": "City Hospital",
        "blood_group": "O+",
        "units": 10,
        "approvability": "Can Approve",
        "available_stock": 25,
        "request_date": "2024-01-15T09:30:00"
      }
    ]
  },
  "status_code": 200
}
```

### 4. Bulk Approve Requests (Admin Only)
```
POST /api/requests/bulk-approve
Content-Type: application/json

Request Body:
{
  "request_ids": [123, 124, 125]
}

Response:
{
  "success": true,
  "message": "Approved 3 out of 3 requests",
  "data": {
    "approved": [123, 124, 125],
    "failed": [],
    "total_processed": 3,
    "success_count": 3,
    "failure_count": 0
  },
  "status_code": 200
}

Response (Partial Success):
{
  "success": true,
  "message": "Approved 2 out of 3 requests",
  "data": {
    "approved": [123, 124],
    "failed": [
      {
        "request_id": 125,
        "error": "Insufficient stock for B+"
      }
    ],
    "total_processed": 3,
    "success_count": 2,
    "failure_count": 1
  },
  "status_code": 207
}
```

---

## HTTP Status Codes

| Code | Meaning | Example Error |
|------|---------|---|
| 200 | ✅ Success | Approval went through |
| 207 | ⚠️ Partial Success | Bulk approval: some approved, some failed |
| 400 | ❌ Bad Request | Insufficient stock, invalid input |
| 401 | ❌ Unauthorized | Not logged in |
| 403 | ❌ Forbidden | Conflict of interest, insufficient permissions |
| 404 | ❌ Not Found | Request ID doesn't exist |
| 408 | ⏰ Timeout | Lock wait timeout (retry later) |
| 409 | ⚠️ Conflict | Already processed, deadlock (retry) |
| 500 | 💥 Server Error | Database connection failed, unexpected error |

---

## Error Types

```javascript
// InsufficientStockError
{
  "error_type": "InsufficientStockError",
  "status_code": 400,
  "data": {
    "blood_group": "AB-",
    "available": 5,
    "requested": 15
  }
}

// AlreadyProcessedError
{
  "error_type": "AlreadyProcessedError",
  "status_code": 409,
  "data": {
    "request_id": 123,
    "current_status": "Approved",
    "approved_by": 5,
    "approved_at": "2024-01-15T10:25:00"
  }
}

// LockTimeoutError
{
  "error_type": "LockTimeoutError",
  "status_code": 408
  // Data: Usually empty - just retry
}

// DeadlockError
{
  "error_type": "DeadlockError",
  "status_code": 409
  // Data: Usually empty - retry automatically
}

// ConflictOfInterest
{
  "error_type": "ConflictOfInterest",
  "status_code": 403
  // Cannot approve requests from user's own hospital
}
```

---

## Using cURL (Command Line)

```bash
# Login first to get session cookie
curl -c cookies.txt -d "email=admin@blood.local&password=pass" \
  http://localhost:5000/login

# Approve request (uses session cookies)
curl -b cookies.txt -X POST \
  http://localhost:5000/api/requests/1/approve

# With error handling
curl -b cookies.txt -X POST \
  http://localhost:5000/api/requests/1/approve \
  -H "Content-Type: application/json" \
  -w "\nStatus: %{http_code}\n"

# Reject with reason
curl -b cookies.txt -X POST \
  http://localhost:5000/api/requests/2/reject \
  -H "Content-Type: application/json" \
  -d '{"reason":"Reserved for critical cases"}'

# List pending requests
curl -b cookies.txt \
  "http://localhost:5000/api/requests/pending?blood_group=O%2B&limit=10"

# Bulk approve
curl -b cookies.txt -X POST \
  http://localhost:5000/api/requests/bulk-approve \
  -H "Content-Type: application/json" \
  -d '{"request_ids":[1,2,3]}'
```

---

## Using Python (Requests Library)

```python
import requests

BASE_URL = 'http://localhost:5000'
session = requests.Session()

# Login
session.post(f'{BASE_URL}/login', data={
    'email': 'admin@blood.local',
    'password': 'password123'
})

# Approve request
response = session.post(f'{BASE_URL}/api/requests/1/approve')
if response.status_code == 200:
    print(f"✅ Approved! New stock: {response.json()['data']['new_stock']}")
elif response.status_code == 400:
    print(f"❌ Insufficient stock: {response.json()['data']}")
elif response.status_code == 409:
    print(f"⚠️ Already processed: {response.json()['message']}")

# Reject request
response = session.post(
    f'{BASE_URL}/api/requests/2/reject',
    json={'reason': 'Reserved for emergency'}
)
print(response.json())

# List pending
response = session.get(f'{BASE_URL}/api/requests/pending')
pending = response.json()['data']['requests']
for req in pending:
    print(f"Request {req['request_id']}: {req['units']} units of {req['blood_group']}")

# Bulk approve
response = session.post(
    f'{BASE_URL}/api/requests/bulk-approve',
    json={'request_ids': [1, 2, 3, 4, 5]}
)
result = response.json()['data']
print(f"Approved: {result['success_count']}, Failed: {result['failure_count']}")
```

---

## Using JavaScript/Fetch

```javascript
const BASE_URL = 'http://localhost:5000';

// Login
await fetch(`${BASE_URL}/login`, {
  method: 'POST',
  credentials: 'include',  // Include cookies
  body: new FormData({
    email: 'admin@blood.local',
    password: 'password123'
  })
});

// Approve request
const response = await fetch(`${BASE_URL}/api/requests/1/approve`, {
  method: 'POST',
  credentials: 'include'
});

const data = await response.json();

if (data.success) {
  console.log(`✅ Approved! New stock: ${data.data.new_stock}`);
} else if (data.error_type === 'InsufficientStockError') {
  console.log(`❌ Stock: ${data.data.available} available, ${data.data.requested} needed`);
} else if (data.error_type === 'AlreadyProcessedError') {
  console.log(`⚠️ Already ${data.data.current_status}`);
} else if (data.error_type === 'LockTimeoutError') {
  console.log('⏰ Try again (another operation is in progress)');
}

// Reject request
const rejectResponse = await fetch(`${BASE_URL}/api/requests/2/reject`, {
  method: 'POST',
  credentials: 'include',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ reason: 'Reserved for emergency' })
});

const rejectData = await rejectResponse.json();
console.log(rejectData);

// List pending
const listResponse = await fetch(`${BASE_URL}/api/requests/pending`, {
  credentials: 'include'
});
const pendingData = await listResponse.json();
pendingData.data.requests.forEach(req => {
  console.log(`${req.request_id}: ${req.units}U of ${req.blood_group}`);
});
```

---

## Permissions Required

| Action | Permission | Role(s) |
|--------|-----------|---------|
| Approve Request | `request:approve` | BLOOD_BANK_ADMIN, SUPER_ADMIN |
| Reject Request | `request:reject` | BLOOD_BANK_ADMIN, SUPER_ADMIN |
| View Pending | `request:view` | All authenticated users |
| Bulk Approve | `admin:manage` | SUPER_ADMIN only |

---

## Common Scenarios

### Scenario 1: Approve a Single Request

```python
# Check current state
SELECT * FROM Blood_Requests WHERE id = 123;
# Status: Pending, blood_group: O+, units_required: 10

SELECT quantity_units FROM Blood_Inventory WHERE blood_group = 'O+';
# quantity_units: 50

# Approve via API
POST /api/requests/123/approve
# ✅ Success

# Check after
SELECT * FROM Blood_Requests WHERE id = 123;
# Status: Approved, approved_by: 5, approval_date: 2024-01-15 10:30:45

SELECT quantity_units FROM Blood_Inventory WHERE blood_group = 'O+';
# quantity_units: 40  (50 - 10 = 40)
```

### Scenario 2: Prevent Double Approval

```python
# Admin A approves request 123
POST /api/requests/123/approve (from User 2)
# ✅ Success: Status → Approved

# Admin B tries to approve same request (simultaneously)
POST /api/requests/123/approve (from User 3)
# ❌ Error: AlreadyProcessedError (Status is already Approved)
# Stock NOT deducted twice!
```

### Scenario 3: Handle Insufficient Stock

```python
# Current stock: A- has 8 units
SELECT quantity_units FROM Blood_Inventory WHERE blood_group = 'A-';
# 8

# Try to approve request for 15 A- units
POST /api/requests/456/approve
# ❌ Error: InsufficientStockError
# - Available: 8
# - Requested: 15
# Status remains Pending, no changes made
```

### Scenario 4: Detect Conflict of Interest

```python
# Hospital User from City Hospital tries to approve request for City Hospital
POST /api/requests/789/approve (User from City Hospital)
# ❌ Error: ConflictOfInterest
# Message: Cannot approve request from your own hospital
# Only Blood Bank Admin can approve (not hospital staff)
```

### Scenario 5: Retry After Lock Timeout

```python
# First attempt - lock is locked by another transaction
POST /api/requests/999/approve
# ⏰ Status 408: LockTimeoutError
# Message: "Could not acquire database lock. Try again."

# Wait a moment, retry
# (Other transaction released lock)
POST /api/requests/999/approve
# ✅ Success
```

---

## Database Queries (SQL)

```sql
-- View all pending requests
SELECT * FROM Blood_Requests WHERE status = 'Pending';

-- View current stock levels
SELECT * FROM v_blood_stock;

-- View approval history
SELECT br.id, br.blood_group, br.units_required,
       br.status, br.approval_date, u.name as approved_by
FROM Blood_Requests br
LEFT JOIN Users_RBAC u ON br.approved_by = u.id
WHERE br.status IN ('Approved', 'Rejected')
ORDER BY br.approval_date DESC
LIMIT 20;

-- View failed transaction attempts
SELECT request_id, error_message, initiated_at
FROM Transaction_Log
WHERE status = 'failed'
ORDER BY initiated_at DESC;

-- Check for active locks (deadlock debugging)
SELECT * FROM Lock_Monitor
WHERE released_at IS NULL;  -- Active locks only

-- Inventory audit trail
SELECT blood_group, previous_stock, new_stock, 
       (previous_stock - new_stock) as deducted,
       initiated_at
FROM Transaction_Log
WHERE action = 'approve'
ORDER BY initiated_at DESC;
```

---

## Performance Tips

```python
# ✅ GOOD: Specific request lookup
SELECT br.id, br.status FROM Blood_Requests 
WHERE id = 123 FOR UPDATE;

# ❌ SLOW: Full table scan
SELECT br.id, br.status FROM Blood_Requests FOR UPDATE;

# ✅ GOOD: Batch operations
POST /api/requests/bulk-approve
{
  "request_ids": [1, 2, 3, 4, 5]
}

# ❌ SLOW: Individual requests
POST /api/requests/1/approve
POST /api/requests/2/approve
POST /api/requests/3/approve
POST /api/requests/4/approve
POST /api/requests/5/approve

# ✅ GOOD: Indexed filter
SELECT * FROM Blood_Requests 
WHERE status = 'Pending'  -- indexed
AND blood_group = 'O+'    -- indexed
FOR UPDATE;

# ❌ SLOW: Unindexed filter
SELECT * FROM Blood_Requests 
WHERE rejection_reason LIKE '%emergency%'  -- not indexed
FOR UPDATE;
```

---

## Troubleshooting

| Issue | Symptom | Solution |
|-------|---------|----------|
| All approvals fail with 409 | "Database deadlock" on every attempt | Check lock ordering - may have circular wait |
| Approvals timeout (408) | Requests hang > 50 seconds | Another transaction holding lock too long; check PROCESSLIST |
| Inventory negative | SELECT shows negative units | Race condition (shouldn't happen with FOR UPDATE) |
| Permission denied (403) | Can't approve even as admin | User missing `request:approve` permission; check Roles_Permissions |
| Request not found (404) | Request ID always returns 404 | Request doesn't exist or wrong database |
| Stock not deducted | Approval succeeds but inventory unchanged | Probably using old code without FOR UPDATE |

---

## Files & Modules

```
transaction_lock_handler.py (450+ lines)
├── BloodRequestApprovalHandler (main class)
├── approve_blood_request() (entry point)
├── approve_multiple_requests() (bulk operations)
├── Custom Exceptions:
│   ├── InvalidRequestError
│   ├── InsufficientStockError
│   ├── AlreadyProcessedError
│   ├── DeadlockError
│   └── LockTimeoutError
└── Internal methods:
    ├── _fetch_request_with_lock()
    ├── _process_approval()
    ├── _process_rejection()
    ├── _handle_database_error()
    ├── _error_response()
    ├── _cleanup()
    └── _log_transaction()

transaction_routes.py (400+ lines)
├── Blueprint: transaction_bp
├── Routes:
│   ├── POST /api/requests/<id>/approve
│   ├── POST /api/requests/<id>/reject
│   ├── GET /api/requests/pending
│   └── POST /api/requests/bulk-approve
├── Helpers:
│   ├── get_current_user_id()
│   ├── format_response()
│   └── register_transaction_routes(app)
└── Error handlers:
    ├── @errorhandler(401)
    ├── @errorhandler(403)
    ├── @errorhandler(404)
    └── @errorhandler(500)

transaction_schema.sql (600+ lines)
├── Blood_Inventory table (InnoDB)
├── Blood_Requests table (InnoDB)
├── Transaction_Log table
├── Lock_Monitor table
├── Stored procedures:
│   └── approve_blood_request_transaction()
└── Views:
    ├── v_blood_stock
    ├── v_pending_requests
    └── v_lock_contention
```

---

## Integration Checklist

- [ ] Database schema created (`transaction_schema.sql`)
- [ ] `transaction_lock_handler.py` copied to project
- [ ] `transaction_routes.py` copied to project
- [ ] `app.py` updated with imports
- [ ] Transaction routes registered in `app.py`
- [ ] `requirements.txt` updated with `mysql-connector-python==8.0.33`
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] App starts without ImportError: `python app.py`
- [ ] Endpoints respond: `curl http://localhost:5000/api/requests/pending`
- [ ] Single approval test passes
- [ ] Race condition test shows one success, one conflict
- [ ] Stock deduction verified in database

---

## Support

For detailed setup: See [TRANSACTION_INTEGRATION_GUIDE.md](TRANSACTION_INTEGRATION_GUIDE.md)

For architecture details: See [transaction_lock_handler.py](transaction_lock_handler.py)

For HTTP endpoint specs: See [transaction_routes.py](transaction_routes.py)

For database schema: See [transaction_schema.sql](transaction_schema.sql)
