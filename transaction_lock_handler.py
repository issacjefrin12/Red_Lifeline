"""
Blood Bank Management System - Transaction Lock Handler
Purpose: Handle blood request approvals with Database Transactions and Pessimistic Locking
Author: Database Security Team
Version: 1.0.0

This module implements row-level locking (SELECT ... FOR UPDATE) to prevent:
- Double approval of the same request
- Race conditions when checking inventory
- Over-allocation of limited blood stock
- Concurrent modification conflicts
"""

import mysql.connector
from mysql.connector import Error, errorcode
from datetime import datetime
import json
import logging
import os
from typing import Tuple, Optional, Dict, Any
from enum import Enum
from db_config import get_db_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== CUSTOM EXCEPTIONS ====================

class InsufficientStockError(Exception):
    """Raised when blood inventory is insufficient for the request"""
    def __init__(self, blood_group: str, available: int, requested: int):
        self.blood_group = blood_group
        self.available = available
        self.requested = requested
        self.message = f"Insufficient stock: {available} available, {requested} requested for {blood_group}"
        super().__init__(self.message)


class AlreadyProcessedError(Exception):
    """Raised when request has already been approved or rejected"""
    def __init__(self, request_id: int, current_status: str):
        self.request_id = request_id
        self.current_status = current_status
        self.message = f"Request {request_id} is already {current_status}"
        super().__init__(self.message)


class DeadlockError(Exception):
    """Raised when database deadlock is detected"""
    def __init__(self, original_error: str):
        self.message = f"Database deadlock detected: {original_error}"
        super().__init__(self.message)


class LockTimeoutError(Exception):
    """Raised when row lock acquisition times out"""
    def __init__(self, original_error: str):
        self.message = f"Lock timeout: {original_error}"
        super().__init__(self.message)


class TransactionError(Exception):
    """Generic transaction error wrapper"""
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


# ==================== APPROVAL STATUS ENUM ====================

class ApprovalAction(Enum):
    """Enum for approval actions"""
    APPROVE = "Approved"
    REJECT = "Rejected"


# ==================== DATABASE CONFIGURATION ====================

DB_CONFIG = {
    **get_db_config(),
    'autocommit': False,  # Critical: Must be False for transaction control
    'use_pure': True,     # Use pure Python implementation
}

LOCK_TIMEOUT = 5  # Seconds to wait for row lock


def get_connection():
    """
    Create database connection with explicit transaction control
    
    Why autocommit=False:
    - Allows us to START TRANSACTION explicitly
    - Enables us to ROLLBACK on errors
    - Ensures data consistency
    """
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Error as e:
        logger.error(f"Failed to connect to database: {e}")
        raise


# ==================== PESSIMISTIC LOCKING HANDLER ====================

class BloodRequestApprovalHandler:
    """
    Handle blood request approvals with pessimistic locking
    
    WHY PESSIMISTIC LOCKING?
    ========================
    Pessimistic locking (SELECT ... FOR UPDATE) is better than optimistic locking here because:
    
    1. HIGH CONTENTION: Blood requests are frequently accessed/modified
       - Multiple admins may try to approve simultaneously
       - Better to lock early than detect conflicts late
    
    2. CRITICAL OPERATIONS: Over-allocation could harm patients
       - Cannot afford to retry transactions
       - Must guarantee atomicity
    
    3. SMALL DATASETS: Blood groups table is small (8 rows)
       - Lock contention is minimal
       - Lock wait time is negligible
    
    COMPARISON:
    ┌─────────────────────┬─────────────────────┬──────────────────────┐
    │ Feature             │ Pessimistic Lock    │ Optimistic Lock      │
    ├─────────────────────┼─────────────────────┼──────────────────────┤
    │ Lock Strategy       │ Lock before read    │ Lock at commit       │
    │ High Contention     │ Better              │ Worse (many retries) │
    │ Small Datasets      │ Ideal               │ OK                   │
    │ Critical Data       │ Safer               │ Risky                │
    │ Deadlock Risk       │ Possible            │ No                   │
    ├─────────────────────┼─────────────────────┼──────────────────────┤
    │ Blood Banks         │ ✅ RECOMMENDED      │ ❌ Not ideal         │
    └─────────────────────┴─────────────────────┴──────────────────────┘
    """
    
    def __init__(self):
        self.conn: Optional[mysql.connector.MySQLConnection] = None
        self.cursor = None
    
    def approve_request(
        self,
        request_id: int,
        action: ApprovalAction = ApprovalAction.APPROVE,
        user_id: int = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Approve or reject a blood request with full transaction safety
        
        Transaction Sequence:
        1. START TRANSACTION
        2. SELECT ... FOR UPDATE on blood_batches (LOCK ROWS)
        3. SELECT on blood_requests to verify status (ALREADY LOCKED)
        4. Check: Is quantity_units >= units_required?
        5. UPDATE blood_batches (deduct units)
        6. UPDATE blood_requests (change status)
        7. INSERT audit log
        8. COMMIT (releases locks)
        
        If any step fails:
        - ROLLBACK entire transaction
        - Release all locks
        - Return error with specific reason
        
        Args:
            request_id: The blood request ID to approve
            action: ApprovalAction.APPROVE or ApprovalAction.REJECT
            user_id: Who is approving (for audit)
        
        Returns:
            (success: bool, result: dict)
            
            Success example:
            {
                'success': True,
                'request_id': 123,
                'action': 'Approved',
                'blood_group': 'O+',
                'units_deducted': 5,
                'previous_stock': 50,
                'new_stock': 45,
                'timestamp': '2026-02-17 14:30:00',
                'message': 'Request approved successfully'
            }
            
            Error example:
            {
                'success': False,
                'error': 'Insufficient stock',
                'details': {
                    'blood_group': 'O+',
                    'available': 3,
                    'requested': 5
                },
                'timestamp': '2026-02-17 14:30:00'
            }
        """
        self.conn = None
        self.cursor = None
        
        try:
            # Step 1: Establish connection
            self.conn = get_connection()
            self.cursor = self.conn.cursor(dictionary=True)
            
            # Step 2: START TRANSACTION (explicit for clarity)
            self.cursor.execute("START TRANSACTION")
            logger.info(f"Transaction started for request_id={request_id}")
            
            # Step 3: FETCH REQUEST with FOR UPDATE (pessimistic lock)
            # The FOR UPDATE clause locks this row until transaction commits
            # This prevents another transaction from modifying it concurrently
            request_data = self._fetch_request_with_lock(request_id)
            
            # Step 4: VERIFY REQUEST STATUS (prevent double approval)
            self._verify_request_pending(request_data, request_id)
            
            # Step 5: APPROVE or REJECT
            if action == ApprovalAction.APPROVE:
                result = self._process_approval(request_data, user_id)
            else:
                result = self._process_rejection(request_data, user_id)
            
            # Step 6: COMMIT TRANSACTION (all locks released)
            self.conn.commit()
            logger.info(f"Transaction committed for request_id={request_id}")
            
            return True, result
            
        except InsufficientStockError as e:
            logger.warning(f"Insufficient stock: {e.message}")
            return False, self._error_response(
                error_type="InsufficientStockError",
                error_message=e.message,
                details={
                    'blood_group': e.blood_group,
                    'available': e.available,
                    'requested': e.requested
                }
            )
        
        except AlreadyProcessedError as e:
            logger.warning(f"Double approval attempt: {e.message}")
            return False, self._error_response(
                error_type="AlreadyProcessedError",
                error_message=e.message,
                details={
                    'request_id': e.request_id,
                    'current_status': e.current_status
                }
            )
        
        except mysql.connector.Error as e:
            # Handle specific MySQL errors
            return False, self._handle_database_error(e, request_id)
        
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return False, self._error_response(
                error_type="UnexpectedError",
                error_message=str(e)
            )
        
        finally:
            self._cleanup()
    
    # ==================== TRANSACTION HELPER METHODS ====================
    
    def _fetch_request_with_lock(self, request_id: int) -> Dict[str, Any]:
        """
        CRITICAL: Fetch blood request with FOR UPDATE lock
        
        WHY FOR UPDATE?
        ================
        SELECT ... FOR UPDATE is the key to pessimistic locking:
        
        ┌─────────────────────────────────┐
        │ Admin A                         │
        │ ┌──────────────────────────────┐│
        │ │ SELECT * FROM Blood_Requests ││
        │ │ WHERE id = 123               ││
        │ │ FOR UPDATE;  ← LOCK ACQUIRED ││
        │ └──────────────────────────────┘│
        │ [Admin A now holds exclusive lock]
        │ Nobody else can:              │
        │ - Read with FOR UPDATE        │
        │ - Modify this row             │
        └─────────────────────────────────┘
                        ↓
        ┌─────────────────────────────────┐
        │ Admin B (concurrent)            │
        │ ┌──────────────────────────────┐│
        │ │ SELECT * FROM Blood_Requests ││
        │ │ WHERE id = 123               ││
        │ │ FOR UPDATE;  ← WAITS HERE    ││
        │ └──────────────────────────────┘│
        │ [Blocked until Admin A releases]
        └─────────────────────────────────┘
        
        What happens:
        1. Admin A locks row 123
        2. Admin B tries to lock same row
        3. Admin B BLOCKS (waits)
        4. Admin A finishes transaction
        5. Admin A commits and releases lock
        6. Admin B acquires lock and continues
        7. No race conditions!
        
        Without FOR UPDATE:
        1. Both admins read row (same data)
        2. Both check inventory (both pass)
        3. Both update inventory
        4. Over-allocation! ❌
        """
        
        query = """
            SELECT br.id, br.hospital_id, br.blood_group, br.units_required,
                   br.status, br.request_date, br.created_by
            FROM Blood_Requests br
            WHERE br.id = %s
            FOR UPDATE  -- PESSIMISTIC LOCK: Lock until transaction ends
        """
        
        try:
            self.cursor.execute(query, (request_id,))
            request_data = self.cursor.fetchone()
            
            if not request_data:
                raise TransactionError(
                    f"Request {request_id} not found",
                    status_code=404
                )
            
            logger.info(f"Lock acquired on request_id={request_id}")
            return request_data
            
        except mysql.connector.Error as e:
            if e.errno == errorcode.ER_LOCK_WAIT_TIMEOUT:
                raise LockTimeoutError(str(e))
            elif e.errno == errorcode.ER_LOCK_DEADLOCK:
                raise DeadlockError(str(e))
            raise
    
    def _verify_request_pending(
        self,
        request_data: Dict[str, Any],
        request_id: int
    ) -> None:
        """
        Verify request is still 'Pending' (prevent double approval)
        
        Edge Case: Double Approval
        ===========================
        Scenario:
        1. Admin A fetches request (status: Pending)
        2. Admin B approves it (status: Approved)
        3. Admin A tries to approve it
           → Should be rejected! ❌
        
        How we prevent it:
        1. Lock acquired on row → Admin B cannot modify
        2. Check status == 'Pending'
        3. If not → Raise AlreadyProcessedError
        4. Admin A sees error
        5. No double approval ✅
        
        With FOR UPDATE, Admin B can't even get the lock,
        so this scenario is impossible!
        """
        
        if request_data['status'] != 'Pending':
            raise AlreadyProcessedError(
                request_id=request_id,
                current_status=request_data['status']
            )
    
    def _process_approval(
        self,
        request_data: Dict[str, Any],
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute approval: Check batches, deduct stock, update status

        Atomic Sequence:
        1. Lock available batches (FIFO by expiry date)
        2. Verify sufficient stock
        3. Deduct from batches
        4. Update request status
        5. Log audit event
        """

        blood_group = request_data['blood_group']
        units_required = request_data['units_required']
        request_id = request_data['id']

        batch_query = """
            SELECT id, units_remaining
            FROM blood_batches
            WHERE blood_group = %s
              AND expiry_date > CURDATE()
              AND status = 'Active'
              AND units_remaining > 0
            ORDER BY expiry_date ASC, id ASC
            FOR UPDATE
        """

        self.cursor.execute(batch_query, (blood_group,))
        batches = self.cursor.fetchall() or []

        available = sum(int(batch['units_remaining'] or 0) for batch in batches)

        if available < units_required:
            raise InsufficientStockError(
                blood_group=blood_group,
                available=available,
                requested=units_required
            )

        remaining = units_required
        for batch in batches:
            if remaining <= 0:
                break
            batch_remaining = int(batch['units_remaining'] or 0)
            if batch_remaining <= 0:
                continue
            deduct = remaining if batch_remaining >= remaining else batch_remaining
            new_remaining = batch_remaining - deduct
            new_status = 'Fully Used' if new_remaining == 0 else 'Active'
            self.cursor.execute(
                "UPDATE blood_batches SET units_remaining = %s, status = %s WHERE id = %s",
                (new_remaining, new_status, batch['id'])
            )
            remaining -= deduct

        logger.info(f"Deducted {units_required} units of {blood_group} from batches")

        update_request_query = """
            UPDATE Blood_Requests
            SET status = %s, approval_date = NOW(), approved_by = %s
            WHERE id = %s
        """

        self.cursor.execute(
            update_request_query,
            ('Approved', user_id, request_id)
        )
        logger.info(f"Request {request_id} approved")

        self._log_audit_event(
            user_id=user_id,
            action='REQUEST_APPROVED',
            request_id=request_id,
            blood_group=blood_group,
            units_deducted=units_required,
            previous_stock=available,
            new_stock=available - units_required
        )

        return {
            'success': True,
            'request_id': request_id,
            'action': 'Approved',
            'blood_group': blood_group,
            'units_deducted': units_required,
            'previous_stock': available,
            'new_stock': available - units_required,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'message': f'Request {request_id} approved. {units_required} units of {blood_group} deducted from batches.'
        }

    def _process_rejection(
        self,
        request_data: Dict[str, Any],
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute rejection (simpler, no inventory changes)
        
        Still uses transaction for consistency and logging
        """
        
        request_id = request_data['id']
        
        # Update request status to Rejected
        update_request_query = """
            UPDATE Blood_Requests
            SET status = %s, approval_date = NOW(), approved_by = %s
            WHERE id = %s
        """
        
        self.cursor.execute(
            update_request_query,
            ('Rejected', user_id, request_id)
        )
        logger.info(f"Request {request_id} rejected")
        
        # Log audit event
        self._log_audit_event(
            user_id=user_id,
            action='REQUEST_REJECTED',
            request_id=request_id,
            blood_group=request_data['blood_group'],
            units_deducted=0
        )
        
        return {
            'success': True,
            'request_id': request_id,
            'action': 'Rejected',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'message': f'Request {request_id} rejected.'
        }
    
    def _log_audit_event(self, **kwargs) -> None:
        """Insert audit log entry (within transaction)"""
        
        try:
            audit_query = """
                INSERT INTO Audit_Logs
                (user_id, action, resource_type, resource_id, status, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
            """
            
            self.cursor.execute(
                audit_query,
                (
                    kwargs.get('user_id'),
                    kwargs.get('action'),
                    'BloodRequest',
                    kwargs.get('request_id'),
                    'Success'
                )
            )
            logger.info(f"Audit logged: {kwargs.get('action')}")
        except Exception as e:
            logger.error(f"Failed to log audit: {e}")
            # Don't raise - audit failure shouldn't block transaction
    
    # ==================== ERROR HANDLING ====================
    
    def _handle_database_error(
        self,
        error: mysql.connector.Error,
        request_id: int
    ) -> Dict[str, Any]:
        """
        Handle MySQL-specific errors
        
        Common errors:
        - ER_LOCK_WAIT_TIMEOUT (1205): Lock wait timeout
        - ER_LOCK_DEADLOCK (1213): Deadlock detected
        - ER_NO_REFERENCED_ROW (1452): Foreign key constraint
        - ER_DUP_ENTRY (1062): Duplicate entry
        """
        
        if error.errno == errorcode.ER_LOCK_WAIT_TIMEOUT:
            logger.warning(f"Lock timeout for request {request_id}")
            return self._error_response(
                error_type="LockTimeoutError",
                error_message="Cannot acquire lock. Try again later.",
                status_code=408  # Request timeout
            )
        
        elif error.errno == errorcode.ER_LOCK_DEADLOCK:
            logger.warning(f"Deadlock detected for request {request_id}")
            return self._error_response(
                error_type="DeadlockError",
                error_message="Database deadlock. Please retry the request.",
                status_code=409  # Conflict
            )
        
        else:
            logger.error(f"Database error: {error}")
            return self._error_response(
                error_type="DatabaseError",
                error_message=f"Database error: {str(error)}",
                status_code=500
            )
    
    def _error_response(
        self,
        error_type: str,
        error_message: str,
        details: Optional[Dict] = None,
        status_code: int = 400
    ) -> Dict[str, Any]:
        """Format error response as JSON"""
        
        response = {
            'success': False,
            'error': error_type,
            'message': error_message,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status_code': status_code
        }
        
        if details:
            response['details'] = details
        
        return response
    
    def _cleanup(self) -> None:
        """
        Cleanup: Always called in finally block
        
        Critical for preventing connection leaks!
        """
        
        try:
            if self.conn:
                # If transaction is still active, rollback
                # (in case of exception before commit)
                if self.conn.is_connected():
                    self.cursor.close() if self.cursor else None
                    self.conn.close()
                    logger.info("Connection closed and cleaned up")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


# ==================== HELPER FUNCTION ====================

def approve_blood_request(
    request_id: int,
    action: str = "Approve",
    user_id: int = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Simple interface for blood request approval
    
    Args:
        request_id: Blood request ID
        action: "Approve" or "Reject"
        user_id: Who is approving
    
    Returns:
        (success, result_dict)
    
    Example:
        >>> success, result = approve_blood_request(123, "Approve", user_id=1)
        >>> if success:
        ...     print(f"Approved: {result['units_deducted']} units deducted")
        ... else:
        ...     print(f"Error: {result['message']}")
    """
    
    handler = BloodRequestApprovalHandler()
    
    action_enum = (
        ApprovalAction.APPROVE if action.lower() == "approve"
        else ApprovalAction.REJECT
    )
    
    return handler.approve_request(request_id, action_enum, user_id)


# ==================== BULK OPERATIONS ====================

def approve_multiple_requests(request_ids: list, user_id: int = None) -> Dict[str, Any]:
    """
    Approve multiple requests (each in separate transaction)
    
    Why separate transactions?
    - Prevents deadlock from holding locks too long
    - Each transaction is independent
    - Failure in one doesn't affect others
    """
    
    results = {
        'total': len(request_ids),
        'approved': [],
        'failed': [],
        'timestamp': datetime.now().isoformat()
    }
    
    for request_id in request_ids:
        success, result = approve_blood_request(request_id, "Approve", user_id)
        
        if success:
            results['approved'].append({
                'request_id': request_id,
                'result': result
            })
        else:
            results['failed'].append({
                'request_id': request_id,
                'error': result
            })
    
    return results


if __name__ == '__main__':
    # Example usage and testing
    print("=" * 60)
    print("Blood Request Approval with Pessimistic Locking")
    print("=" * 60)
    
    # Test single approval
    success, result = approve_blood_request(
        request_id=1,
        action="Approve",
        user_id=5
    )
    
    print(f"\nResult:")
    print(json.dumps(result, indent=2))

