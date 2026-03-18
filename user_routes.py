"""
USER MANAGEMENT ROUTES - Flask Endpoints
For: User creation, role assignment, and role-specific dashboards

Author: Blood Bank Admin Team
Version: 2.0.0
"""

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash
from user_management import UserManager, RoleManager, DashboardManager
from rbac import permission_required, role_required, get_user_role
import logging
from datetime import date

logger = logging.getLogger(__name__)

# Create Blueprint
user_mgmt_bp = Blueprint('user_mgmt', __name__, url_prefix='/admin')

# ==================== SUPER_ADMIN: USER MANAGEMENT ====================

@user_mgmt_bp.route('/users', methods=['GET'])
@permission_required('admin:manage')
def list_users():
    """
    List all users
    SUPER_ADMIN only
    GET /admin/users
    """
    try:
        users = UserManager.get_all_users()
        
        if request.is_json:
            return jsonify({
                'success': True,
                'users': users,
                'total': len(users)
            }), 200
        else:
            # HTML response
            roles = RoleManager.get_all_roles()
            return render_template(
                'admin/user_list.html',
                users=users,
                roles=roles,
                title='User Management'
            )
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('index'))


@user_mgmt_bp.route('/users/create', methods=['GET', 'POST'])
@permission_required('admin:manage')
def create_user():
    """
    Create new user with role assignment
    SUPER_ADMIN only
    GET /admin/users/create - Show form
    POST /admin/users/create - Create user
    """
    try:
        if request.method == 'GET':
            # Show create user form
            roles = RoleManager.get_all_roles()
            hospitals = RoleManager.get_eligible_hospitals()
            
            if request.is_json:
                return jsonify({
                    'roles': roles,
                    'hospitals': hospitals
                }), 200
            else:
                return render_template(
                    'admin/create_user.html',
                    roles=roles,
                    hospitals=hospitals,
                    title='Create New User'
                )
        
        # POST: Create user
        data = request.get_json() if request.is_json else request.form
        
        # Validate input
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()
        role_id = int(data.get('role_id', 0))
        hospital_id = data.get('hospital_id')
        
        if not username or not email or not password or not role_id:
            error_msg = 'Missing required fields'
            if request.is_json:
                return jsonify({'error': error_msg}), 400
            flash(error_msg, 'danger')
            return redirect(url_for('user_mgmt.create_user'))
        
        # Convert hospital_id to int if provided, otherwise set to None
        if hospital_id and str(hospital_id).strip():
            try:
                hospital_id = int(hospital_id)
            except (ValueError, TypeError):
                hospital_id = None
        else:
            hospital_id = None
        
        # Hash password
        password_hash = generate_password_hash(password)
        
        # Create user
        creator_id = session.get('user_id')
        success, message, user_id = UserManager.create_user(
            username=username,
            email=email,
            password_hash=password_hash,
            role_id=role_id,
            hospital_id=hospital_id,
            created_by_user_id=creator_id
        )
        
        if success:
            logger.info(f"User created: {username} (ID: {user_id})")
            
            if request.is_json:
                return jsonify({
                    'success': True,
                    'message': message,
                    'user_id': user_id
                }), 201
            else:
                flash(f'✅ {message}', 'success')
                return redirect(url_for('user_mgmt.list_users'))
        else:
            logger.warning(f"Failed to create user: {message}")
            
            if request.is_json:
                return jsonify({
                    'success': False,
                    'error': message
                }), 400
            else:
                flash(f'❌ {message}', 'danger')
                return redirect(url_for('user_mgmt.create_user'))
    
    except Exception as e:
        logger.error(f"Error in create_user: {e}")
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('user_mgmt.create_user'))


@user_mgmt_bp.route('/users/<int:user_id>', methods=['GET'])
@permission_required('admin:manage')
def view_user(user_id):
    """
    View user details
    SUPER_ADMIN only
    GET /admin/users/<user_id>
    """
    try:
        user = UserManager.get_user_by_id(user_id)
        
        if not user:
            if request.is_json:
                return jsonify({'error': 'User not found'}), 404
            flash('User not found', 'danger')
            return redirect(url_for('user_mgmt.list_users'))
        
        if request.is_json:
            return jsonify({'success': True, 'user': user}), 200
        else:
            roles = RoleManager.get_all_roles()
            hospitals = RoleManager.get_eligible_hospitals()
            return render_template(
                'admin/user_detail.html',
                user=user,
                roles=roles,
                hospitals=hospitals,
                title=f'User: {user["username"]}'
            )
    except Exception as e:
        logger.error(f"Error viewing user: {e}")
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('user_mgmt.list_users'))


@user_mgmt_bp.route('/users/<int:user_id>/role', methods=['POST'])
@permission_required('admin:manage')
def update_user_role(user_id):
    """
    Update user's role
    SUPER_ADMIN only
    POST /admin/users/<user_id>/role
    Body: {role_id: <int>}
    """
    try:
        data = request.get_json() if request.is_json else request.form
        role_id = int(data.get('role_id', 0))
        
        if not role_id:
            error_msg = 'Role ID is required'
            if request.is_json:
                return jsonify({'error': error_msg}), 400
            flash(error_msg, 'danger')
            return redirect(url_for('user_mgmt.view_user', user_id=user_id))
        
        success, message = UserManager.update_user_role(user_id, role_id)
        
        if success:
            logger.info(f"User {user_id} role updated")
            if request.is_json:
                return jsonify({'success': True, 'message': message}), 200
            flash(f'✅ {message}', 'success')
        else:
            logger.warning(f"Failed to update user role: {message}")
            if request.is_json:
                return jsonify({'success': False, 'error': message}), 400
            flash(f'❌ {message}', 'danger')
        
        return redirect(url_for('user_mgmt.view_user', user_id=user_id))
    
    except Exception as e:
        logger.error(f"Error updating user role: {e}")
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('user_mgmt.view_user', user_id=user_id))


@user_mgmt_bp.route('/users/<int:user_id>/deactivate', methods=['POST'])
@permission_required('admin:manage')
def deactivate_user(user_id):
    """
    Deactivate user
    SUPER_ADMIN only
    POST /admin/users/<user_id>/deactivate
    """
    try:
        success, message = UserManager.deactivate_user(user_id)
        
        if success:
            logger.info(f"User {user_id} deactivated")
            if request.is_json:
                return jsonify({'success': True, 'message': message}), 200
            flash(f'✅ {message}', 'success')
        else:
            logger.warning(f"Failed to deactivate user: {message}")
            if request.is_json:
                return jsonify({'success': False, 'error': message}), 400
            flash(f'❌ {message}', 'danger')
        
        return redirect(url_for('user_mgmt.view_user', user_id=user_id))
    
    except Exception as e:
        logger.error(f"Error deactivating user: {e}")
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('user_mgmt.view_user', user_id=user_id))


@user_mgmt_bp.route('/users/<int:user_id>/reactivate', methods=['POST'])
@permission_required('admin:manage')
def reactivate_user(user_id):
    """
    Reactivate user
    SUPER_ADMIN only
    POST /admin/users/<user_id>/reactivate
    """
    try:
        success, message = UserManager.reactivate_user(user_id)
        
        if success:
            logger.info(f"User {user_id} reactivated")
            if request.is_json:
                return jsonify({'success': True, 'message': message}), 200
            flash(f'✅ {message}', 'success')
        else:
            logger.warning(f"Failed to reactivate user: {message}")
            if request.is_json:
                return jsonify({'success': False, 'error': message}), 400
            flash(f'❌ {message}', 'danger')
        
        return redirect(url_for('user_mgmt.view_user', user_id=user_id))
    
    except Exception as e:
        logger.error(f"Error reactivating user: {e}")
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('user_mgmt.view_user', user_id=user_id))


@user_mgmt_bp.route('/users/<int:user_id>/reset-login', methods=['POST'])
@permission_required('admin:manage')
def reset_failed_login(user_id):
    """
    Reset failed login attempts for a user
    SUPER_ADMIN only
    POST /admin/users/<user_id>/reset-login
    """
    try:
        success, message = UserManager.reset_failed_login_attempts(user_id)
        
        if success:
            if request.is_json:
                return jsonify({'success': True, 'message': message}), 200
            flash(f'✅ {message}', 'success')
        else:
            if request.is_json:
                return jsonify({'success': False, 'error': message}), 400
            flash(f'❌ {message}', 'danger')
        
        return redirect(url_for('user_mgmt.view_user', user_id=user_id))
    
    except Exception as e:
        logger.error(f"Error resetting failed login: {e}")
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('user_mgmt.view_user', user_id=user_id))


# ==================== ROLE-BASED DASHBOARDS ====================

@user_mgmt_bp.route('/dashboard', methods=['GET'])
def dashboard():
    """
    Role-based dashboard
    GET /admin/dashboard
    
    Returns different data based on user's role:
    - SUPER_ADMIN: System overview
    - BLOOD_BANK_ADMIN: Operational data
    - STAFF_MEMBER: Donation operations
    - HOSPITAL_USER: Hospital-specific requests
    - DONOR: Donation profile
    """
    try:
        user_id = session.get('user_id')
        if not user_id:
            return redirect(url_for('login'))
        
        # Get user's role
        role_id, role_name = get_user_role(user_id)
        if not role_name:
            flash('User role not found', 'danger')
            return redirect(url_for('logout'))
        
        # Get dashboard data for this role
        dashboard_data = DashboardManager.get_dashboard_for_role(user_id, role_name)
        
        if request.is_json:
            return jsonify(dashboard_data), 200
        else:
            # Return HTML template based on role
            template_map = {
                'SUPER_ADMIN': 'dashboard/super_admin_dashboard.html',
                'BLOOD_BANK_ADMIN': 'dashboard/blood_bank_admin_dashboard.html',
                'STAFF_MEMBER': 'dashboard/staff_member_dashboard.html',
                'HOSPITAL_USER': 'dashboard/hospital_user_dashboard.html',
                'DONOR': 'dashboard/donor_dashboard.html'
            }
            
            template_name = template_map.get(role_name, 'dashboard/default_dashboard.html')

            # Fallback gracefully when dashboard query and current DB schema are out of sync.
            if isinstance(dashboard_data, dict) and dashboard_data.get('error'):
                flash(
                    f'{role_name} dashboard is unavailable with current database schema: {dashboard_data["error"]}',
                    'warning'
                )
                template_name = 'dashboard/default_dashboard.html'
            
            return render_template(
                template_name,
                role=role_name,
                data=dashboard_data,
                dashboard_data=dashboard_data,
                donor_name=session.get('username'),
                now=date.today(),
                title=f'{role_name} Dashboard'
            )
    
    except Exception as e:
        logger.error(f"Error loading dashboard: {e}")
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        flash(f'Error loading dashboard: {str(e)}', 'danger')
        return redirect(url_for('index'))


@user_mgmt_bp.route('/dashboard/data', methods=['GET'])
def get_dashboard_data():
    """
    Get dashboard data as JSON (for AJAX)
    GET /admin/dashboard/data
    """
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
        
        role_id, role_name = get_user_role(user_id)
        if not role_name:
            return jsonify({'error': 'User role not found'}), 404
        
        dashboard_data = DashboardManager.get_dashboard_for_role(user_id, role_name)
        return jsonify(dashboard_data), 200
    
    except Exception as e:
        logger.error(f"Error fetching dashboard data: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== ROLE MANAGEMENT ====================

@user_mgmt_bp.route('/roles', methods=['GET'])
@permission_required('admin:manage')
def list_roles():
    """
    List all roles
    SUPER_ADMIN only
    GET /admin/roles
    """
    try:
        roles = RoleManager.get_all_roles()
        
        if request.is_json:
            return jsonify({
                'success': True,
                'roles': roles,
                'total': len(roles)
            }), 200
        else:
            return render_template(
                'admin/role_list.html',
                roles=roles,
                title='Role Management'
            )
    except Exception as e:
        logger.error(f"Error listing roles: {e}")
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('index'))


@user_mgmt_bp.route('/roles/<int:role_id>', methods=['GET'])
@permission_required('admin:manage')
def view_role(role_id):
    """
    View role details with permissions
    SUPER_ADMIN only
    GET /admin/roles/<role_id>
    """
    try:
        role = RoleManager.get_role_by_id(role_id)
        
        if not role:
            if request.is_json:
                return jsonify({'error': 'Role not found'}), 404
            flash('Role not found', 'danger')
            return redirect(url_for('user_mgmt.list_roles'))
        
        if request.is_json:
            return jsonify({'success': True, 'role': role}), 200
        else:
            return render_template(
                'admin/role_detail.html',
                role=role,
                title=f'Role: {role["role_name"]}'
            )
    except Exception as e:
        logger.error(f"Error viewing role: {e}")
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('user_mgmt.list_roles'))


# ==================== REGISTER BLUEPRINT ====================

def register_user_management_routes(app):
    """
    Register user management routes with Flask app
    
    Usage in app.py:
        from user_routes import register_user_management_routes
        register_user_management_routes(app)
    """
    app.register_blueprint(user_mgmt_bp)
    logger.info("User management routes registered successfully")
