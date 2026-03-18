"""
Blood Bank Management System - RBAC-Secure Route Handlers
File: rbac_routes.py
Purpose: Drop-in replacements for app.py routes with RBAC security
Integration: Copy-paste these functions into app.py after updating imports
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from functools import wraps
from datetime import datetime
import mysql.connector
from mysql.connector import Error
import logging
import os
from rbac import (
    permission_required, role_required, log_audit_event, 
    get_user_permissions, get_current_user_info, user_has_permission,
    can_approve_blood_request, can_create_blood_request,
    verify_request_ownership, get_audit_logs,
    invalidate_permission_cache
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CONFIG = {
    'host': os.getenv('BBMS_DB_HOST', 'localhost'),
    'user': os.getenv('BBMS_DB_USER', 'root'),
    'password': os.getenv('BBMS_DB_PASSWORD', 'jefrin'),
    'database': os.getenv('BBMS_DB_NAME', 'blood_bank_db'),
    'port': int(os.getenv('BBMS_DB_PORT', '3306'))
}

def get_db():
    """Get database connection"""
    return mysql.connector.connect(**DB_CONFIG)

def dict_from_cursor(cursor, row):
    """Convert row to dict"""
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))

def dict_from_cursor_list(cursor, rows):
    """Convert rows to list of dicts"""
    if not rows:
        return []
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


# ==================== SECURE LOGIN/LOGOUT ====================

def login_user(request_app):
    """
    Enhanced login with RBAC integration
    
    Security Features:
    - Hash password verification (placeholder - use bcrypt in production)
    - Session management
    - Failed login attempt tracking
    - Audit logging
    """
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            flash('Username and password required', 'danger')
            return True  # Return render_template('login.html')
        
        try:
            conn = get_db()
            cursor = conn.cursor(dictionary=True)
            
            # Query user with role info
            cursor.execute("""
                SELECT u.id, u.username, u.password_hash, u.full_name, 
                       u.is_active, u.is_locked, u.failed_login_attempts,
                       r.role_name
                FROM Users_RBAC u
                JOIN Roles r ON u.role_id = r.id
                WHERE u.username = %s
            """, (username,))
            
            user = cursor.fetchone()
            
            if not user:
                log_audit_event(
                    user_id=None,
                    action='LOGIN_FAILED',
                    resource_type='USER',
                    resource_id=None,
                    status='Failed',
                    reason_if_denied='User not found'
                )
                flash('Invalid username or password', 'danger')
                cursor.close()
                conn.close()
                return True
            
            # Check if account is locked (too many failed attempts)
            if user['is_locked']:
                log_audit_event(
                    user_id=user['id'],
                    action='LOGIN_FAILED',
                    resource_type='USER',
                    resource_id=None,
                    status='Denied',
                    reason_if_denied='Account locked due to failed login attempts'
                )
                flash('Account is locked. Contact administrator.', 'danger')
                cursor.close()
                conn.close()
                return True
            
            # Check if account is active
            if not user['is_active']:
                log_audit_event(
                    user_id=user['id'],
                    action='LOGIN_FAILED',
                    resource_type='USER',
                    resource_id=None,
                    status='Denied',
                    reason_if_denied='Account inactive'
                )
                flash('Account is inactive. Contact administrator.', 'danger')
                cursor.close()
                conn.close()
                return True
            
            # TODO: Replace with bcrypt.checkpw() in production
            # For demo: plain text comparison (NOT SECURE)
            if user['password_hash'] != password:
                # Increment failed login attempts
                failed_attempts = user['failed_login_attempts'] + 1
                is_locked = failed_attempts >= 5  # Lock after 5 failed attempts
                
                cursor.execute("""
                    UPDATE Users_RBAC 
                    SET failed_login_attempts = %s, is_locked = %s
                    WHERE id = %s
                """, (failed_attempts, is_locked, user['id']))
                conn.commit()
                
                log_audit_event(
                    user_id=user['id'],
                    action='LOGIN_FAILED',
                    resource_type='USER',
                    resource_id=None,
                    status='Failed',
                    reason_if_denied=f'Invalid password (attempt {failed_attempts}/5)'
                )
                
                flash('Invalid username or password', 'danger')
                cursor.close()
                conn.close()
                return True
            
            # Login successful
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user['role_name']
            session.permanent = True
            
            # Reset failed login attempts
            cursor.execute("""
                UPDATE Users_RBAC 
                SET failed_login_attempts = 0, last_login = NOW()
                WHERE id = %s
            """, (user['id'],))
            conn.commit()
            
            log_audit_event(
                user_id=user['id'],
                action='LOGIN_SUCCESS',
                resource_type='USER',
                resource_id=user['id'],
                status='Success'
            )
            
            flash(f'Welcome, {user["full_name"]}! Role: {user["role_name"]}', 'success')
            cursor.close()
            conn.close()
            
            return False  # Redirect to index
            
        except Error as e:
            logger.error(f"Login database error: {e}")
            flash(f'Database error: {str(e)}', 'danger')
            return True
    
    return True  # Render login page


def logout_user():
    """Logout with audit logging"""
    user_id = session.get('user_id')
    
    if user_id:
        log_audit_event(
            user_id=user_id,
            action='LOGOUT',
            resource_type='USER',
            resource_id=user_id,
            status='Success'
        )
    
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))


# ==================== SECURE REQUEST APPROVAL ====================

def update_request_status_secure(request_id, status):
    """
    SECURE Request Approval Handler
    
    Business Rules Enforced:
    1. Only BLOOD_BANK_ADMIN or SUPER_ADMIN can approve
    2. Cannot approve own hospital's requests (Conflict of Interest)
    3. Must have explicit permission: 'request:approve'
    4. All actions are audited
    
    Args:
        request_id: BloodRequest ID
        status: 'Approved' or 'Rejected'
    
    Returns:
        (success, message, changed_fields)
    """
    user_id = session.get('user_id')
    if not user_id:
        return False, 'Not authenticated', None
    
    # Validate status
    if status not in ['Approved', 'Rejected']:
        return False, 'Invalid status', None
    
    try:
        # Check authorization
        can_approve, denial_reason = can_approve_blood_request(user_id, request_id)
        if not can_approve:
            log_audit_event(
                user_id=user_id,
                action='APPROVE_REQUEST',
                resource_type='BloodRequest',
                resource_id=request_id,
                status='Denied',
                reason_if_denied=denial_reason
            )
            return False, denial_reason, None
        
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        # Get current request state (for audit)
        cursor.execute("""
            SELECT id, hospital_id, blood_group, units_required, status, request_date
            FROM Blood_Requests
            WHERE id = %s
        """, (request_id,))
        
        old_request = cursor.fetchone()
        if not old_request:
            cursor.close()
            conn.close()
            return False, 'Request not found', None
        
        old_state = dict(old_request)
        new_state = dict(old_request)
        
        # Process approval
        if status == 'Approved':
            blood_group = old_request['blood_group']
            units = int(old_request['units_required'] or 0)

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

            cursor.execute(batch_query, (blood_group,))
            batches = cursor.fetchall() or []
            available = sum(int(batch['units_remaining'] or 0) for batch in batches)

            if available < units:
                log_audit_event(
                    user_id=user_id,
                    action='APPROVE_REQUEST',
                    resource_type='BloodRequest',
                    resource_id=request_id,
                    old_value=old_state,
                    status='Denied',
                    reason_if_denied=f'Insufficient inventory: {available}/{units} available'
                )
                conn.rollback()
                cursor.close()
                conn.close()
                return False, f'Insufficient inventory: {available}/{units} available', None

            remaining = units
            for batch in batches:
                if remaining <= 0:
                    break
                batch_remaining = int(batch['units_remaining'] or 0)
                if batch_remaining <= 0:
                    continue
                deduct = remaining if batch_remaining >= remaining else batch_remaining
                new_remaining = batch_remaining - deduct
                new_status = 'Fully Used' if new_remaining == 0 else 'Active'
                cursor.execute(
                    "UPDATE blood_batches SET units_remaining = %s, status = %s WHERE id = %s",
                    (new_remaining, new_status, batch['id'])
                )
                remaining -= deduct

            new_state['available_units'] = available - units
        
        # Update request status
        approval_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S') if status == 'Approved' else None
        
        cursor.execute("""
            UPDATE Blood_Requests 
            SET status = %s, approval_date = %s, approved_by = %s
            WHERE id = %s
        """, (status, approval_date, user_id, request_id))
        
        new_state['status'] = status
        new_state['approved_by'] = user_id
        new_state['approval_date'] = approval_date
        
        conn.commit()
        
        # Audit log - SUCCESS
        log_audit_event(
            user_id=user_id,
            action=f'REQUEST_{status.upper()}',
            resource_type='BloodRequest',
            resource_id=request_id,
            old_value=old_state,
            new_value=new_state,
            status='Success'
        )
        
        cursor.close()
        conn.close()
        
        return True, f'Request {status.lower()} successfully', new_state
        
    except Error as e:
        logger.error(f"Database error in update_request_status_secure: {e}")
        log_audit_event(
            user_id=user_id,
            action='APPROVE_REQUEST',
            resource_type='BloodRequest',
            resource_id=request_id,
            status='Failed',
            reason_if_denied=f'Database error: {str(e)}'
        )
        return False, f'Database error: {str(e)}', None


# ==================== SECURE DONATION RECORDING ====================

def record_donation_secure(donor_id, units, donation_date, user_id):
    """
    SECURE Donation Recording
    
    Business Rules:
    - Only STAFF_MEMBER, BLOOD_BANK_ADMIN, SUPER_ADMIN can record
    - Must have permission: 'donation:create'
    - Inventory AUTOMATICALLY increases via trigger
    
    Returns:
        (success, donation_id, message)
    """
    try:
        # Check permission
        if not user_has_permission(user_id, 'donation:create'):
            log_audit_event(
                user_id=user_id,
                action='CREATE_DONATION',
                resource_type='Donation',
                resource_id=None,
                status='Denied',
                reason_if_denied='Missing permission: donation:create'
            )
            return False, None, 'Permission denied: donation:create'
        
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        # Verify donor exists
        cursor.execute("SELECT blood_group FROM Donors WHERE id = %s", (donor_id,))
        donor = cursor.fetchone()
        if not donor:
            return False, None, 'Donor not found'
        
        blood_group = donor['blood_group']
        
        # Insert donation
        cursor.execute("""
            INSERT INTO Donations (donor_id, units, donation_date, blood_group)
            VALUES (%s, %s, %s, %s)
        """, (donor_id, units, donation_date, blood_group))
        
        donation_id = cursor.lastrowid
        conn.commit()
        
        # Audit log
        log_audit_event(
            user_id=user_id,
            action='CREATE_DONATION',
            resource_type='Donation',
            resource_id=donation_id,
            new_value={'donor_id': donor_id, 'units': units, 'blood_group': blood_group},
            status='Success'
        )
        
        cursor.close()
        conn.close()
        
        return True, donation_id, 'Donation recorded successfully. Inventory updated automatically.'
        
    except Error as e:
        logger.error(f"Error recording donation: {e}")
        return False, None, f'Database error: {str(e)}'


# ==================== HOSPITAL SELF-SERVICE REQUEST ====================

def create_blood_request_hospital(hospital_id, blood_group, units_required, user_id):
    """
    SECURE Blood Request by Hospital
    
    Business Rules:
    - Only HOSPITAL_USER with assigned hospital can create
    - Can ONLY create for their OWN hospital
    - Cannot request more than reasonable limits (e.g., max 50 units)
    - Must have permission: 'request:create'
    
    Returns:
        (success, request_id, message)
    """
    try:
        # Check permission and hospital assignment
        can_create, assigned_hospital_id, denial_reason = can_create_blood_request(user_id)
        
        if not can_create:
            log_audit_event(
                user_id=user_id,
                action='CREATE_REQUEST',
                resource_type='BloodRequest',
                resource_id=None,
                status='Denied',
                reason_if_denied=denial_reason
            )
            return False, None, denial_reason
        
        # Security: Ensure hospital matches assignment
        if hospital_id != assigned_hospital_id:
            log_audit_event(
                user_id=user_id,
                action='CREATE_REQUEST',
                resource_type='BloodRequest',
                resource_id=None,
                status='Denied',
                reason_if_denied='Attempting to create request for different hospital'
            )
            return False, None, 'You can only create requests for your assigned hospital'
        
        # Validate units (reasonable limit)
        if units_required < 1 or units_required > 50:
            return False, None, 'Units must be between 1 and 50'
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Insert request
        cursor.execute("""
            INSERT INTO Blood_Requests 
            (hospital_id, blood_group, units_required, status, created_by)
            VALUES (%s, %s, %s, 'Pending', %s)
        """, (hospital_id, blood_group, units_required, user_id))
        
        request_id = cursor.lastrowid
        conn.commit()
        
        # Audit log
        log_audit_event(
            user_id=user_id,
            action='CREATE_REQUEST',
            resource_type='BloodRequest',
            resource_id=request_id,
            new_value={
                'hospital_id': hospital_id,
                'blood_group': blood_group,
                'units_required': units_required
            },
            status='Success'
        )
        
        cursor.close()
        conn.close()
        
        return True, request_id, 'Request created. Blood Bank will review and approve/reject.'
        
    except Error as e:
        logger.error(f"Error creating blood request: {e}")
        return False, None, f'Database error: {str(e)}'


# ==================== SECURE ROUTES ====================

def register_secure_routes(app):
    """
    Register all RBAC-secured routes to Flask app
    Call this in main app.py: register_secure_routes(app)
    """
    
    # ===== Authentication Routes =====
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """Login with RBAC support"""
        should_render = login_user(app)
        if should_render:
            return render_template('login.html')
        return redirect(url_for('index'))
    
    @app.route('/logout')
    def logout():
        """Logout with audit logging"""
        return logout_user()
    
    # ===== Secure Donation Routes =====
    
    @app.route('/add-donation', methods=['GET', 'POST'])
    @permission_required('donation:create')
    def add_donation():
        """Record new donation (STAFF_MEMBER, BLOOD_BANK_ADMIN, SUPER_ADMIN only)"""
        user_id = session.get('user_id')
        
        if request.method == 'POST':
            try:
                donor_id = int(request.form.get('donor_id'))
                units = int(request.form.get('units'))
                donation_date = request.form.get('date')
                
                success, donation_id, message = record_donation_secure(
                    donor_id, units, donation_date, user_id
                )
                
                if success:
                    flash(message, 'success')
                    return redirect(url_for('view_donations'))
                else:
                    flash(message, 'danger')
            
            except ValueError as e:
                flash(f'Invalid input: {str(e)}', 'danger')
            except Exception as e:
                flash(f'Error: {str(e)}', 'danger')
        
        # Get donors for dropdown
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name, blood_group FROM Donors WHERE status = 'Active'")
        donors = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return render_template('add_donation.html', donors=donors)
    
    # ===== Secure Request Approval =====
    
    @app.route('/update-request/<int:request_id>/<status>', methods=['GET', 'POST'])
    @permission_required('request:approve')
    def update_request_status(request_id, status):
        """
        Approve or reject blood request
        SECURITY:
        - Only BLOOD_BANK_ADMIN or SUPER_ADMIN
        - Cannot approve own hospital's requests
        - All actions audited
        """
        success, message, changes = update_request_status_secure(request_id, status)
        
        if success:
            flash(message, 'success')
        else:
            flash(message, 'danger')
        
        return redirect(url_for('view_requests'))
    
    # ===== Secure Hospital Self-Service =====
    
    @app.route('/blood-request', methods=['GET', 'POST'])
    @permission_required('request:create')
    def blood_request():
        """
        Hospital staff create blood request
        SECURITY:
        - Only HOSPITAL_USER
        - Only for their assigned hospital
        - Cannot approve own requests
        """
        user_id = session.get('user_id')
        user_info = get_current_user_info()
        
        if not user_info or not user_info['hospital_id']:
            flash('Hospital not assigned to your account', 'danger')
            return redirect(url_for('index'))
        
        hospital_id = user_info['hospital_id']
        
        if request.method == 'POST':
            try:
                blood_group = request.form.get('blood_group')
                units = int(request.form.get('units'))
                
                success, req_id, message = create_blood_request_hospital(
                    hospital_id, blood_group, units, user_id
                )
                
                if success:
                    flash(message, 'success')
                    return redirect(url_for('view_requests'))
                else:
                    flash(message, 'danger')
            
            except ValueError:
                flash('Invalid units entered', 'danger')
            except Exception as e:
                flash(f'Error: {str(e)}', 'danger')
        
        # Get available blood groups
        blood_groups = ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-']
        return render_template('make_request.html', 
                             hospital_name=user_info['full_name'],
                             blood_groups=blood_groups)
    
    # ===== Audit Log Route =====
    
    @app.route('/audit-logs')
    @permission_required('audit:read')
    def view_audit_logs():
        """
        View audit logs
        SECURITY:
        - SUPER_ADMIN and BLOOD_BANK_ADMIN see all logs
        - Regular users see only their own logs (via audit:read_self)
        """
        user_id = session.get('user_id')
        user_info = get_current_user_info()
        
        # Check if super admin can view all logs
        if 'audit:read' in get_user_permissions(user_id):
            logs = get_audit_logs(user_id=None, days=90, limit=500)
            all_logs = True
        else:
            logs = get_audit_logs(user_id=user_id, days=30, limit=100)
            all_logs = False
        
        return render_template('audit_logs.html', logs=logs, all_logs=all_logs)
    
    # ===== View Requests (with security) =====
    
    @app.route('/requests')
    def view_requests():
        """
        View blood requests
        SECURITY:
        - BLOOD_BANK_ADMIN sees ALL requests
        - HOSPITAL_USER sees only their hospital's requests
        """
        user_id = session.get('user_id')
        user_info = get_current_user_info()
        
        if not user_info:
            return redirect(url_for('login'))
        
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        # Filter based on role
        if user_info['role_name'] in ['BLOOD_BANK_ADMIN', 'SUPER_ADMIN']:
            # Can see all requests
            cursor.execute("""
                SELECT br.id, h.name as hospital_name, br.blood_group, 
                       br.units_required, br.status, br.request_date,
                       COALESCE(u.full_name, 'Unknown') as approved_by_name
                FROM Blood_Requests br
                JOIN Hospitals h ON br.hospital_id = h.id
                LEFT JOIN Users_RBAC u ON br.approved_by = u.id
                ORDER BY br.request_date DESC
            """)
            can_approve = True
        else:
            # Hospital users see only their own requests
            cursor.execute("""
                SELECT br.id, h.name as hospital_name, br.blood_group, 
                       br.units_required, br.status, br.request_date
                FROM Blood_Requests br
                JOIN Hospitals h ON br.hospital_id = h.id
                WHERE h.id = %s
                ORDER BY br.request_date DESC
            """, (user_info['hospital_id'],))
            can_approve = False
        
        requests = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return render_template('view_requests.html', 
                             requests=requests, 
                             can_approve=can_approve,
                             user_role=user_info['role_name'])
