"""
TRANSACTION ROUTES - Flask HTTP Endpoints for Blood Request Approvals
=====================================================================

Integrates transaction_lock_handler.py with Flask application.
Provides HTTP endpoints for approving/rejecting blood requests with
pessimistic locking and transaction support.

Routes:
- POST /api/requests/<request_id>/approve
  Approve a blood request (requires 'request:approve' permission)
  
- POST /api/requests/<request_id>/reject
  Reject a blood request (requires 'request:reject' permission)
  
- GET /api/pending-requests
  List all pending requests requiring approval (RBAC filtered)

- POST /api/requests/bulk-approve
  Approve multiple requests atomically (admin only)

Author: Blood Bank Management System
Version: 1.0.0
"""

import logging
import os
import mysql.connector
from flask import Blueprint, request, jsonify, session
from datetime import datetime
from transaction_lock_handler import (
    approve_blood_request,
    InsufficientStockError,
    AlreadyProcessedError,
    DeadlockError,
    LockTimeoutError
)
from rbac import permission_required, can_approve_blood_request

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Create Blueprint for transaction routes
transaction_bp = Blueprint('transactions', __name__, url_prefix='/api')

DB_CONFIG = {
    'host': os.getenv('BBMS_DB_HOST', 'localhost'),
    'user': os.getenv('BBMS_DB_USER', 'root'),
    'password': os.getenv('BBMS_DB_PASSWORD', 'jefrin'),
    'database': os.getenv('BBMS_DB_NAME', 'blood_bank_db'),
    'port': int(os.getenv('BBMS_DB_PORT', '3306'))
}

# ==================== HELPER FUNCTIONS ====================

def get_current_user_id():
    """Extract user_id from Flask session"""
    if 'user_id' not in session:
        return None
    return session.get('user_id')

def get_current_user_hospital_id():
    """Extract hospital_id for current user"""
    user_id = get_current_user_id()
    if not user_id:
        return None
    
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT hospital_id FROM Users_RBAC WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        logger.warning(f"Could not get hospital_id for user {user_id}: {str(e)}")
        return None

def format_response(success, message, data=None, status_code=200, error_type=None):
    """
    Standard JSON response format for transaction endpoints
    
    Args:
        success (bool): Operation succeeded
        message (str): Human-readable message
        data (dict): Optional response data
        status_code (int): HTTP status code
        error_type (str): Type of error (for debugging)
    
    Returns:
        tuple: (dict, int) for Flask jsonify
    """
    response = {
        'success': success,
        'message': message,
        'timestamp': datetime.utcnow().isoformat(),
        'status_code': status_code
    }
    
    if error_type:
        response['error_type'] = error_type
    
    if data:
        response['data'] = data
    
    return jsonify(response), status_code

# ==================== ENDPOINTS ====================

@transaction_bp.route('/requests/<int:request_id>/approve', methods=['POST'])
@permission_required('request:approve')
def approve_request_http(request_id):
    """
    HTTP Endpoint: Approve Blood Request
    
    POST /api/requests/123/approve
    
    Required Permissions:
    - request:approve
    - NOT same hospital as request (conflict check)
    
    Request Body: {} (empty or can include metadata)
    
    Response (Success 200):
    {
        "success": true,
        "message": "Request 123 approved",
        "data": {
            "request_id": 123,
            "blood_group": "O+",
            "units_approved": 10,
            "new_stock": 25,
            "hospital_name": "City Hospital"
        },
        "timestamp": "2024-01-15T10:30:45.123456"
    }
    
    Response (Insufficient Stock 400):
    {
        "success": false,
        "message": "Insufficient stock to fulfill request",
        "error_type": "InsufficientStockError",
        "data": {
            "blood_group": "AB-",
            "requested": 15,
            "available": 8
        },
        "status_code": 400
    }
    
    Response (Already Processed 409):
    {
        "success": false,
        "message": "Request already approved",
        "error_type": "AlreadyProcessedError",
        "data": {
            "request_id": 123,
            "current_status": "Approved",
            "approved_by": 5,
            "approved_at": "2024-01-15T10:25:00"
        },
        "status_code": 409
    }
    
    Response (Lock Timeout 408):
    {
        "success": false,
        "message": "Could not acquire lock. Try again.",
        "error_type": "LockTimeoutError",
        "status_code": 408
    }
    
    Response (Deadlock 409):
    {
        "success": false,
        "message": "Database deadlock. Request retried.",
        "error_type": "DeadlockError",
        "status_code": 409
    }
    """
    try:
        # Get current user
        user_id = get_current_user_id()
        if not user_id:
            return format_response(
                success=False,
                message='User not authenticated',
                status_code=401,
                error_type='AuthenticationError'
            )
        
        # CONFLICT CHECK: User cannot approve requests from their own hospital
        can_approve, deny_reason = can_approve_blood_request(user_id, request_id)
        if not can_approve:
            return format_response(
                success=False,
                message=deny_reason or 'Conflict of interest: Cannot approve request from your own hospital',
                status_code=403,
                error_type='ConflictOfInterest'
            )
        
        logger.info(f"User {user_id} attempting to approve request {request_id}")
        
        # Call transaction handler
        success, result = approve_blood_request(
            request_id=request_id,
            action='approve',
            user_id=user_id
        )
        
        # Check result
        if success:
            logger.info(f"Request {request_id} approved successfully by user {user_id}")
            return format_response(
                success=True,
                message=f"Request {request_id} approved successfully",
                data={
                    'request_id': request_id,
                    'blood_group': result.get('blood_group'),
                    'units_approved': result.get('units_deducted'),
                    'new_stock': result.get('new_stock'),
                    'approval_timestamp': result.get('timestamp')
                },
                status_code=200
            )
        else:
            # Transaction failed - extract error details
            error_type = result.get('error', 'UnknownError')
            status_code = result.get('status_code', 400)
            message = result.get('message', 'Transaction failed')
            
            logger.warning(f"Request {request_id} approval failed: {error_type} - {message}")
            
            return format_response(
                success=False,
                message=message,
                data=result.get('details'),
                status_code=status_code,
                error_type=error_type
            )
    
    except InsufficientStockError as e:
        logger.warning(f"Insufficient stock for request {request_id}: {str(e)}")
        return format_response(
            success=False,
            message=f"Insufficient {e.blood_group} blood. Available: {e.available}, Required: {e.requested}",
            data={
                'blood_group': e.blood_group,
                'available': e.available,
                'requested': e.requested
            },
            status_code=400,
            error_type='InsufficientStockError'
        )
    
    except AlreadyProcessedError as e:
        logger.warning(f"Request {request_id} already processed: {str(e)}")
        return format_response(
            success=False,
            message=f"Request already {e.current_status.lower()}",
            data={
                'request_id': request_id,
                'current_status': e.current_status
            },
            status_code=409,
            error_type='AlreadyProcessedError'
        )
    
    except LockTimeoutError as e:
        logger.error(f"Lock timeout for request {request_id}: {str(e)}")
        return format_response(
            success=False,
            message='Could not acquire database lock. Another operation is in progress. Please try again.',
            status_code=408,
            error_type='LockTimeoutError'
        )
    
    except DeadlockError as e:
        logger.error(f"Deadlock detected for request {request_id}: {str(e)}")
        return format_response(
            success=False,
            message='Database deadlock occurred. Request will be retried.',
            status_code=409,
            error_type='DeadlockError'
        )
    
    except Exception as e:
        logger.exception(f"Unexpected error approving request {request_id}: {str(e)}")
        return format_response(
            success=False,
            message=str(e),
            status_code=500,
            error_type='InternalServerError'
        )


@transaction_bp.route('/requests/<int:request_id>/reject', methods=['POST'])
@permission_required('request:reject')
def reject_request_http(request_id):
    """
    HTTP Endpoint: Reject Blood Request
    
    POST /api/requests/123/reject
    Content-Type: application/json
    
    Request Body:
    {
        "reason": "Stock reserved for critical case"
    }
    
    Required Permissions:
    - request:reject
    
    Response (Success 200):
    {
        "success": true,
        "message": "Request 123 rejected",
        "data": {
            "request_id": 123,
            "rejection_reason": "Stock reserved for critical case"
        },
        "timestamp": "2024-01-15T10:30:45.123456"
    }
    """
    try:
        user_id = get_current_user_id()
        if not user_id:
            return format_response(
                success=False,
                message='User not authenticated',
                status_code=401,
                error_type='AuthenticationError'
            )
        
        # Get rejection reason from request body
        data = request.get_json() or {}
        reason = data.get('reason', 'No reason provided')
        
        logger.info(f"User {user_id} attempting to reject request {request_id}")
        
        # Call transaction handler for rejection
        success, result = approve_blood_request(
            request_id=request_id,
            action='reject',
            user_id=user_id
        )
        
        if success:
            logger.info(f"Request {request_id} rejected successfully by user {user_id}")
            return format_response(
                success=True,
                message=f"Request {request_id} rejected",
                data={
                    'request_id': request_id,
                    'rejection_reason': reason
                },
                status_code=200
            )
        else:
            return format_response(
                success=False,
                message=result.get('message', 'Rejection failed'),
                data=result.get('details'),
                status_code=result.get('status_code', 400),
                error_type=result.get('error')
            )
    
    except AlreadyProcessedError as e:
        return format_response(
            success=False,
            message=f"Request already {e.current_status.lower()}",
            status_code=409,
            error_type='AlreadyProcessedError'
        )
    
    except Exception as e:
        logger.exception(f"Error rejecting request {request_id}: {str(e)}")
        return format_response(
            success=False,
            message=str(e),
            status_code=500,
            error_type='InternalServerError'
        )


@transaction_bp.route('/requests/pending', methods=['GET'])
@permission_required('request:read')
def list_pending_requests():
    """
    HTTP Endpoint: List Pending Requests
    
    GET /api/requests/pending
    
    Query Parameters:
    - blood_group: Filter by blood group (optional)
    - hospital_id: Filter by hospital (optional, RBAC filtered)
    - limit: Results per page (default 50)
    - page: Page number (default 1)
    
    Response:
    {
        "success": true,
        "message": "Pending requests retrieved",
        "data": {
            "total": 3,
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
        "timestamp": "2024-01-15T10:30:45.123456"
    }
    """
    try:
        user_id = get_current_user_id()
        if not user_id:
            return format_response(
                success=False,
                message='User not authenticated',
                status_code=401,
                error_type='AuthenticationError'
            )
        
        # Get query parameters
        blood_group = request.args.get('blood_group')
        hospital_id = request.args.get('hospital_id')
        limit = int(request.args.get('limit', 50))
        page = int(request.args.get('page', 1))
        offset = (page - 1) * limit
        
        # Connect to database
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        # Build query
        query = """
        SELECT 
            br.id as request_id,
            h.name as hospital,
            br.blood_group,
            br.units_required as units,
            br.request_date,
            COALESCE(bi.total_units, 0) as available_stock,
            CASE 
                WHEN COALESCE(bi.total_units, 0) >= br.units_required THEN 'Can Approve'
                ELSE 'Insufficient Stock'
            END as approvability
        FROM Blood_Requests br
        JOIN Hospitals h ON br.hospital_id = h.id
        LEFT JOIN (
            SELECT blood_group, SUM(units_remaining) as total_units
            FROM blood_batches
            WHERE expiry_date > CURDATE() AND status = 'Active'
            GROUP BY blood_group
        ) bi ON br.blood_group = bi.blood_group
        WHERE br.status = 'Pending'
        """
        
        params = []
        
        if blood_group:
            query += " AND br.blood_group = %s"
            params.append(blood_group)
        
        if hospital_id:
            query += " AND br.hospital_id = %s"
            params.append(hospital_id)
        
        query += " ORDER BY br.request_date ASC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        requests = cursor.fetchall()
        
        # Get total count
        count_query = """
        SELECT COUNT(*) as total FROM Blood_Requests 
        WHERE status = 'Pending'
        """
        if blood_group:
            count_query += " AND blood_group = %s"
        if hospital_id:
            count_query += " AND hospital_id = %s"
        
        count_params = [blood_group] if blood_group else []
        if hospital_id:
            count_params.append(hospital_id)
        
        cursor.execute(count_query, count_params)
        total = cursor.fetchone()['total']
        
        cursor.close()
        conn.close()
        
        return format_response(
            success=True,
            message=f"Retrieved {len(requests)} pending requests",
            data={
                'total': total,
                'page': page,
                'limit': limit,
                'requests': requests
            },
            status_code=200
        )
    
    except Exception as e:
        logger.exception(f"Error listing pending requests: {str(e)}")
        return format_response(
            success=False,
            message=str(e),
            status_code=500,
            error_type='InternalServerError'
        )


@transaction_bp.route('/requests/bulk-approve', methods=['POST'])
@permission_required('admin:manage')  # Admin only
def bulk_approve_requests():
    """
    HTTP Endpoint: Bulk Approve Multiple Requests
    
    POST /api/requests/bulk-approve
    Content-Type: application/json
    
    Request Body:
    {
        "request_ids": [123, 124, 125]
    }
    
    Response:
    {
        "success": true,
        "message": "Approved 3 requests",
        "data": {
            "approved": [123, 124, 125],
            "failed": [],
            "total_processed": 3
        }
    }
    """
    try:
        user_id = get_current_user_id()
        if not user_id:
            return format_response(
                success=False,
                message='User not authenticated',
                status_code=401,
                error_type='AuthenticationError'
            )
        
        data = request.get_json() or {}
        request_ids = data.get('request_ids', [])
        
        if not request_ids or not isinstance(request_ids, list):
            return format_response(
                success=False,
                message='request_ids must be a list of integers',
                status_code=400,
                error_type='InvalidInput'
            )
        
        logger.info(f"User {user_id} bulk approving {len(request_ids)} requests")
        
        approved = []
        failed = []
        
        # Approve each request
        for req_id in request_ids:
            try:
                can_approve, deny_reason = can_approve_blood_request(user_id, req_id)
                if not can_approve:
                    failed.append({
                        'request_id': req_id,
                        'error': deny_reason or 'Conflict of interest'
                    })
                    continue
                
                success, result = approve_blood_request(
                    request_id=req_id,
                    action='approve',
                    user_id=user_id
                )
                
                if success:
                    approved.append(req_id)
                else:
                    failed.append({
                        'request_id': req_id,
                        'error': result.get('message')
                    })
            
            except Exception as e:
                logger.warning(f"Failed to approve request {req_id}: {str(e)}")
                failed.append({
                    'request_id': req_id,
                    'error': str(e)
                })
        
        return format_response(
            success=len(approved) > 0,
            message=f"Approved {len(approved)} out of {len(request_ids)} requests",
            data={
                'approved': approved,
                'failed': failed,
                'total_processed': len(request_ids),
                'success_count': len(approved),
                'failure_count': len(failed)
            },
            status_code=200 if len(failed) == 0 else 207  # 207 Multi-Status
        )
    
    except Exception as e:
        logger.exception(f"Error in bulk approve: {str(e)}")
        return format_response(
            success=False,
            message=str(e),
            status_code=500,
            error_type='InternalServerError'
        )


# ==================== REGISTER ROUTES ====================

def register_transaction_routes(app):
    """
    Register transaction routes to Flask app
    
    Usage in app.py:
        from transaction_routes import register_transaction_routes
        register_transaction_routes(app)
    """
    app.register_blueprint(transaction_bp)
    logger.info("Transaction routes registered successfully")


# ==================== ERROR HANDLERS ====================

@transaction_bp.errorhandler(401)
def unauthorized(error):
    return format_response(
        success=False,
        message='Unauthorized - Login required',
        status_code=401,
        error_type='Unauthorized'
    )

@transaction_bp.errorhandler(403)
def forbidden(error):
    return format_response(
        success=False,
        message='Forbidden - Insufficient permissions',
        status_code=403,
        error_type='Forbidden'
    )

@transaction_bp.errorhandler(404)
def not_found(error):
    return format_response(
        success=False,
        message='Resource not found',
        status_code=404,
        error_type='NotFound'
    )

@transaction_bp.errorhandler(500)
def internal_error(error):
    logger.exception("Internal server error")
    return format_response(
        success=False,
        message='Internal server error',
        status_code=500,
        error_type='InternalServerError'
    )


if __name__ == '__main__':
    # For testing
    from flask import Flask
    
    test_app = Flask(__name__)
    test_app.secret_key = 'test-secret-key'
    register_transaction_routes(test_app)
    
    print("Transaction routes registered. Routes:")
    for rule in test_app.url_map.iter_rules():
        if 'transactions' in rule.endpoint:
            print(f"  {rule.rule} [{rule.methods}]")
