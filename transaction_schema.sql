-- ========================================
-- BLOOD BANK - TRANSACTION & LOCKING SUPPORT
-- Pessimistic Locking for Race Condition Prevention
-- ========================================

/**
TRANSACTION PHILOSOPHY
======================

This schema is designed for PESSIMISTIC LOCKING:

┌────────────────────────────────────────────────────┐
│ PESSIMISTIC LOCKING (SELECT ... FOR UPDATE)        │
├────────────────────────────────────────────────────┤
│ ✅ Assume conflicts WILL happen                    │
│ ✅ Lock rows BEFORE reading                        │
│ ✅ Other transactions WAIT for lock                │
│ ✅ No race conditions possible                     │
│ ✅ Best for: Blood banks (critical operations)    │
│ ⚠️ Risk: Deadlocks if lock order inconsistent     │
│ ⚠️ Cost: Lock overhead                            │
└────────────────────────────────────────────────────┘

ALTERNATIVE: Optimistic Locking
├─ Read without lock
├─ Check version at commit
├─ Retry if conflict
└─ NOT RECOMMENDED for blood inventory

WHY PESSIMISTIC FOR BLOOD BANKS?
=================================
1. Critical Data: Over-allocation could harm patients
2. High Contention: Multiple admins approving simultaneously
3. Small Dataset: 8 blood groups (minimal performance impact)
4. Consistency: Cannot afford to retry on conflicts
*/

USE blood_bank_db;

-- ==================== ISOLATION LEVEL ====================

/**
Set REPEATABLE READ isolation level for transactions
This prevents:
- Dirty reads (reading uncommitted data)
- Non-repeatable reads (data changing between reads)
- But allows phantom reads (acceptable for blood bank)
*/
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;

-- ==================== BLOOD_INVENTORY TABLE ====================

CREATE TABLE IF NOT EXISTS Blood_Inventory (
    blood_group ENUM('O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-') PRIMARY KEY,
    quantity_units INT DEFAULT 0 CHECK (quantity_units >= 0),
    
    -- LOCKING SUPPORT: Version/timestamp for deadlock detection
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- Metadata
    critical_threshold INT DEFAULT 5,  -- Alert if below this
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes for performance
    INDEX idx_low_stock (quantity_units),
    INDEX idx_last_updated (last_updated)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

/**
WHY ENGINE=InnoDB?
===================
- ✅ Supports row-level locking (critical for FOR UPDATE)
- ✅ Supports transactions
- ✅ ACID compliance
- ❌ MyISAM does NOT support locking or transactions
- ❌ MyISAM does NOT support FOR UPDATE clause

Blood banks MUST use InnoDB or similar (PostgreSQL, etc)
*/

-- ==================== BLOOD_REQUESTS TABLE ====================

CREATE TABLE IF NOT EXISTS Blood_Requests (
    id INT PRIMARY KEY AUTO_INCREMENT,
    hospital_id INT NOT NULL,
    blood_group ENUM('O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-') NOT NULL,
    units_required INT NOT NULL CHECK (units_required > 0),
    
    -- STATUS FIELD: Critical for preventing double approval
    status ENUM('Pending', 'Approved', 'Rejected') DEFAULT 'Pending',
    
    -- TIMESTAMPS
    request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approval_date DATETIME,  -- Set when approved/rejected
    
    -- AUDIT FIELDS
    created_by INT,
    approved_by INT,
    rejection_reason TEXT,
    
    -- Foreign keys
    FOREIGN KEY (hospital_id) REFERENCES Hospitals(id) ON DELETE CASCADE,
    FOREIGN KEY (blood_group) REFERENCES Blood_Inventory(blood_group),
    FOREIGN KEY (created_by) REFERENCES Users_RBAC(id) ON DELETE SET NULL,
    FOREIGN KEY (approved_by) REFERENCES Users_RBAC(id) ON DELETE SET NULL,
    
    -- Indexes for transaction queries
    INDEX idx_status (status),      -- Fast filter by status
    INDEX idx_hospital (hospital_id),
    INDEX idx_blood_group (blood_group),
    INDEX idx_request_date (request_date),
    INDEX idx_approval_date (approval_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

/**
STATUS FIELD EXPLANATION
=========================
Pending  → Original state
Approved → Units deducted, FINAL state
Rejected → Denied, FINAL state

DOUBLE APPROVAL PREVENTION:
In transaction, we check:
    IF status != 'Pending' THEN ABORT ✅

This prevents:
- Admin A and B both looking at 'Pending'
- Admin A locks row, approves
- Admin B still sees 'Pending' (old data)
- Admin B tries to approve → Detection!
*/

-- ==================== DONATIONS TABLE ====================

CREATE TABLE IF NOT EXISTS Donations (
    id INT PRIMARY KEY AUTO_INCREMENT,
    donor_id INT NOT NULL,
    units INT NOT NULL CHECK (units > 0),
    donation_date DATE NOT NULL,
    blood_group ENUM('O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-') NOT NULL,
    health_status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (donor_id) REFERENCES Donors(id) ON DELETE CASCADE,
    FOREIGN KEY (blood_group) REFERENCES Blood_Inventory(blood_group),
    
    INDEX idx_donor (donor_id),
    INDEX idx_donation_date (donation_date),
    INDEX idx_blood_group (blood_group)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==================== DONORS TABLE ====================

CREATE TABLE IF NOT EXISTS Donors (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    age INT NOT NULL CHECK (age >= 18),
    gender ENUM('Male', 'Female', 'Other') NOT NULL,
    blood_group ENUM('O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-') NOT NULL,
    phone VARCHAR(15) UNIQUE NOT NULL,
    last_donation_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM('Active', 'Inactive') DEFAULT 'Active',
    
    INDEX idx_phone (phone),
    INDEX idx_blood_group (blood_group),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==================== HOSPITALS TABLE ====================

CREATE TABLE IF NOT EXISTS Hospitals (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL,
    contact VARCHAR(15) NOT NULL,
    address VARCHAR(255) NOT NULL,
    email VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==================== TRANSACTION LOCK TRACKING ====================

/**
Optional: Monitor active locks (for debugging)
*/
CREATE TABLE IF NOT EXISTS Lock_Monitor (
    id INT PRIMARY KEY AUTO_INCREMENT,
    request_id INT,
    thread_id INT,
    lock_type VARCHAR(50),  -- FOR UPDATE, etc
    acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    released_at TIMESTAMP NULL,
    duration_seconds INT GENERATED ALWAYS AS (
        CASE 
            WHEN released_at IS NULL THEN TIMESTAMPDIFF(SECOND, acquired_at, NOW())
            ELSE TIMESTAMPDIFF(SECOND, acquired_at, released_at)
        END
    ) STORED,
    
    INDEX idx_request_id (request_id),
    INDEX idx_acquired_at (acquired_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==================== INITIALIZE BLOOD_INVENTORY ====================

INSERT IGNORE INTO Blood_Inventory (blood_group, quantity_units, critical_threshold)
VALUES
('O+', 50, 5),
('O-', 30, 5),
('A+', 40, 4),
('A-', 20, 3),
('B+', 35, 4),
('B-', 15, 3),
('AB+', 25, 3),
('AB-', 10, 2);

-- ==================== STORED PROCEDURES FOR TRANSACTIONS ====================

/**
STORED PROCEDURE: Approve Blood Request with Locks
===================================================
Alternative to application-level transaction handling

Usage: CALL approve_blood_request_transaction(request_id, user_id)

Returns:
- 0: Success
- 1: Insufficient stock
- 2: Already processed
- 3: Request not found
*/

DELIMITER //

CREATE PROCEDURE IF NOT EXISTS approve_blood_request_transaction(
    IN p_request_id INT,
    IN p_user_id INT,
    OUT p_status INT,
    OUT p_message VARCHAR(255)
)
MODIFIES SQL DATA
BEGIN
    DECLARE v_hospital_id INT;
    DECLARE v_blood_group VARCHAR(10);
    DECLARE v_units_required INT;
    DECLARE v_request_status VARCHAR(20);
    DECLARE v_available_units INT;
    DECLARE p_error_code INT DEFAULT 0;
    
    -- Declare handlers for error conditions
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET p_status = 3;
        SET p_message = 'Transaction failed - rolled back';
    END;
    
    -- Start transaction
    START TRANSACTION;
    
    -- Step 1: FETCH REQUEST with lock
    SELECT 
        hospital_id, blood_group, units_required, status
    INTO 
        v_hospital_id, v_blood_group, v_units_required, v_request_status
    FROM Blood_Requests
    WHERE id = p_request_id
    FOR UPDATE;  -- PESSIMISTIC LOCK
    
    -- Check if request exists
    IF v_hospital_id IS NULL THEN
        ROLLBACK;
        SET p_status = 3;
        SET p_message = CONCAT('Request ', p_request_id, ' not found');
        LEAVE;
    END IF;
    
    -- Step 2: Verify status is still Pending
    IF v_request_status != 'Pending' THEN
        ROLLBACK;
        SET p_status = 2;
        SET p_message = CONCAT('Request already ', v_request_status);
        LEAVE;
    END IF;
    
    -- Step 3: LOCK INVENTORY and check stock
    SELECT quantity_units INTO v_available_units
    FROM Blood_Inventory
    WHERE blood_group = v_blood_group
    FOR UPDATE;  -- PESSIMISTIC LOCK
    
    IF v_available_units < v_units_required THEN
        ROLLBACK;
        SET p_status = 1;
        SET p_message = CONCAT('Insufficient stock: ', v_available_units, 
                               ' available, ', v_units_required, ' required');
        LEAVE;
    END IF;
    
    -- Step 4: DEDUCT FROM INVENTORY
    UPDATE Blood_Inventory
    SET quantity_units = quantity_units - v_units_required
    WHERE blood_group = v_blood_group;
    
    -- Step 5: UPDATE REQUEST STATUS
    UPDATE Blood_Requests
    SET 
        status = 'Approved',
        approval_date = NOW(),
        approved_by = p_user_id
    WHERE id = p_request_id;
    
    -- Success
    COMMIT;
    SET p_status = 0;
    SET p_message = CONCAT('Request ', p_request_id, ' approved. ', 
                           v_units_required, ' units of ', v_blood_group, 
                           ' deducted from inventory');

END //

DELIMITER ;

-- ==================== VIEWS FOR MONITORING ====================

/**
View: Available Blood Stock
Useful for dashboards and reports
*/
CREATE OR REPLACE VIEW v_blood_stock AS
SELECT 
    blood_group,
    quantity_units,
    critical_threshold,
    CASE 
        WHEN quantity_units < critical_threshold THEN 'Critical'
        WHEN quantity_units < critical_threshold * 2 THEN 'Low'
        ELSE 'Adequate'
    END AS stock_status,
    last_updated
FROM Blood_Inventory
ORDER BY blood_group;

/**
View: Pending Requests
Shows requests waiting for approval
*/
CREATE OR REPLACE VIEW v_pending_requests AS
SELECT 
    br.id,
    br.hospital_id,
    h.name as hospital_name,
    br.blood_group,
    br.units_required,
    bi.quantity_units as available_stock,
    CASE 
        WHEN bi.quantity_units >= br.units_required THEN 'Can Approve'
        ELSE 'Insufficient Stock'
    END as approvability,
    br.request_date,
    br.created_by
FROM Blood_Requests br
JOIN Hospitals h ON br.hospital_id = h.id
LEFT JOIN Blood_Inventory bi ON br.blood_group = bi.blood_group
WHERE br.status = 'Pending'
ORDER BY br.request_date ASC;

/**
View: Lock Contention Analysis
For monitoring deadlock/timeout issues
*/
CREATE OR REPLACE VIEW v_lock_contention AS
SELECT 
    request_id,
    COUNT(*) as total_lock_attempts,
    AVG(duration_seconds) as avg_lock_duration,
    MAX(duration_seconds) as max_lock_duration,
    SUM(CASE WHEN released_at IS NULL THEN 1 ELSE 0 END) as active_locks
FROM Lock_Monitor
WHERE acquired_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY request_id
ORDER BY total_lock_attempts DESC;

-- ==================== DEADLOCK PREVENTION CONFIGURATION ====================

/**
Lock Acquisition Order (CRITICAL!)
===================================
To prevent deadlocks, ALWAYS acquire locks in same order:

CORRECT:
1. Lock Blood_Requests (requesting row)
2. Lock Blood_Inventory (blood group row)

WRONG:
1. Lock Blood_Inventory
2. Lock Blood_Requests
(Different order = risk of circular wait = DEADLOCK)

All procedures/code must follow CORRECT order
*/

-- ==================== TRANSACTION LOG ====================

CREATE TABLE IF NOT EXISTS Transaction_Log (
    id INT PRIMARY KEY AUTO_INCREMENT,
    request_id INT,
    action VARCHAR(50),
    status VARCHAR(20),
    blood_group VARCHAR(10),
    units_involved INT,
    previous_stock INT,
    new_stock INT,
    error_message TEXT,
    initiated_by INT,
    initiated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    
    FOREIGN KEY (request_id) REFERENCES Blood_Requests(id) ON DELETE CASCADE,
    FOREIGN KEY (initiated_by) REFERENCES Users_RBAC(id) ON DELETE SET NULL,
    
    INDEX idx_request_id (request_id),
    INDEX idx_status (status),
    INDEX idx_initiated_at (initiated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==================== PERFORMANCE TUNING ====================

/**
QUERY HINTS FOR TRANSACTION QUERIES
====================================

Fast path for common operations:

-- Fast: Uses index on status
SELECT * FROM Blood_Requests WHERE status = 'Pending' AND id = 123 FOR UPDATE;

-- Slow: Full table scan
SELECT * FROM Blood_Requests FOR UPDATE;

-- Use LIMIT with FOR UPDATE to minimize lock scope
SELECT * FROM Blood_Requests WHERE status = 'Pending' 
FOR UPDATE LIMIT 100;

Index strategy:
- status: Fast filtering of pending requests
- blood_group: Fast lookup in inventory
- request_id: Primary key for FOR UPDATE
*/

-- ==================== VERIFICATION QUERIES ====================

-- Check transaction isolation level
-- SHOW VARIABLES LIKE 'transaction_isolation';

-- List current locks
-- SHOW ENGINE INNODB STATUS;

-- Check for deadlocks in last hour
-- SELECT * FROM Lock_Monitor WHERE acquired_at > DATE_SUB(NOW(), INTERVAL 1 HOUR);

-- View current pending requests
-- SELECT * FROM v_pending_requests;

-- View blood stock status
-- SELECT * FROM v_blood_stock;
