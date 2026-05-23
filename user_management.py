"""
USER MANAGEMENT & ROLE-BASED DASHBOARD SYSTEM
Blood Bank Management System

This module provides:
1. User management (create, edit, deactivate users)
2. Role assignment and management
3. Role-specific dashboard views
4. User permissions enforcement

Author: Blood Bank Admin Team
Version: 2.0.0
"""

import mysql.connector
from mysql.connector import Error
from datetime import datetime, date, timedelta
import logging
import os
from typing import Tuple, Dict, List, Optional
from db_config import get_db_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CONFIG = {
    **get_db_config()
}

BLOOD_GROUPS = ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-']

def get_db():
    """Get database connection"""
    return mysql.connector.connect(**DB_CONFIG)


def column_exists(cursor, table_name: str, column_name: str) -> bool:
    """Check if a column exists in current DB schema."""
    cursor.execute(
        """
        SELECT COUNT(*) as cnt
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (DB_CONFIG['database'], table_name, column_name)
    )
    row = cursor.fetchone()
    if isinstance(row, dict):
        return (row.get('cnt') or 0) > 0
    return (row[0] if row else 0) > 0


def table_exists(cursor, table_name: str) -> bool:
    """Check if a table exists in current DB schema."""
    cursor.execute(
        """
        SELECT COUNT(*) as cnt
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = %s
        """,
        (DB_CONFIG['database'], table_name)
    )
    row = cursor.fetchone()
    if isinstance(row, dict):
        return (row.get('cnt') or 0) > 0
    return (row[0] if row else 0) > 0


def get_batch_inventory_summary(cursor) -> List[Dict]:
    """Compute inventory totals from blood_batches."""
    if not table_exists(cursor, 'blood_batches'):
        return []

    cursor.execute(
        """
        SELECT
            blood_group,
            SUM(CASE WHEN expiry_date > CURDATE() AND status = 'Active' THEN units_remaining ELSE 0 END) as total_units,
            SUM(CASE WHEN expiry_date > CURDATE()
                      AND expiry_date <= DATE_ADD(CURDATE(), INTERVAL 5 DAY)
                      AND status = 'Active' THEN units_remaining ELSE 0 END) as near_expiry_units,
            SUM(CASE WHEN expiry_date <= CURDATE() OR status = 'Expired' THEN units_remaining ELSE 0 END) as expired_units
        FROM blood_batches
        GROUP BY blood_group
        """
    )
    rows = cursor.fetchall() or []
    summary_map = {row['blood_group']: row for row in rows}

    summary = []
    for group in BLOOD_GROUPS:
        row = summary_map.get(group, {})
        total_units = int(row.get('total_units') or 0)
        near_expiry_units = int(row.get('near_expiry_units') or 0)
        expired_units = int(row.get('expired_units') or 0)
        summary.append({
            'blood_group': group,
            'quantity_units': total_units,
            'total_units': total_units,
            'near_expiry_units': near_expiry_units,
            'expired_units': expired_units
        })

    return summary


def get_available_units_for_group(cursor, blood_group: str) -> int:
    """Return available units for a blood group from batches."""
    if table_exists(cursor, 'blood_batches'):
        cursor.execute(
            """
            SELECT COALESCE(SUM(units_remaining), 0) as total_units
            FROM blood_batches
            WHERE blood_group = %s
              AND expiry_date > CURDATE()
              AND status = 'Active'
            """,
            (blood_group,)
        )
        row = cursor.fetchone() or {}
        return int(row.get('total_units') or 0)
    return 0


# ==================== USER MANAGEMENT ====================

class UserManager:
    """
    Manages user creation, role assignment, and user lifecycle
    Only SUPER_ADMIN can access most of these functions
    """
    
    @staticmethod
    def create_user(
        username: str,
        email: str,
        password_hash: str,
        role_id: int,
        hospital_id: Optional[int] = None,
        created_by_user_id: int = None
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Create a new user with assigned role
        
        Args:
            username: Username
            email: Email address
            password_hash: Hashed password (bcrypt)
            role_id: Role ID to assign
            hospital_id: Hospital ID (for HOSPITAL_USER and STAFF_MEMBER)
            created_by_user_id: User ID of the admin creating this user
        
        Returns:
            (success, message, user_id)
        """
        try:
            conn = get_db()
            cursor = conn.cursor()
            
            # Check if user already exists
            cursor.execute("SELECT id FROM Users_RBAC WHERE email = %s OR username = %s",
                          (email, username))
            if cursor.fetchone():
                return False, "User already exists with this email or username", None
            
            # Validate role exists
            cursor.execute("SELECT id, role_name FROM Roles WHERE id = %s", (role_id,))
            role_row = cursor.fetchone()
            if not role_row:
                return False, "Invalid role ID", None
            role_name = role_row[1]
            
            # Insert user
            cursor.execute("""
                INSERT INTO Users_RBAC 
                (username, email, password_hash, role_id, hospital_id, is_active, created_at, created_by)
                VALUES (%s, %s, %s, %s, %s, TRUE, NOW(), %s)
            """, (username, email, password_hash, role_id, hospital_id, created_by_user_id))
            user_id = cursor.lastrowid

            donor_profile_auto_created = False

            # For DONOR users, auto-link (or auto-create) donor profile to prevent dashboard-link issues.
            if (
                role_name == 'DONOR'
                and column_exists(cursor, 'Users_RBAC', 'donor_id')
                and table_exists(cursor, 'Donors')
            ):
                donor_id = None
                donors_has_email = column_exists(cursor, 'Donors', 'email')

                if donors_has_email and email:
                    cursor.execute("SELECT id FROM Donors WHERE email = %s LIMIT 1", (email,))
                    row = cursor.fetchone()
                    if row:
                        donor_id = row[0]

                if not donor_id and username:
                    cursor.execute("SELECT id FROM Donors WHERE name = %s LIMIT 1", (username,))
                    row = cursor.fetchone()
                    if row:
                        donor_id = row[0]

                if not donor_id and username and username.lower().startswith('donor'):
                    suffix = username[5:]
                    if suffix.isdigit():
                        cursor.execute("SELECT id FROM Donors WHERE id = %s LIMIT 1", (int(suffix),))
                        row = cursor.fetchone()
                        if row:
                            donor_id = row[0]

                if not donor_id and username:
                    token = username.strip().split()[0] if username.strip() else ''
                    if token:
                        cursor.execute(
                            "SELECT id FROM Donors WHERE LOWER(name) LIKE LOWER(%s) ORDER BY id LIMIT 2",
                            (f"{token}%",)
                        )
                        rows = cursor.fetchall() or []
                        if len(rows) == 1:
                            donor_id = rows[0][0]

                if not donor_id and email and '@' in email:
                    local_part = email.split('@', 1)[0].strip()
                    if local_part:
                        cursor.execute(
                            "SELECT id FROM Donors WHERE LOWER(name) LIKE LOWER(%s) ORDER BY id LIMIT 2",
                            (f"{local_part}%",)
                        )
                        rows = cursor.fetchall() or []
                        if len(rows) == 1:
                            donor_id = rows[0][0]

                if not donor_id:
                    # Create a minimal donor profile if no matching donor exists.
                    phone_number = str(9900000000 + int(user_id))
                    while True:
                        cursor.execute("SELECT id FROM Donors WHERE phone = %s LIMIT 1", (phone_number,))
                        if not cursor.fetchone():
                            break
                        phone_number = str(int(phone_number) + 1000)

                    donor_columns = ['name', 'age', 'blood_group', 'phone']
                    donor_values = [username, 21, 'O+', phone_number]

                    if column_exists(cursor, 'Donors', 'gender'):
                        donor_columns.append('gender')
                        donor_values.append('Not Specified')
                    if donors_has_email:
                        donor_columns.append('email')
                        donor_values.append(email or None)
                    if column_exists(cursor, 'Donors', 'address'):
                        donor_columns.append('address')
                        donor_values.append(None)
                    if column_exists(cursor, 'Donors', 'availability'):
                        donor_columns.append('availability')
                        donor_values.append('Available')
                    if column_exists(cursor, 'Donors', 'status'):
                        donor_columns.append('status')
                        donor_values.append('Active')

                    placeholders = ", ".join(["%s"] * len(donor_values))
                    cursor.execute(
                        f"INSERT INTO Donors ({', '.join(donor_columns)}) VALUES ({placeholders})",
                        tuple(donor_values)
                    )
                    donor_id = cursor.lastrowid
                    donor_profile_auto_created = True

                cursor.execute(
                    "UPDATE Users_RBAC SET donor_id = %s WHERE id = %s",
                    (donor_id, user_id)
                )

            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"User created: {username} (ID: {user_id}) with role_id: {role_id}")
            if donor_profile_auto_created:
                return True, f"User '{username}' created successfully (donor profile auto-created and linked)", user_id
            return True, f"User '{username}' created successfully", user_id
            
        except Error as e:
            logger.error(f"Error creating user: {e}")
            return False, f"Database error: {str(e)}", None
    
    @staticmethod
    def get_all_users() -> List[Dict]:
        """
        Get list of all users with their roles
        SUPER_ADMIN only
        
        Returns: List of user dictionaries
        """
        try:
            conn = get_db()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT 
                    u.id,
                    u.username,
                    u.email,
                    r.role_name,
                    h.name as hospital_name,
                    u.is_active,
                    u.created_at,
                    u.last_login,
                    u.failed_login_attempts
                FROM Users_RBAC u
                LEFT JOIN Roles r ON u.role_id = r.id
                LEFT JOIN Hospitals h ON u.hospital_id = h.id
                ORDER BY u.created_at DESC
            """)
            
            users = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return users if users else []
            
        except Error as e:
            logger.error(f"Error fetching users: {e}")
            return []
    
    @staticmethod
    def get_user_by_id(user_id: int) -> Optional[Dict]:
        """
        Get user details by ID
        
        Returns: User dictionary or None
        """
        try:
            conn = get_db()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT 
                    u.id,
                    u.username,
                    u.email,
                    u.role_id,
                    r.role_name,
                    u.hospital_id,
                    h.name as hospital_name,
                    u.is_active,
                    u.created_at,
                    u.last_login,
                    u.failed_login_attempts
                FROM Users_RBAC u
                LEFT JOIN Roles r ON u.role_id = r.id
                LEFT JOIN Hospitals h ON u.hospital_id = h.id
                WHERE u.id = %s
            """, (user_id,))
            
            user = cursor.fetchone()
            if not user:
                cursor.close()
                conn.close()
                return None

            cursor.execute("""
                SELECT p.permission_name, p.description
                FROM Role_Permissions rp
                JOIN Permissions p ON rp.permission_id = p.id
                WHERE rp.role_id = %s
                ORDER BY p.permission_name
            """, (user['role_id'],))
            user['role_permissions'] = cursor.fetchall() or []

            cursor.execute("""
                SELECT
                    action,
                    CONCAT(
                        resource_type,
                        IF(resource_id IS NULL, '', CONCAT(' #', resource_id)),
                        IF(reason_if_denied IS NULL, '', CONCAT(' - ', reason_if_denied))
                    ) as description,
                    created_at as timestamp
                FROM Audit_Logs
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 20
            """, (user_id,))
            user['activity_logs'] = cursor.fetchall() or []

            cursor.close()
            conn.close()
            
            return user
            
        except Error as e:
            logger.error(f"Error fetching user {user_id}: {e}")
            return None
    
    @staticmethod
    def update_user_role(user_id: int, new_role_id: int) -> Tuple[bool, str]:
        """
        Change user's role
        SUPER_ADMIN only
        
        Returns: (success, message)
        """
        try:
            conn = get_db()
            cursor = conn.cursor()
            
            # Validate role exists
            cursor.execute("SELECT id FROM Roles WHERE id = %s", (new_role_id,))
            if not cursor.fetchone():
                return False, "Invalid role ID"
            
            # Update user role
            cursor.execute(
                "UPDATE Users_RBAC SET role_id = %s WHERE id = %s",
                (new_role_id, user_id)
            )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"User {user_id} role changed to {new_role_id}")
            return True, "User role updated successfully"
            
        except Error as e:
            logger.error(f"Error updating user role: {e}")
            return False, f"Database error: {str(e)}"
    
    @staticmethod
    def deactivate_user(user_id: int) -> Tuple[bool, str]:
        """
        Deactivate user (don't delete, just mark inactive)
        SUPER_ADMIN only
        
        Returns: (success, message)
        """
        try:
            conn = get_db()
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE Users_RBAC SET is_active = FALSE WHERE id = %s",
                (user_id,)
            )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"User {user_id} deactivated")
            return True, "User deactivated successfully"
            
        except Error as e:
            logger.error(f"Error deactivating user: {e}")
            return False, f"Database error: {str(e)}"
    
    @staticmethod
    def reactivate_user(user_id: int) -> Tuple[bool, str]:
        """
        Reactivate user
        SUPER_ADMIN only
        
        Returns: (success, message)
        """
        try:
            conn = get_db()
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE Users_RBAC SET is_active = TRUE WHERE id = %s",
                (user_id,)
            )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"User {user_id} reactivated")
            return True, "User reactivated successfully"
            
        except Error as e:
            logger.error(f"Error reactivating user: {e}")
            return False, f"Database error: {str(e)}"
    
    @staticmethod
    def reset_failed_login_attempts(user_id: int) -> Tuple[bool, str]:
        """Reset failed login attempts for a user"""
        try:
            conn = get_db()
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE Users_RBAC SET failed_login_attempts = 0 WHERE id = %s",
                (user_id,)
            )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True, "Failed login attempts reset"
            
        except Error as e:
            logger.error(f"Error resetting failed login attempts: {e}")
            return False, f"Database error: {str(e)}"


# ==================== ROLE MANAGEMENT ====================

class RoleManager:
    """
    Manages roles and their permissions
    Only SUPER_ADMIN can access
    """
    
    @staticmethod
    def get_all_roles() -> List[Dict]:
        """Get list of all roles"""
        try:
            conn = get_db()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT 
                    id,
                    role_name,
                    description,
                    is_active,
                    created_at
                FROM Roles
                ORDER BY role_name
            """)
            
            roles = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return roles if roles else []
            
        except Error as e:
            logger.error(f"Error fetching roles: {e}")
            return []
    
    @staticmethod
    def get_role_by_id(role_id: int) -> Optional[Dict]:
        """Get role details with permissions"""
        try:
            conn = get_db()
            cursor = conn.cursor(dictionary=True)
            
            # Get role info
            cursor.execute(
                "SELECT id, role_name, description FROM Roles WHERE id = %s",
                (role_id,)
            )
            role = cursor.fetchone()
            
            if not role:
                return None
            
            # Get permissions for this role
            cursor.execute("""
                SELECT p.id, p.permission_name, p.description
                FROM Permissions p
                JOIN Role_Permissions rp ON p.id = rp.permission_id
                WHERE rp.role_id = %s
            """, (role_id,))
            
            permissions = cursor.fetchall()
            role['permissions'] = permissions if permissions else []
            
            cursor.close()
            conn.close()
            
            return role
            
        except Error as e:
            logger.error(f"Error fetching role {role_id}: {e}")
            return None
    
    @staticmethod
    def get_eligible_hospitals() -> List[Dict]:
        """Get list of hospitals for user assignment"""
        try:
            conn = get_db()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT id, name, contact, address
                FROM Hospitals
                ORDER BY name
            """)
            
            hospitals = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return hospitals if hospitals else []
            
        except Error as e:
            logger.error(f"Error fetching hospitals: {e}")
            return []


# ==================== DASHBOARD DATA ====================

class DashboardManager:
    """
    Provides role-specific dashboard data
    """
    
    @staticmethod
    def get_super_admin_dashboard(user_id: int) -> Dict:
        """
        SUPER_ADMIN Dashboard
        Shows: System-level overview
        """
        try:
            conn = get_db()
            cursor = conn.cursor(dictionary=True)

            total_blood_banks = 1
            if table_exists(cursor, 'Blood_Banks'):
                cursor.execute("SELECT COUNT(*) as count FROM Blood_Banks")
                total_blood_banks = cursor.fetchone()['count'] or 0

            cursor.execute("SELECT COUNT(*) as count FROM Hospitals")
            total_hospitals = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM Donors")
            total_donors = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM Users_RBAC")
            total_users = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM Blood_Requests WHERE status = 'Pending'")
            pending_requests = cursor.fetchone()['count']

            active_sessions = None

            cursor.execute("""
                SELECT
                    u.id,
                    u.username,
                    u.email,
                    r.role_name,
                    u.is_active,
                    u.last_login,
                    u.failed_login_attempts
                FROM Users_RBAC u
                LEFT JOIN Roles r ON u.role_id = r.id
                ORDER BY u.created_at DESC
            """)
            users = cursor.fetchall() or []

            roles_with_permissions = []
            if table_exists(cursor, 'Roles'):
                cursor.execute("""
                    SELECT
                        r.id,
                        r.role_name,
                        r.description,
                        p.permission_name
                    FROM Roles r
                    LEFT JOIN Role_Permissions rp ON r.id = rp.role_id
                    LEFT JOIN Permissions p ON rp.permission_id = p.id
                    ORDER BY r.role_name, p.permission_name
                """)
                role_rows = cursor.fetchall() or []
                role_map = {}
                for row in role_rows:
                    role_id = row['id']
                    role_entry = role_map.get(role_id)
                    if not role_entry:
                        role_entry = {
                            'id': role_id,
                            'role_name': row['role_name'],
                            'description': row.get('description'),
                            'permissions': []
                        }
                        role_map[role_id] = role_entry
                    perm = row.get('permission_name')
                    if perm:
                        role_entry['permissions'].append(perm)
                roles_with_permissions = list(role_map.values())

            audit_logs = []
            if table_exists(cursor, 'Audit_Logs'):
                cursor.execute("""
                    SELECT
                        al.id,
                        u.username,
                        al.action,
                        al.resource_type,
                        al.resource_id,
                        al.status,
                        al.reason_if_denied,
                        al.created_at as timestamp
                    FROM Audit_Logs al
                    LEFT JOIN Users_RBAC u ON al.user_id = u.id
                    ORDER BY al.created_at DESC
                    LIMIT 25
                """)
                audit_logs = cursor.fetchall() or []

            cursor.close()
            conn.close()
            
            return {
                'role': 'SUPER_ADMIN',
                'total_blood_banks': total_blood_banks,
                'total_hospitals': total_hospitals,
                'total_donors': total_donors,
                'total_users': total_users,
                'pending_requests': pending_requests,
                'active_sessions': active_sessions,
                'users': users,
                'roles_with_permissions': roles_with_permissions,
                'audit_logs': audit_logs,
                'user_id': user_id
            }
            
        except Error as e:
            logger.error(f"Error getting SUPER_ADMIN dashboard: {e}")
            return {'error': str(e), 'role': 'SUPER_ADMIN'}
    
    @staticmethod
    def get_blood_bank_admin_dashboard(user_id: int) -> Dict:
        """
        BLOOD_BANK_ADMIN Dashboard
        Shows: Operational data
        """
        try:
            conn = get_db()
            cursor = conn.cursor(dictionary=True)

            inventory = get_batch_inventory_summary(cursor)
            total_units_available = sum(int(item.get('total_units') or 0) for item in inventory)

            inventory_enriched = []
            critical_alerts = []
            for item in inventory:
                units = int(item.get('total_units') or 0)
                if units >= 20:
                    status_label = 'Available'
                    status_class = 'bg-success'
                elif units >= 5:
                    status_label = 'Low'
                    status_class = 'bg-warning text-dark'
                else:
                    status_label = 'Critical'
                    status_class = 'bg-danger'
                    critical_alerts.append(item)

                inventory_enriched.append({
                    **item,
                    'status_label': status_label,
                    'status_class': status_class
                })

            # Pending requests
            cursor.execute("""
                SELECT 
                    br.id, h.name as hospital_name,
                    br.blood_group, br.units_required, br.request_date
                FROM Blood_Requests br
                LEFT JOIN Hospitals h ON br.hospital_id = h.id
                WHERE br.status = 'Pending'
                ORDER BY br.request_date ASC
            """)
            pending_requests = cursor.fetchall() or []

            pending_blood_groups = sorted(
                {row.get('blood_group') for row in pending_requests if row.get('blood_group')}
            )

            # Today's donations
            cursor.execute("""
                SELECT COUNT(*) as total_count, COALESCE(SUM(units), 0) as total_units
                FROM Donations
                WHERE donation_date = CURDATE()
            """)
            today_stats = cursor.fetchone() or {}

            # Monthly donation analytics
            cursor.execute("""
                SELECT MONTH(donation_date) as month, COALESCE(SUM(units), 0) as total_units
                FROM Donations
                WHERE YEAR(donation_date) = YEAR(CURDATE())
                GROUP BY MONTH(donation_date)
                ORDER BY MONTH(donation_date)
            """)
            monthly_rows = cursor.fetchall() or []
            month_map = {
                int(row.get('month') or 0): int(row.get('total_units') or 0)
                for row in monthly_rows
                if row.get('month') is not None
            }
            monthly_donations = [month_map.get(month, 0) for month in range(1, 13)]

            # Request status analytics
            cursor.execute("""
                SELECT
                    SUM(status = 'Pending') as pending_count,
                    SUM(status = 'Approved') as approved_count,
                    SUM(status = 'Rejected') as rejected_count
                FROM Blood_Requests
            """)
            request_status_row = cursor.fetchone() or {}
            request_status = {
                'pending': int(request_status_row.get('pending_count') or 0),
                'approved': int(request_status_row.get('approved_count') or 0),
                'rejected': int(request_status_row.get('rejected_count') or 0)
            }

            # Recent donations
            cursor.execute("""
                SELECT 
                    d.id, d.blood_group, d.units, d.donation_date,
                    do.name as donor_name
                FROM Donations d
                LEFT JOIN Donors do ON d.donor_id = do.id
                ORDER BY d.donation_date DESC
                LIMIT 10
            """)
            recent_donations = cursor.fetchall() or []

            # Audit logs (recent)
            audit_logs = []
            if column_exists(cursor, 'Audit_Logs', 'created_at'):
                cursor.execute("""
                    SELECT 
                        al.id, u.username, al.action, al.resource_type, al.resource_id,
                        al.status, al.created_at
                    FROM Audit_Logs al
                    LEFT JOIN Users_RBAC u ON al.user_id = u.id
                    ORDER BY al.created_at DESC
                    LIMIT 10
                """)
                audit_logs = cursor.fetchall() or []

            cursor.close()
            conn.close()

            return {
                'role': 'BLOOD_BANK_ADMIN',
                'user_id': user_id,
                'summary': {
                    'total_units': total_units_available,
                    'pending_requests_count': len(pending_requests),
                    'today_donations': int(today_stats.get('total_count') or 0),
                    'today_units': int(today_stats.get('total_units') or 0),
                    'critical_alerts_count': len(critical_alerts)
                },
                'inventory': inventory_enriched,
                'pending_requests': pending_requests,
                'pending_blood_groups': pending_blood_groups,
                'critical_alerts': critical_alerts,
                'recent_donations': recent_donations,
                'audit_logs': audit_logs,
                'analytics': {
                    'monthly_donations': monthly_donations,
                    'request_status': request_status,
                    'blood_group_distribution': [
                        {
                            'blood_group': item.get('blood_group'),
                            'units': int(item.get('total_units') or 0)
                        }
                        for item in inventory_enriched
                    ]
                }
            }
            
        except Error as e:
            logger.error(f"Error getting BLOOD_BANK_ADMIN dashboard: {e}")
            return {'error': str(e), 'role': 'BLOOD_BANK_ADMIN'}

    @staticmethod
    def get_staff_member_dashboard(user_id: int) -> Dict:
        """
        STAFF_MEMBER Dashboard
        Shows: Data entry and donation operations
        """
        try:
            conn = get_db()
            cursor = conn.cursor(dictionary=True)

            # Donor list (active + inactive for visibility)
            cursor.execute("""
                SELECT
                    id, name, blood_group, phone, gender,
                    last_donation_date, status
                FROM Donors
                ORDER BY name
            """)
            donors = cursor.fetchall() or []

            # Summary counts
            cursor.execute("SELECT COUNT(*) as count FROM Donors")
            total_donors = cursor.fetchone()['count']

            cursor.execute("""
                SELECT COUNT(*) as count
                FROM Donations
                WHERE donation_date = CURDATE()
            """)
            todays_donations = cursor.fetchone()['count']

            cursor.execute("""
                SELECT COUNT(*) as count
                FROM Donors
                WHERE status = 'Active'
                  AND (last_donation_date IS NULL
                       OR last_donation_date <= DATE_SUB(CURDATE(), INTERVAL 90 DAY))
            """)
            eligible_donors = cursor.fetchone()['count']

            inventory_summary = get_batch_inventory_summary(cursor)
            low_stock = [item for item in inventory_summary if (item.get('total_units') or 0) < 5]
            low_stock_count = len(low_stock)

            # Donation history (recent)
            cursor.execute("""
                SELECT
                    d.id, d.blood_group, d.units, d.donation_date,
                    do.name as donor_name
                FROM Donations d
                LEFT JOIN Donors do ON d.donor_id = do.id
                ORDER BY d.donation_date DESC
                LIMIT 100
            """)
            donations_recent = cursor.fetchall() or []

            cursor.close()
            conn.close()

            return {
                'role': 'STAFF_MEMBER',
                'summary': {
                    'total_donors': total_donors,
                    'todays_donations': todays_donations,
                    'eligible_donors': eligible_donors,
                    'low_stock_count': low_stock_count
                },
                'donors': donors,
                'low_stock': low_stock,
                'donations_recent': donations_recent,
                'user_id': user_id
            }

        except Error as e:
            logger.error(f"Error getting STAFF_MEMBER dashboard: {e}")
            return {'error': str(e), 'role': 'STAFF_MEMBER'}

    @staticmethod
    def get_hospital_user_dashboard(user_id: int) -> Dict:
        """
        HOSPITAL_USER Dashboard
        Shows: Hospital-specific data with limited visibility
        """
        try:
            conn = get_db()
            cursor = conn.cursor(dictionary=True)

            # Get user's hospital
            cursor.execute("SELECT hospital_id FROM Users_RBAC WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            hospital_id = user['hospital_id'] if user else None

            if not hospital_id:
                return {
                    'role': 'HOSPITAL_USER',
                    'error': 'Hospital not assigned',
                    'user_id': user_id
                }

            # Hospital info
            cursor.execute(
                "SELECT id, name, contact, email, address FROM Hospitals WHERE id = %s",
                (hospital_id,)
            )
            hospital_info = cursor.fetchone()

            # Blood availability (generic status, no unit counts)
            availability_rows = get_batch_inventory_summary(cursor)
            availability = []
            for row in availability_rows:
                units = int(row.get('total_units') or 0)
                if units >= 20:
                    status_label = 'Available'
                    status_class = 'bg-success'
                elif units >= 5:
                    status_label = 'Low'
                    status_class = 'bg-warning text-dark'
                else:
                    status_label = 'Not Available'
                    status_class = 'bg-danger'
                availability.append({
                    'blood_group': row.get('blood_group'),
                    'status_label': status_label,
                    'status_class': status_class
                })

            has_urgency = column_exists(cursor, 'Blood_Requests', 'urgency')
            has_rejection_reason = column_exists(cursor, 'Blood_Requests', 'rejection_reason')

            select_fields = "id, blood_group, units_required, status, request_date, approval_date"
            if has_urgency:
                select_fields += ", urgency"
            else:
                select_fields += ", NULL as urgency"
            if has_rejection_reason:
                select_fields += ", rejection_reason"
            else:
                select_fields += ", NULL as rejection_reason"

            cursor.execute(f"""
                SELECT {select_fields}
                FROM Blood_Requests
                WHERE hospital_id = %s
                ORDER BY request_date DESC
            """, (hospital_id,))
            my_requests = cursor.fetchall() or []

            cursor.execute("""
                SELECT
                    SUM(status = 'Pending') as pending_count,
                    SUM(status = 'Approved') as approved_count,
                    SUM(status = 'Rejected') as rejected_count
                FROM Blood_Requests
                WHERE hospital_id = %s
            """, (hospital_id,))
            stats_row = cursor.fetchone() or {}
            pending_count = int(stats_row.get('pending_count') or 0)
            approved_count = int(stats_row.get('approved_count') or 0)
            rejected_count = int(stats_row.get('rejected_count') or 0)

            cursor.execute("""
                SELECT COALESCE(SUM(units_required), 0) as total_units
                FROM Blood_Requests
                WHERE hospital_id = %s
                  AND request_date >= DATE_FORMAT(CURDATE(), '%%Y-%%m-01')
            """, (hospital_id,))
            month_units = cursor.fetchone() or {}
            total_units_month = int(month_units.get('total_units') or 0)

            cursor.close()
            conn.close()

            return {
                'role': 'HOSPITAL_USER',
                'hospital_info': hospital_info,
                'availability': availability,
                'summary': {
                    'pending_count': pending_count,
                    'approved_count': approved_count,
                    'rejected_count': rejected_count,
                    'units_requested_month': total_units_month
                },
                'my_requests': my_requests,
                'has_urgency': has_urgency,
                'has_rejection_reason': has_rejection_reason,
                'user_id': user_id
            }

        except Error as e:
            logger.error(f"Error getting HOSPITAL_USER dashboard: {e}")
            return {'error': str(e), 'role': 'HOSPITAL_USER'}

    @staticmethod
    def get_donor_dashboard(user_id: int) -> Dict:
        """
        DONOR Dashboard
        Shows: Personal profile, eligibility status, availability, history, and request alerts
        """
        try:
            conn = get_db()
            cursor = conn.cursor(dictionary=True)

            # 1) Resolve logged-in user
            users_has_full_name = column_exists(cursor, 'Users_RBAC', 'full_name')
            user_select_fields = "id, username, email"
            if users_has_full_name:
                user_select_fields += ", full_name"

            cursor.execute(
                f"SELECT {user_select_fields} FROM Users_RBAC WHERE id = %s",
                (user_id,)
            )
            user = cursor.fetchone()
            if not user:
                cursor.close()
                conn.close()
                return {'role': 'DONOR', 'error': 'User not found', 'user_id': user_id}

            donors_has_email = column_exists(cursor, 'Donors', 'email')
            donors_has_availability = column_exists(cursor, 'Donors', 'availability')
            donors_has_address = column_exists(cursor, 'Donors', 'address')
            donors_has_profile_image_url = column_exists(cursor, 'Donors', 'profile_image_url')
            users_has_donor_id = column_exists(cursor, 'Users_RBAC', 'donor_id')

            # 2) Resolve donor profile linked to this user
            donor_id = None
            linked_donor_id = None
            if users_has_donor_id:
                cursor.execute("SELECT donor_id FROM Users_RBAC WHERE id = %s", (user_id,))
                donor_link = cursor.fetchone()
                if donor_link and donor_link.get('donor_id'):
                    donor_id = donor_link['donor_id']
                    linked_donor_id = donor_id

            if not donor_id and donors_has_email and user.get('email'):
                cursor.execute("SELECT id FROM Donors WHERE email = %s LIMIT 1", (user['email'],))
                by_email = cursor.fetchone()
                if by_email:
                    donor_id = by_email['id']

            if not donor_id:
                cursor.execute("SELECT id FROM Donors WHERE name = %s LIMIT 1", (user['username'],))
                by_name = cursor.fetchone()
                if by_name:
                    donor_id = by_name['id']

            # Common bootstrap pattern: usernames like donor1, donor2, ...
            if not donor_id and user.get('username'):
                raw_username = str(user.get('username')).strip()
                if raw_username.lower().startswith('donor'):
                    suffix = raw_username[5:]
                    if suffix.isdigit():
                        cursor.execute("SELECT id FROM Donors WHERE id = %s LIMIT 1", (int(suffix),))
                        by_id = cursor.fetchone()
                        if by_id:
                            donor_id = by_id['id']

            # Fallback to full_name match if available.
            if not donor_id and users_has_full_name and user.get('full_name'):
                cursor.execute("SELECT id FROM Donors WHERE name = %s LIMIT 1", (user['full_name'],))
                by_full_name = cursor.fetchone()
                if by_full_name:
                    donor_id = by_full_name['id']

            # Soft match by username prefix (unique only), e.g. "Jefrin" -> "Jefrin Issac".
            if not donor_id and user.get('username'):
                name_token = str(user.get('username')).strip().split()[0] if str(user.get('username')).strip() else ''
                if name_token:
                    cursor.execute(
                        """
                        SELECT id
                        FROM Donors
                        WHERE LOWER(name) LIKE LOWER(%s)
                        ORDER BY id
                        LIMIT 2
                        """,
                        (f"{name_token}%",)
                    )
                    token_matches = cursor.fetchall() or []
                    if len(token_matches) == 1:
                        donor_id = token_matches[0]['id']

            # Soft match by email local-part prefix (unique only).
            if not donor_id and user.get('email') and '@' in str(user.get('email')):
                local_part = str(user.get('email')).split('@', 1)[0].strip()
                if local_part:
                    cursor.execute(
                        """
                        SELECT id
                        FROM Donors
                        WHERE LOWER(name) LIKE LOWER(%s)
                        ORDER BY id
                        LIMIT 2
                        """,
                        (f"{local_part}%",)
                    )
                    email_matches = cursor.fetchall() or []
                    if len(email_matches) == 1:
                        donor_id = email_matches[0]['id']

            if not donor_id:
                cursor.close()
                conn.close()
                return {
                    'role': 'DONOR',
                    'error': 'Donor profile is not linked to this account yet.',
                    'user_id': user_id
                }

            donor_select_fields = """
                d.id, d.name, d.age, d.gender, d.blood_group,
                d.phone, d.last_donation_date, d.status, d.created_at
            """
            if donors_has_email:
                donor_select_fields += ", d.email"
            if donors_has_availability:
                donor_select_fields += ", d.availability"
            if donors_has_address:
                donor_select_fields += ", d.address"
            if donors_has_profile_image_url:
                donor_select_fields += ", d.profile_image_url"

            cursor.execute(
                f"SELECT {donor_select_fields} FROM Donors d WHERE d.id = %s",
                (donor_id,)
            )
            donor = cursor.fetchone()
            if not donor:
                cursor.close()
                conn.close()
                return {'role': 'DONOR', 'error': 'Donor profile not found', 'user_id': user_id}

            donor_email = donor.get('email') if donors_has_email else user.get('email')
            donor_availability = donor.get('availability') if donors_has_availability else (
                'Available' if donor.get('status') == 'Active' else 'Not Available'
            )
            donor_address = donor.get('address') if donors_has_address else None
            donor_profile_image_url = donor.get('profile_image_url') if donors_has_profile_image_url else None
            is_available = donor_availability == 'Available'
            donor_blood_group = donor.get('blood_group')

            # 3) Donation summary (90-day eligibility rule)
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total_donations,
                    COALESCE(SUM(units), 0) as total_units_donated,
                    MAX(donation_date) as last_donation_date
                FROM Donations
                WHERE donor_id = %s
                """,
                (donor_id,)
            )
            donation_summary = cursor.fetchone() or {}
            last_donation_date = donation_summary.get('last_donation_date')
            if isinstance(last_donation_date, datetime):
                last_donation_date = last_donation_date.date()

            if last_donation_date:
                next_eligible_date = last_donation_date + timedelta(days=90)
                is_eligible = date.today() >= next_eligible_date
            else:
                next_eligible_date = None
                is_eligible = True

            # Persist donor link for future lookups when possible.
            if users_has_donor_id and donor_id and not linked_donor_id:
                cursor.execute(
                    """
                    UPDATE Users_RBAC
                    SET donor_id = %s
                    WHERE id = %s AND (donor_id IS NULL OR donor_id = 0)
                    """,
                    (donor_id, user_id)
                )

            total_donations = int(donation_summary.get('total_donations') or 0)
            total_units_donated = int(donation_summary.get('total_units_donated') or 0)
            # Approximation commonly used in awareness campaigns.
            lives_saved = total_units_donated * 3

            # 4) Donation history (only this donor)
            cursor.execute(
                """
                SELECT
                    donation_date,
                    units,
                    'Red Lifeline Blood Bank' as hospital_name
                FROM Donations
                WHERE donor_id = %s
                ORDER BY donation_date DESC
                LIMIT 100
                """,
                (donor_id,)
            )
            history_rows = cursor.fetchall() or []
            donation_history = []
            for row in history_rows:
                donation_history.append({
                    'donation_date': row.get('donation_date'),
                    'hospital': row.get('hospital_name') or 'Red Lifeline Blood Bank',
                    'units': int(row.get('units') or 0),
                    'status': 'Completed'
                })

            # 5) Inventory alert for donor blood group
            current_units = get_available_units_for_group(
                cursor,
                donor_blood_group
            )
            urgent_threshold = 10
            urgent_need = current_units <= urgent_threshold

            # 6) Notifications from pending blood requests for donor blood group
            notifications = []
            if table_exists(cursor, 'Blood_Requests'):
                has_urgency = column_exists(cursor, 'Blood_Requests', 'urgency')
                has_notes = column_exists(cursor, 'Blood_Requests', 'notes')

                request_select = """
                    br.id as request_id,
                    br.blood_group,
                    br.units_required,
                    br.request_date,
                    h.name as hospital_name
                """
                if has_urgency:
                    request_select += ", br.urgency"
                else:
                    request_select += ", 'Normal' as urgency"
                if has_notes:
                    request_select += ", br.notes"
                else:
                    request_select += ", NULL as notes"

                request_order = "br.request_date ASC"
                if has_urgency:
                    request_order = """
                        CASE br.urgency
                            WHEN 'Critical' THEN 1
                            WHEN 'High' THEN 2
                            WHEN 'Normal' THEN 3
                            ELSE 4
                        END,
                        br.request_date ASC
                    """

                cursor.execute(
                    f"""
                    SELECT {request_select}
                    FROM Blood_Requests br
                    LEFT JOIN Hospitals h ON br.hospital_id = h.id
                    WHERE br.status = 'Pending'
                      AND br.blood_group = %s
                    ORDER BY {request_order}
                    LIMIT 5
                    """,
                    (donor_blood_group,)
                )
                pending_requests = cursor.fetchall() or []

                for req in pending_requests:
                    urgency = req.get('urgency') or 'Normal'
                    hospital_name = req.get('hospital_name') or 'Unknown Hospital'
                    notifications.append({
                        'request_id': req.get('request_id'),
                        'blood_group': req.get('blood_group'),
                        'units_required': int(req.get('units_required') or 0),
                        'hospital_name': hospital_name,
                        'request_date': req.get('request_date'),
                        'urgency': urgency,
                        'notes': req.get('notes') or '',
                        'message': f"{urgency} Request: {donor_blood_group} needed at {hospital_name}",
                        'is_urgent': urgency in ['Critical', 'High']
                    })

            urgent_notifications = [n for n in notifications if n.get('is_urgent')]
            top_notification = urgent_notifications[0] if urgent_notifications else (notifications[0] if notifications else None)

            # 7) Trend graph (recent donations)
            cursor.execute(
                """
                SELECT donation_date, units
                FROM Donations
                WHERE donor_id = %s
                ORDER BY donation_date DESC
                LIMIT 6
                """,
                (donor_id,)
            )
            recent_donations = cursor.fetchall() or []
            recent_donations.reverse()

            trend_labels = []
            trend_units = []
            for item in recent_donations:
                donation_date = item.get('donation_date')
                if isinstance(donation_date, datetime):
                    donation_date = donation_date.date()
                trend_labels.append(donation_date.strftime('%d %b') if donation_date else '')
                trend_units.append(int(item.get('units') or 0))

            conn.commit()
            cursor.close()
            conn.close()

            return {
                'role': 'DONOR',
                'user_id': user_id,
                'profile': {
                    'donor_id': donor['id'],
                    'full_name': donor.get('name'),
                    'blood_group': donor.get('blood_group'),
                    'age': donor.get('age'),
                    'phone': donor.get('phone'),
                    'email': donor_email,
                    'address': donor_address or 'Not provided',
                    'profile_image_url': donor_profile_image_url,
                    'status': donor.get('status'),
                    'availability': donor_availability,
                    'is_available': is_available
                },
                'summary': {
                    'total_donations': total_donations,
                    'last_donation_date': last_donation_date,
                    'total_units_donated': total_units_donated,
                    'lives_saved': lives_saved,
                    'is_eligible': is_eligible,
                    'next_eligible_date': next_eligible_date,
                    'last_donation_label': (
                        last_donation_date.strftime('%b %Y') if last_donation_date else 'Never'
                    )
                },
                'donation_history': donation_history,
                'notifications': notifications,
                'alerts': {
                    'urgent_need': bool(top_notification) or urgent_need,
                    'current_units': current_units,
                    'message': (
                        top_notification.get('message')
                        if top_notification
                        else f"Urgent need for {donor_blood_group} donors"
                    )
                },
                'trend': {
                    'labels': trend_labels,
                    'units': trend_units
                },
                'capabilities': {
                    'can': [
                        'Update profile',
                        'Mark availability',
                        'View donation history',
                        'Respond to urgent requests'
                    ],
                    'cannot': [
                        'See inventory',
                        'See other donors',
                        'Approve requests'
                    ]
                }
            }
            
        except Error as e:
            logger.error(f"Error getting DONOR dashboard: {e}")
            return {'error': str(e), 'role': 'DONOR'}
    
    @staticmethod
    def get_dashboard_for_role(user_id: int, role_name: str) -> Dict:
        """
        Get appropriate dashboard data based on user's role
        
        Returns: Role-specific dashboard dictionary
        """
        if role_name == 'SUPER_ADMIN':
            return DashboardManager.get_super_admin_dashboard(user_id)
        elif role_name == 'BLOOD_BANK_ADMIN':
            return DashboardManager.get_blood_bank_admin_dashboard(user_id)
        elif role_name == 'STAFF_MEMBER':
            return DashboardManager.get_staff_member_dashboard(user_id)
        elif role_name == 'HOSPITAL_USER':
            return DashboardManager.get_hospital_user_dashboard(user_id)
        elif role_name == 'DONOR':
            return DashboardManager.get_donor_dashboard(user_id)
        else:
            return {'error': f'Unknown role: {role_name}'}



