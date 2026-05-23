"""
Blood Bank Management System - Role-Based Access Control (RBAC) Middleware
Author: Security Team
Purpose: Enforce permission-based access control across all endpoints
"""

import mysql.connector
from mysql.connector import Error
from functools import wraps
from flask import session, jsonify, request, redirect, url_for, flash
from datetime import datetime
import json
import logging
import os
from db_config import get_db_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CONFIG = {
    **get_db_config()
}

# ==================== PERMISSION CACHE ====================
# In production, use Redis for distributed caching

USER_PERMISSIONS_CACHE = {}  # {user_id: [permissions]}
ROLE_PERMISSIONS_CACHE = {}  # {role_id: [permissions]}


def get_db():
    """Get database connection"""
    return mysql.connector.connect(**DB_CONFIG)


def invalidate_permission_cache(user_id=None, role_id=None):
    """Invalidate caches when permissions change"""
    if user_id and user_id in USER_PERMISSIONS_CACHE:
        del USER_PERMISSIONS_CACHE[user_id]
    if role_id and role_id in ROLE_PERMISSIONS_CACHE:
        del ROLE_PERMISSIONS_CACHE[role_id]


# ==================== USER & ROLE HELPERS ====================

def get_user_role(user_id):
    """
    Fetch user's role ID from database
    Returns: (role_id, role_name) tuple or (None, None)
    """
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT u.role_id, r.role_name 
            FROM Users_RBAC u
            JOIN Roles r ON u.role_id = r.id
            WHERE u.id = %s AND u.is_active = TRUE
        """, (user_id,))
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result:
            return result['role_id'], result['role_name']
        return None, None
    except Error as e:
        logger.error(f"Error fetching user role: {e}")
        return None, None


def get_user_permissions(user_id):
    """
    Fetch all permissions for a user based on their role
    Returns: List of permission names
    Caches result to reduce database queries
    """
    # Check cache first
    if user_id in USER_PERMISSIONS_CACHE:
        return USER_PERMISSIONS_CACHE[user_id]
    
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT DISTINCT p.permission_name
            FROM Users_RBAC u
            JOIN Roles r ON u.role_id = r.id
            JOIN Role_Permissions rp ON r.id = rp.role_id
            JOIN Permissions p ON rp.permission_id = p.id
            WHERE u.id = %s AND u.is_active = TRUE AND r.is_active = TRUE
        """, (user_id,))
        
        permissions = [row['permission_name'] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        
        # Cache the result
        USER_PERMISSIONS_CACHE[user_id] = permissions
        
        return permissions
    except Error as e:
        logger.error(f"Error fetching user permissions: {e}")
        return []


def user_has_permission(user_id, permission_name):
    """
    Check if user has a specific permission
    
    Args:
        user_id: User ID
        permission_name: Permission name (e.g., 'request:approve')
    
    Returns: Boolean
    """
    permissions = get_user_permissions(user_id)
    return permission_name in permissions


# ==================== RBAC DECORATOR ====================

def role_required(*required_roles):
    """
    Decorator to restrict access based on user role
    Usage: @role_required('BLOOD_BANK_ADMIN', 'SUPER_ADMIN')
    
    Security Note: This checks role membership, not granular permissions.
    For granular access control, use @permission_required instead.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Check if user is logged in
            user_id = session.get('user_id')
            if not user_id:
                if request.is_json or 'application/json' in request.headers.get('Accept', ''):
                    return jsonify({'error': 'Unauthorized. Please login.'}), 401
                return redirect(url_for('login')), 302
            
            # Get user's role
            _, role_name = get_user_role(user_id)
            
            if not role_name or role_name not in required_roles:
                # Log the unauthorized access attempt
                log_audit_event(
                    user_id=user_id,
                    action='ACCESS_DENIED',
                    resource_type='ENDPOINT',
                    resource_id=None,
                    status='Denied',
                    reason_if_denied=f'Insufficient role. Required: {required_roles}, Got: {role_name}'
                )
                
                if request.is_json or 'application/json' in request.headers.get('Accept', ''):
                    return jsonify({
                        'error': 'Access Denied',
                        'message': f'This action requires one of these roles: {", ".join(required_roles)}'
                    }), 403
                
                flash(f'Access Denied. Required role: {", ".join(required_roles)}', 'danger')
                return redirect(url_for('index')), 302
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def permission_required(permission_name):
    """
    Decorator to restrict access based on granular permission
    Usage: @permission_required('request:approve')
    
    This is the preferred decorator for granular access control.
    It checks the user's specific permissions, not just their role.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Check if user is logged in
            user_id = session.get('user_id')
            if not user_id:
                if request.is_json or 'application/json' in request.headers.get('Accept', ''):
                    return jsonify({'error': 'Unauthorized. Please login.'}), 401
                return redirect(url_for('login')), 302
            
            # Check permission
            if not user_has_permission(user_id, permission_name):
                # Log the denied access
                log_audit_event(
                    user_id=user_id,
                    action='PERMISSION_DENIED',
                    resource_type='ENDPOINT',
                    resource_id=None,
                    status='Denied',
                    reason_if_denied=f'Missing permission: {permission_name}'
                )
                
                if request.is_json or 'application/json' in request.headers.get('Accept', ''):
                    return jsonify({
                        'error': 'Permission Denied',
                        'message': f'You do not have permission: {permission_name}'
                    }), 403
                
                flash(f'Permission Denied: {permission_name}', 'danger')
                return redirect(url_for('index')), 302
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ==================== SEPARATION OF CONCERNS ====================

def can_approve_blood_request(user_id, request_id):
    """
    SEPARATION OF CONCERNS: Explicit permission check for request approval
    
    Business Rule:
    - Only BLOOD_BANK_ADMIN or SUPER_ADMIN can approve requests
    - A hospital CANNOT approve their own requests
    - Must have required permission: 'request:approve'
    
    Args:
        user_id: User attempting to approve
        request_id: Blood request ID
    
    Returns:
        (can_approve, reason_if_denied)
    """
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        # Check 1: User must have the permission
        if not user_has_permission(user_id, 'request:approve'):
            return False, "Missing permission: request:approve"
        
        # Check 2: Get the request details
        cursor.execute("""
            SELECT br.id, br.hospital_id, br.status 
            FROM Blood_Requests br
            WHERE br.id = %s
        """, (request_id,))
        
        request_data = cursor.fetchone()
        if not request_data:
            return False, "Blood request not found"
        
        # Check 3: Get user's hospital (if assigned)
        cursor.execute("""
            SELECT hospital_id FROM Users_RBAC WHERE id = %s
        """, (user_id,))
        
        user_data = cursor.fetchone()
        user_hospital_id = user_data['hospital_id'] if user_data else None
        
        # Check 4: CRITICAL - Prevent hospital from approving own request
        if user_hospital_id and user_hospital_id == request_data['hospital_id']:
            return False, "Conflict of Interest: Cannot approve your own hospital's request"
        
        # Check 5: Cannot approve already approved/rejected requests
        if request_data['status'] != 'Pending':
            return False, f"Request is already {request_data['status']}"
        
        cursor.close()
        conn.close()
        return True, None
        
    except Error as e:
        logger.error(f"Error in can_approve_blood_request: {e}")
        return False, "Database error"


def can_create_blood_request(user_id):
    """
    SEPARATION OF CONCERNS: Explicit permission check for creating request
    
    Business Rule:
    - Only HOSPITAL_USER can create requests (in their own hospital)
    - Must have required permission: 'request:create'
    
    Returns:
        (can_create, hospital_id, reason_if_denied)
    """
    try:
        # Check 1: User must have permission
        if not user_has_permission(user_id, 'request:create'):
            return False, None, "Missing permission: request:create"
        
        # Check 2: User must be assigned to a hospital
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT hospital_id FROM Users_RBAC WHERE id = %s AND hospital_id IS NOT NULL
        """, (user_id,))
        
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not user_data:
            return False, None, "Hospital User must be assigned to a hospital"
        
        return True, user_data['hospital_id'], None
        
    except Error as e:
        logger.error(f"Error in can_create_blood_request: {e}")
        return False, None, "Database error"


# ==================== AUDIT LOGGING ====================

def log_audit_event(user_id, action, resource_type, resource_id, 
                   old_value=None, new_value=None, status='Success', 
                   reason_if_denied=None):
    """
    Log all critical actions for audit trail and security compliance
    
    Args:
        user_id: Who performed the action
        action: What action (e.g., 'APPROVE_REQUEST', 'CREATE_DONOR')
        resource_type: Type of resource (e.g., 'BloodRequest', 'Donor')
        resource_id: ID of the affected resource
        old_value: Previous state (JSON)
        new_value: New state (JSON)
        status: 'Success', 'Denied', 'Failed'
        reason_if_denied: Why permission was denied (if applicable)
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        ip_address = request.remote_addr if request else 'system'
        user_agent = request.headers.get('User-Agent', '')[:255] if request else ''
        
        cursor.execute("""
            INSERT INTO Audit_Logs 
            (user_id, action, resource_type, resource_id, old_value, new_value, 
             ip_address, user_agent, status, reason_if_denied)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            action,
            resource_type,
            resource_id,
            json.dumps(old_value) if old_value else None,
            json.dumps(new_value) if new_value else None,
            ip_address,
            user_agent,
            status,
            reason_if_denied
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Audit: {action} on {resource_type}#{resource_id} by User#{user_id} - {status}")
        
    except Error as e:
        logger.error(f"Error logging audit event: {e}")


def get_audit_logs(user_id=None, days=30, limit=100):
    """
    Retrieve audit logs
    If user_id provided, only return logs for that user's own actions
    """
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        if user_id:
            # User can only see their own logs
            cursor.execute("""
                SELECT id, user_id, action, resource_type, resource_id, 
                       status, created_at
                FROM Audit_Logs
                WHERE user_id = %s AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                ORDER BY created_at DESC
                LIMIT %s
            """, (user_id, days, limit))
        else:
            # Admin can see all logs
            cursor.execute("""
                SELECT id, user_id, action, resource_type, resource_id, 
                       status, reason_if_denied, created_at
                FROM Audit_Logs
                WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                ORDER BY created_at DESC
                LIMIT %s
            """, (days, limit))
        
        logs = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return logs
    except Error as e:
        logger.error(f"Error fetching audit logs: {e}")
        return []


# ==================== HELPER FUNCTIONS ====================

def verify_request_ownership(user_id, request_id):
    """
    Verify that a hospital user is requesting their own work
    Prevents one hospital from accessing another's requests
    """
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        # Get user's hospital
        cursor.execute("""
            SELECT hospital_id FROM Users_RBAC WHERE id = %s
        """, (user_id,))
        
        user_data = cursor.fetchone()
        if not user_data:
            cursor.close()
            conn.close()
            return False
        
        user_hospital_id = user_data['hospital_id']
        
        # Check if request belongs to user's hospital
        cursor.execute("""
            SELECT hospital_id FROM Blood_Requests WHERE id = %s
        """, (request_id,))
        
        request_data = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if request_data:
            return request_data['hospital_id'] == user_hospital_id
        return False
        
    except Error as e:
        logger.error(f"Error verifying request ownership: {e}")
        return False


def get_current_user_info():
    """Get current logged-in user's information"""
    user_id = session.get('user_id')
    if not user_id:
        return None
    
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT u.id, u.username, u.email, u.full_name, 
                   r.role_name, u.hospital_id
            FROM Users_RBAC u
            JOIN Roles r ON u.role_id = r.id
            WHERE u.id = %s
        """, (user_id,))
        
        user_info = cursor.fetchone()
        cursor.close()
        conn.close()
        
        return user_info
    except Error as e:
        logger.error(f"Error fetching user info: {e}")
        return None


def is_super_admin(user_id):
    """Quick check if user is super admin"""
    _, role_name = get_user_role(user_id)
    return role_name == 'SUPER_ADMIN'


def is_blood_bank_admin(user_id):
    """Quick check if user is blood bank admin"""
    _, role_name = get_user_role(user_id)
    return role_name == 'BLOOD_BANK_ADMIN'
