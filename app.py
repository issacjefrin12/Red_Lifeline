"""
Blood Bank Management System - Flask Backend (MySQL Edition)
Author: Senior Full-Stack Developer
Version: 2.0 - MySQL Edition
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
import mysql.connector
from mysql.connector import Error
import os
from datetime import datetime, date, timedelta
from functools import wraps
from decimal import Decimal
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import secrets
import string
import hashlib
from transaction_lock_handler import approve_blood_request, InsufficientStockError, AlreadyProcessedError
from db_config import get_db_config

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('BBMS_SECRET_KEY', 'change-me-in-production')
app.config['SESSION_COOKIE_SECURE'] = os.getenv('BBMS_SESSION_COOKIE_SECURE', 'false').lower() == 'true'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)

# MySQL Database Configuration
DB_CONFIG = {
    **get_db_config()
}

BLOOD_GROUPS = ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-']
ALLOWED_PROFILE_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
DONOR_PROFILE_UPLOAD_DIR = os.path.join(app.root_path, 'static', 'uploads', 'donor_profiles')
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('BBMS_MAX_UPLOAD_MB', '5')) * 1024 * 1024


def allowed_profile_image_file(filename):
    """Return True if uploaded filename has an allowed image extension."""
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_PROFILE_IMAGE_EXTENSIONS


def remove_local_donor_profile_image(profile_image_url):
    """Remove locally stored donor profile image if it belongs to upload dir."""
    if not profile_image_url:
        return
    local_prefix = '/static/uploads/donor_profiles/'
    if not str(profile_image_url).startswith(local_prefix):
        return
    filename = os.path.basename(profile_image_url)
    if not filename:
        return
    absolute_path = os.path.join(DONOR_PROFILE_UPLOAD_DIR, filename)
    if os.path.isfile(absolute_path):
        try:
            os.remove(absolute_path)
        except OSError:
            pass


def save_donor_profile_image(file_storage, donor_id):
    """Save donor profile image and return public static path."""
    if not file_storage or not file_storage.filename:
        return None, None

    filename = secure_filename(file_storage.filename)
    if not allowed_profile_image_file(filename):
        allowed_list = ", ".join(sorted(ALLOWED_PROFILE_IMAGE_EXTENSIONS))
        return None, f"Invalid image type. Allowed: {allowed_list}."

    extension = filename.rsplit('.', 1)[1].lower()
    unique_name = f"donor_{donor_id}_{int(datetime.utcnow().timestamp())}_{secrets.token_hex(4)}.{extension}"
    os.makedirs(DONOR_PROFILE_UPLOAD_DIR, exist_ok=True)
    target_path = os.path.join(DONOR_PROFILE_UPLOAD_DIR, unique_name)
    file_storage.save(target_path)
    return f"/static/uploads/donor_profiles/{unique_name}", None


def table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        """,
        (DB_CONFIG['database'], table_name)
    )
    row = cursor.fetchone()
    if isinstance(row, dict):
        return (list(row.values())[0] if row else 0) > 0
    return (row[0] if row else 0) > 0


def column_exists(cursor, table_name, column_name):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (DB_CONFIG['database'], table_name, column_name)
    )
    row = cursor.fetchone()
    if isinstance(row, dict):
        return (list(row.values())[0] if row else 0) > 0
    return (row[0] if row else 0) > 0


def apply_schema_extensions(cursor):
    """Backfill optional columns used by donor/admin dashboards."""
    if table_exists(cursor, 'Donors'):
        if not column_exists(cursor, 'Donors', 'email'):
            cursor.execute("ALTER TABLE Donors ADD COLUMN email VARCHAR(255) NULL")
        if not column_exists(cursor, 'Donors', 'availability'):
            cursor.execute(
                "ALTER TABLE Donors ADD COLUMN availability VARCHAR(20) DEFAULT 'Available'"
            )
        if not column_exists(cursor, 'Donors', 'address'):
            cursor.execute("ALTER TABLE Donors ADD COLUMN address VARCHAR(255) NULL")
        if not column_exists(cursor, 'Donors', 'profile_image_url'):
            cursor.execute("ALTER TABLE Donors ADD COLUMN profile_image_url VARCHAR(500) NULL")
        if not column_exists(cursor, 'Donors', 'last_active_at'):
            cursor.execute("ALTER TABLE Donors ADD COLUMN last_active_at DATETIME NULL")

    if table_exists(cursor, 'Users_RBAC'):
        if not column_exists(cursor, 'Users_RBAC', 'donor_id'):
            cursor.execute("ALTER TABLE Users_RBAC ADD COLUMN donor_id INT NULL")

    if table_exists(cursor, 'Blood_Requests'):
        if not column_exists(cursor, 'Blood_Requests', 'urgency'):
            cursor.execute("ALTER TABLE Blood_Requests ADD COLUMN urgency VARCHAR(20) DEFAULT 'Normal'")
        if not column_exists(cursor, 'Blood_Requests', 'created_by'):
            cursor.execute("ALTER TABLE Blood_Requests ADD COLUMN created_by INT NULL")
        if not column_exists(cursor, 'Blood_Requests', 'approved_by'):
            cursor.execute("ALTER TABLE Blood_Requests ADD COLUMN approved_by INT NULL")
        if not column_exists(cursor, 'Blood_Requests', 'notes'):
            cursor.execute("ALTER TABLE Blood_Requests ADD COLUMN notes TEXT NULL")
        if not column_exists(cursor, 'Blood_Requests', 'rejection_reason'):
            cursor.execute("ALTER TABLE Blood_Requests ADD COLUMN rejection_reason TEXT NULL")


def ensure_rbac_schema(cursor):
    """Create RBAC tables and seed base roles/permissions if missing."""
    cursor.execute('''CREATE TABLE IF NOT EXISTS Roles (
        id INT PRIMARY KEY AUTO_INCREMENT,
        role_name VARCHAR(50) UNIQUE NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_active BOOLEAN DEFAULT TRUE
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Permissions (
        id INT PRIMARY KEY AUTO_INCREMENT,
        permission_name VARCHAR(100) UNIQUE NOT NULL,
        description TEXT,
        resource VARCHAR(50) NOT NULL,
        action VARCHAR(50) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Users_RBAC (
        id INT PRIMARY KEY AUTO_INCREMENT,
        username VARCHAR(100) UNIQUE NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        full_name VARCHAR(255) NOT NULL,
        role_id INT NOT NULL,
        hospital_id INT NULL,
        is_active BOOLEAN DEFAULT TRUE,
        is_locked BOOLEAN DEFAULT FALSE,
        failed_login_attempts INT DEFAULT 0,
        last_login DATETIME NULL,
        password_changed_at DATETIME NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (role_id) REFERENCES Roles(id),
        FOREIGN KEY (hospital_id) REFERENCES Hospitals(id) ON DELETE SET NULL
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Role_Permissions (
        role_id INT NOT NULL,
        permission_id INT NOT NULL,
        PRIMARY KEY (role_id, permission_id),
        FOREIGN KEY (role_id) REFERENCES Roles(id) ON DELETE CASCADE,
        FOREIGN KEY (permission_id) REFERENCES Permissions(id) ON DELETE CASCADE
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Audit_Logs (
        id INT PRIMARY KEY AUTO_INCREMENT,
        user_id INT NULL,
        action VARCHAR(100) NOT NULL,
        resource_type VARCHAR(50) NOT NULL,
        resource_id INT NULL,
        old_value JSON NULL,
        new_value JSON NULL,
        ip_address VARCHAR(45) NULL,
        user_agent VARCHAR(255) NULL,
        status VARCHAR(20) DEFAULT 'Success',
        reason_if_denied TEXT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES Users_RBAC(id) ON DELETE SET NULL
    )''')

    # Backfill missing columns for older RBAC schemas.
    if table_exists(cursor, 'Roles'):
        if not column_exists(cursor, 'Roles', 'description'):
            cursor.execute("ALTER TABLE Roles ADD COLUMN description TEXT NULL")
        if not column_exists(cursor, 'Roles', 'is_active'):
            cursor.execute("ALTER TABLE Roles ADD COLUMN is_active BOOLEAN DEFAULT TRUE")
        if not column_exists(cursor, 'Roles', 'created_at'):
            cursor.execute("ALTER TABLE Roles ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    if table_exists(cursor, 'Permissions'):
        if not column_exists(cursor, 'Permissions', 'description'):
            cursor.execute("ALTER TABLE Permissions ADD COLUMN description TEXT NULL")
        if not column_exists(cursor, 'Permissions', 'resource'):
            cursor.execute("ALTER TABLE Permissions ADD COLUMN resource VARCHAR(50) NOT NULL DEFAULT 'system'")
        if not column_exists(cursor, 'Permissions', 'action'):
            cursor.execute("ALTER TABLE Permissions ADD COLUMN action VARCHAR(50) NOT NULL DEFAULT 'manage'")
        if not column_exists(cursor, 'Permissions', 'created_at'):
            cursor.execute("ALTER TABLE Permissions ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    if table_exists(cursor, 'Users_RBAC'):
        if not column_exists(cursor, 'Users_RBAC', 'is_active'):
            cursor.execute("ALTER TABLE Users_RBAC ADD COLUMN is_active BOOLEAN DEFAULT TRUE")
        if not column_exists(cursor, 'Users_RBAC', 'is_locked'):
            cursor.execute("ALTER TABLE Users_RBAC ADD COLUMN is_locked BOOLEAN DEFAULT FALSE")
        if not column_exists(cursor, 'Users_RBAC', 'failed_login_attempts'):
            cursor.execute("ALTER TABLE Users_RBAC ADD COLUMN failed_login_attempts INT DEFAULT 0")
        if not column_exists(cursor, 'Users_RBAC', 'last_login'):
            cursor.execute("ALTER TABLE Users_RBAC ADD COLUMN last_login DATETIME NULL")
        if not column_exists(cursor, 'Users_RBAC', 'password_changed_at'):
            cursor.execute("ALTER TABLE Users_RBAC ADD COLUMN password_changed_at DATETIME NULL")
        if not column_exists(cursor, 'Users_RBAC', 'created_at'):
            cursor.execute("ALTER TABLE Users_RBAC ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        if not column_exists(cursor, 'Users_RBAC', 'updated_at'):
            cursor.execute("ALTER TABLE Users_RBAC ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")

    if table_exists(cursor, 'Audit_Logs'):
        if not column_exists(cursor, 'Audit_Logs', 'status'):
            cursor.execute("ALTER TABLE Audit_Logs ADD COLUMN status VARCHAR(20) DEFAULT 'Success'")
        if not column_exists(cursor, 'Audit_Logs', 'reason_if_denied'):
            cursor.execute("ALTER TABLE Audit_Logs ADD COLUMN reason_if_denied TEXT NULL")

    roles = [
        ('SUPER_ADMIN', 'Full system override.'),
        ('BLOOD_BANK_ADMIN', 'Manages inventory and approvals.'),
        ('HOSPITAL_USER', 'Can create blood requests and view own requests.'),
        ('STAFF_MEMBER', 'Operational staff for donor/donation entry.'),
        ('DONOR', 'Can view own profile and donation history.')
    ]
    for role_name, description in roles:
        cursor.execute(
            '''
            INSERT INTO Roles (role_name, description, is_active)
            VALUES (%s, %s, TRUE)
            ON DUPLICATE KEY UPDATE description = VALUES(description), is_active = TRUE
            ''',
            (role_name, description)
        )

    permissions = [
        ('donor:create', 'Create new donor record', 'donors', 'create'),
        ('donor:read', 'View donor records', 'donors', 'read'),
        ('donor:read_self', 'View own donor profile', 'donors', 'read_self'),
        ('donor:update', 'Update donor information', 'donors', 'update'),
        ('donor:delete', 'Delete donor record', 'donors', 'delete'),
        ('donation:create', 'Record new donation', 'donations', 'create'),
        ('donation:read', 'View donation records', 'donations', 'read'),
        ('donation:read_self', 'View own donation history', 'donations', 'read_self'),
        ('donation:update', 'Update donation record', 'donations', 'update'),
        ('donation:delete', 'Delete donation record', 'donations', 'delete'),
        ('request:create', 'Create blood request', 'requests', 'create'),
        ('request:read', 'View blood requests', 'requests', 'read'),
        ('request:read_self', 'View own blood requests', 'requests', 'read_self'),
        ('request:approve', 'Approve blood request', 'requests', 'approve'),
        ('request:reject', 'Reject blood request', 'requests', 'reject'),
        ('request:update_status', 'Update request status', 'requests', 'update_status'),
        ('inventory:read', 'View blood inventory', 'inventory', 'read'),
        ('inventory:update', 'Update blood inventory', 'inventory', 'update'),
        ('inventory:manage', 'Full inventory management', 'inventory', 'manage'),
        ('hospital:create', 'Register new hospital', 'hospitals', 'create'),
        ('hospital:read', 'View hospital records', 'hospitals', 'read'),
        ('hospital:update', 'Update hospital information', 'hospitals', 'update'),
        ('hospital:approve', 'Approve hospital registration', 'hospitals', 'approve'),
        ('hospital:delete', 'Delete hospital record', 'hospitals', 'delete'),
        ('audit:read', 'View audit logs', 'audit', 'read'),
        ('audit:read_self', 'View own activity logs', 'audit', 'read_self'),
        ('admin:manage', 'Manage users and roles', 'admin', 'manage'),
        ('users:create', 'Create user account', 'users', 'create'),
        ('users:read', 'View user information', 'users', 'read'),
        ('users:update', 'Update user information', 'users', 'update'),
        ('users:delete', 'Delete user account', 'users', 'delete'),
        ('users:assign_role', 'Assign roles to users', 'users', 'assign_role'),
        ('system:config', 'System configuration access', 'system', 'config')
    ]
    for permission_name, description, resource, action in permissions:
        cursor.execute(
            '''
            INSERT INTO Permissions (permission_name, description, resource, action)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                description = VALUES(description),
                resource = VALUES(resource),
                action = VALUES(action)
            ''',
            (permission_name, description, resource, action)
        )

    cursor.execute('''
        INSERT IGNORE INTO Role_Permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM Roles r
        JOIN Permissions p
        WHERE r.role_name = 'SUPER_ADMIN'
    ''')
    cursor.execute('''
        INSERT IGNORE INTO Role_Permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM Roles r
        JOIN Permissions p
        WHERE r.role_name = 'BLOOD_BANK_ADMIN'
          AND p.permission_name IN (
            'donor:create', 'donor:read', 'donor:update',
            'donation:create', 'donation:read', 'donation:update',
            'request:read', 'request:approve', 'request:reject', 'request:update_status',
            'inventory:read', 'inventory:manage',
            'hospital:read',
            'audit:read'
          )
    ''')
    cursor.execute('''
        INSERT IGNORE INTO Role_Permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM Roles r
        JOIN Permissions p
        WHERE r.role_name = 'HOSPITAL_USER'
          AND p.permission_name IN (
            'request:create', 'request:read_self', 'inventory:read', 'hospital:read', 'audit:read_self'
          )
    ''')
    cursor.execute('''
        INSERT IGNORE INTO Role_Permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM Roles r
        JOIN Permissions p
        WHERE r.role_name = 'STAFF_MEMBER'
          AND p.permission_name IN (
            'donor:create', 'donor:read', 'donor:update',
            'donation:create', 'donation:read',
            'inventory:read', 'audit:read_self'
          )
    ''')
    cursor.execute('''
        INSERT IGNORE INTO Role_Permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM Roles r
        JOIN Permissions p
        WHERE r.role_name = 'DONOR'
          AND p.permission_name IN (
            'donor:read_self', 'donation:read_self', 'inventory:read', 'audit:read_self'
          )
    ''')

# ==================== DATABASE INITIALIZATION ====================

def init_db():
    """Initialize MySQL database with schema"""
    try:
        conn = mysql.connector.connect(
            host=DB_CONFIG['host'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            port=DB_CONFIG['port']
        )
        cursor = conn.cursor()
        
        # Create database if not exists
        db_name = DB_CONFIG['database']
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
        cursor.execute(f"USE `{db_name}`")
        
        # Create Users table
        cursor.execute('''CREATE TABLE IF NOT EXISTS Users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            email VARCHAR(255),
            full_name VARCHAR(255),
            role VARCHAR(50) DEFAULT 'staff',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # Create Donors table
        cursor.execute('''CREATE TABLE IF NOT EXISTS Donors (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            age INT NOT NULL,
            gender VARCHAR(20),
            blood_group VARCHAR(10) NOT NULL,
            phone VARCHAR(20) UNIQUE NOT NULL,
            email VARCHAR(255),
            address VARCHAR(255),
            profile_image_url VARCHAR(500),
            availability VARCHAR(20) DEFAULT 'Available',
            last_donation_date DATE,
            last_active_at DATETIME NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) DEFAULT 'Active'
        )''')
        
        # Create Blood Inventory table
        cursor.execute('''CREATE TABLE IF NOT EXISTS Blood_Inventory (
            blood_group VARCHAR(10) PRIMARY KEY,
            quantity_units INT DEFAULT 0
        )''')
        
        # Create Hospitals table
        cursor.execute('''CREATE TABLE IF NOT EXISTS Hospitals (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            contact VARCHAR(100) NOT NULL,
            address TEXT NOT NULL,
            email VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # Create Blood Requests table
        cursor.execute('''CREATE TABLE IF NOT EXISTS Blood_Requests (
            id INT AUTO_INCREMENT PRIMARY KEY,
            hospital_id INT NOT NULL,
            blood_group VARCHAR(10) NOT NULL,
            units_required INT NOT NULL,
            status VARCHAR(20) DEFAULT 'Pending',
            request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approval_date DATETIME,
            FOREIGN KEY(hospital_id) REFERENCES Hospitals(id)
        )''')
        
        # Create Donations table
        cursor.execute('''CREATE TABLE IF NOT EXISTS Donations (
            id INT AUTO_INCREMENT PRIMARY KEY,
            donor_id INT NOT NULL,
            units INT NOT NULL,
            donation_date DATE NOT NULL,
            blood_group VARCHAR(10) NOT NULL,
            health_status VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(donor_id) REFERENCES Donors(id)
        )''')

        # Create Blood Batches table (inventory batches)
        cursor.execute('''CREATE TABLE IF NOT EXISTS blood_batches (
            id INT AUTO_INCREMENT PRIMARY KEY,
            blood_group VARCHAR(10) NOT NULL,
            units_total INT NOT NULL,
            units_remaining INT NOT NULL,
            donation_date DATE NOT NULL,
            expiry_date DATE NOT NULL,
            donor_id INT NOT NULL,
            status VARCHAR(20) DEFAULT 'Active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (donor_id) REFERENCES Donors(id) ON DELETE CASCADE
        )''')
        
        # Initialize blood groups
        for bg in BLOOD_GROUPS:
            cursor.execute('INSERT IGNORE INTO Blood_Inventory VALUES (%s, 0)', (bg,))
        
        # Create default users
        default_users = [
            ('admin', os.getenv('BBMS_ADMIN_PASSWORD', 'admin123'), 'admin@redlifeline.com', 'Admin User', 'admin'),
            ('staff', os.getenv('BBMS_STAFF_PASSWORD', 'staff123'), 'staff@redlifeline.com', 'Staff Member', 'staff'),
        ]
        for username, password, email, full_name, role in default_users:
            cursor.execute('''INSERT IGNORE INTO Users (username, password, email, full_name, role) 
                            VALUES (%s, %s, %s, %s, %s)''',
                         (username, password, email, full_name, role))

        # Ensure RBAC tables/seed data exist for user management and permissions.
        ensure_rbac_schema(cursor)

        # Ensure optional columns expected by advanced donor/admin features exist.
        apply_schema_extensions(cursor)
        
        conn.commit()
        conn.close()
        print("[OK] MySQL database initialized successfully!")
    except Error as e:
        print(f"[ERROR] Database initialization error: {e}")

# ==================== DATABASE FUNCTIONS ====================

def get_db():
    """Get MySQL database connection"""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Error as e:
        app.logger.error(
            "MySQL connection failed (host=%s, db=%s, port=%s, user=%s): %s",
            DB_CONFIG.get('host'),
            DB_CONFIG.get('database'),
            DB_CONFIG.get('port'),
            DB_CONFIG.get('user'),
            str(e)
        )
        raise

def dict_from_cursor(cursor, row):
    """Convert MySQL cursor result to dictionary"""
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))

def dict_from_cursor_list(cursor, rows):
    """Convert MySQL cursor results to list of dictionaries"""
    if not rows:
        return []
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in rows]

def get_batch_inventory_summary(cursor):
    """Compute inventory totals from blood_batches."""
    if not table_exists(cursor, 'blood_batches'):
        return []

    cursor.execute("""
        SELECT
            blood_group,
            SUM(CASE WHEN expiry_date > CURDATE() AND status = 'Active' THEN units_remaining ELSE 0 END) as total_units,
            SUM(CASE WHEN expiry_date > CURDATE()
                      AND expiry_date <= DATE_ADD(CURDATE(), INTERVAL 5 DAY)
                      AND status = 'Active' THEN units_remaining ELSE 0 END) as near_expiry_units,
            SUM(CASE WHEN expiry_date <= CURDATE() OR status = 'Expired' THEN units_remaining ELSE 0 END) as expired_units
        FROM blood_batches
        GROUP BY blood_group
    """)
    rows = cursor.fetchall() or []
    summary_map = {row[0] if not isinstance(row, dict) else row.get('blood_group'): row for row in rows}

    summary = []
    for group in BLOOD_GROUPS:
        row = summary_map.get(group)
        if isinstance(row, dict):
            total_units = int(row.get('total_units') or 0)
            near_expiry_units = int(row.get('near_expiry_units') or 0)
            expired_units = int(row.get('expired_units') or 0)
        elif row:
            total_units = int(row[1] or 0)
            near_expiry_units = int(row[2] or 0)
            expired_units = int(row[3] or 0)
        else:
            total_units = 0
            near_expiry_units = 0
            expired_units = 0

        summary.append({
            'blood_group': group,
            'quantity_units': total_units,
            'total_units': total_units,
            'near_expiry_units': near_expiry_units,
            'expired_units': expired_units
        })

    return summary


def get_available_units_for_group(cursor, blood_group):
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
        row = cursor.fetchone()
        if isinstance(row, dict):
            return int(row.get('total_units') or 0)
        return int(row[0] if row else 0)

    return 0

# ==================== UTILITY FUNCTIONS ====================

def validate_phone(phone):
    """Validate phone number format"""
    return len(phone) >= 10 and phone.isdigit()

def validate_email(email):
    """Validate email format"""
    return '@' in email and '.' in email

def make_serializable(data):
    """Convert non-serializable types (date, Decimal) for JSON responses"""
    if isinstance(data, list):
        return [make_serializable(item) for item in data]
    elif isinstance(data, dict):
        return {k: make_serializable(v) for k, v in data.items()}
    elif isinstance(data, (date, datetime)):
        return data.isoformat()
    elif isinstance(data, Decimal):
        return int(data)
    return data

@app.template_filter('strftime')
def format_datetime(value, fmt='%Y-%m-%d %H:%M'):
    """Jinja filter for safely formatting datetime-like values."""
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.strftime(fmt)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time()).strftime(fmt)
    if isinstance(value, str):
        # Attempt common database string formats before falling back.
        for parse_fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y-%m-%d %H:%M:%S.%f'):
            try:
                return datetime.strptime(value, parse_fmt).strftime(fmt)
            except ValueError:
                continue
        return value
    return str(value)

# ==================== AUTHENTICATION ====================

# Demo credentials (change in production)
ADMIN_USERNAME = os.getenv('BBMS_ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('BBMS_ADMIN_PASSWORD', 'admin123')

def login_required(f):
    """Decorator to require login for protected routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access the system.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def donor_prohibited(f):
    """Prevent DONOR role from accessing operational/admin routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role_name') == 'DONOR':
            flash('Donor accounts cannot access this section.', 'warning')
            return redirect(url_for('user_mgmt.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def resolve_donor_id_for_user(cursor, user_id, username, email):
    """Resolve donor profile linked to current user."""
    donor_id = None

    if table_exists(cursor, 'Users_RBAC') and column_exists(cursor, 'Users_RBAC', 'donor_id'):
        cursor.execute("SELECT donor_id FROM Users_RBAC WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        if row and row[0]:
            donor_id = row[0]

    if not donor_id and column_exists(cursor, 'Donors', 'email') and email:
        cursor.execute("SELECT id FROM Donors WHERE email = %s LIMIT 1", (email,))
        row = cursor.fetchone()
        if row:
            donor_id = row[0]

    if not donor_id and username:
        cursor.execute("SELECT id FROM Donors WHERE name = %s LIMIT 1", (username,))
        row = cursor.fetchone()
        if row:
            donor_id = row[0]

    # Common bootstrap pattern: usernames like donor1, donor2, ...
    if not donor_id and username:
        raw_username = username.strip()
        if raw_username.lower().startswith('donor'):
            suffix = raw_username[5:]
            if suffix.isdigit():
                cursor.execute("SELECT id FROM Donors WHERE id = %s LIMIT 1", (int(suffix),))
                row = cursor.fetchone()
                if row:
                    donor_id = row[0]

    # Fallback: try RBAC full_name against donor name.
    if (
        not donor_id
        and table_exists(cursor, 'Users_RBAC')
        and column_exists(cursor, 'Users_RBAC', 'full_name')
    ):
        cursor.execute("SELECT full_name FROM Users_RBAC WHERE id = %s", (user_id,))
        name_row = cursor.fetchone()
        full_name = name_row[0].strip() if name_row and name_row[0] else None
        if full_name:
            cursor.execute("SELECT id FROM Donors WHERE name = %s LIMIT 1", (full_name,))
            row = cursor.fetchone()
            if row:
                donor_id = row[0]

    # Soft match: username prefix (e.g., "Jefrin" -> "Jefrin Issac"), only when unique.
    if not donor_id and username:
        name_token = username.strip().split()[0] if username.strip() else ''
        if name_token:
            cursor.execute(
                "SELECT id FROM Donors WHERE LOWER(name) LIKE LOWER(%s) ORDER BY id LIMIT 2",
                (f"{name_token}%",)
            )
            matches = cursor.fetchall() or []
            if len(matches) == 1:
                donor_id = matches[0][0]

    # Soft match: email local-part prefix, only when unique.
    if not donor_id and email and '@' in email:
        local_part = email.split('@', 1)[0].strip()
        if local_part:
            cursor.execute(
                "SELECT id FROM Donors WHERE LOWER(name) LIKE LOWER(%s) ORDER BY id LIMIT 2",
                (f"{local_part}%",)
            )
            matches = cursor.fetchall() or []
            if len(matches) == 1:
                donor_id = matches[0][0]

    return donor_id


def get_hospital_id_for_user(user_id):
    """Resolve hospital_id for a given user."""
    if not user_id:
        return None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT hospital_id FROM Users_RBAC WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def generate_password(length=12):
    """Generate a random password for bootstrap accounts."""
    if length < 8:
        length = 8
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def hash_reset_token(token):
    """Hash reset token for storage."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def ensure_password_reset_table(cursor):
    """Create password reset table if missing."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS Password_Reset_Tokens (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            user_table VARCHAR(20) NOT NULL,
            token_hash CHAR(64) NOT NULL,
            expires_at DATETIME NOT NULL,
            used BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_token_hash (token_hash),
            INDEX idx_user (user_id, user_table),
            INDEX idx_expires (expires_at)
        )
        """
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'GET' and session.get('logged_in'):
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # Always reset any existing session before a new login attempt.
        session.clear()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session.permanent = True
            session['logged_in'] = True
            session['username'] = username
            
            # Look up the admin user in Users_RBAC for RBAC integration
            try:
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT u.id, u.role_id, r.role_name
                    FROM Users_RBAC u
                    LEFT JOIN Roles r ON r.id = u.role_id
                    WHERE u.username = %s AND u.is_active = TRUE""",
                    (username,)
                )
                rbac_user = cursor.fetchone()
                
                if not rbac_user:
                    # Auto-create admin in Users_RBAC with SUPER_ADMIN role
                    cursor.execute("SELECT id FROM Roles WHERE role_name = 'SUPER_ADMIN'")
                    role = cursor.fetchone()
                    if role:
                        cursor.execute(
                            """INSERT INTO Users_RBAC 
                            (username, email, password_hash, full_name, role_id, is_active)
                            VALUES (%s, %s, %s, %s, %s, TRUE)""",
                            (
                                username,
                                'admin@redlifeline.com',
                                generate_password_hash(password),
                                'Administrator',
                                role[0]
                            )
                        )
                        conn.commit()
                        session['user_id'] = cursor.lastrowid
                        session['role_id'] = role[0]
                        session['role_name'] = 'SUPER_ADMIN'
                    else:
                        session['user_id'] = None
                        session.pop('role_id', None)
                        session.pop('role_name', None)
                else:
                    session['user_id'] = rbac_user[0]
                    session['role_id'] = rbac_user[1]
                    session['role_name'] = rbac_user[2] if len(rbac_user) > 2 else None
                
                cursor.close()
                conn.close()
            except Exception:
                session['user_id'] = None
                session.pop('role_id', None)
                session.pop('role_name', None)
            
            flash('Welcome back, Admin!', 'success')
            return redirect(url_for('index'))
        else:
            # Check Users_RBAC table for other users (username or email).
            # Supports legacy plaintext passwords and upgrades them to hashes on successful login.
            try:
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT u.id, u.username, u.password_hash, u.role_id, r.role_name
                    FROM Users_RBAC u
                    LEFT JOIN Roles r ON r.id = u.role_id
                    WHERE (u.username = %s OR u.email = %s) AND u.is_active = TRUE
                    LIMIT 1""",
                    (username, username)
                )
                user = cursor.fetchone()
                
                if user:
                    user_id, login_name, password_hash, role_id, role_name = user

                    password_ok = False
                    if password_hash:
                        if password_hash.startswith(('pbkdf2:', 'scrypt:')):
                            password_ok = check_password_hash(password_hash, password)
                        else:
                            # Legacy/plaintext password support (auto-migrate on success)
                            password_ok = password_hash == password
                            if password_ok:
                                cursor.execute(
                                    "UPDATE Users_RBAC SET password_hash = %s WHERE id = %s",
                                    (generate_password_hash(password), user_id)
                                )
                                conn.commit()

                    if password_ok:
                        cursor.close()
                        conn.close()
                        session.permanent = True
                        session['logged_in'] = True
                        session['username'] = login_name
                        session['user_id'] = user_id
                        session['role_id'] = role_id
                        session['role_name'] = role_name
                        flash(f'Welcome back, {login_name}!', 'success')
                        return redirect(url_for('index'))

                # Legacy fallback: allow login from old Users table
                cursor.execute(
                    """SELECT id, username, password
                    FROM Users
                    WHERE username = %s OR email = %s
                    LIMIT 1""",
                    (username, username)
                )
                legacy_user = cursor.fetchone()
                cursor.close()
                conn.close()

                if legacy_user and legacy_user[2] == password:
                    session.permanent = True
                    session['logged_in'] = True
                    session['username'] = legacy_user[1]
                    session['user_id'] = legacy_user[0]
                    session.pop('role_id', None)
                    session['role_name'] = 'LEGACY_USER'
                    flash(f'Welcome back, {legacy_user[1]}!', 'success')
                    return redirect(url_for('index'))
            except Exception:
                pass
            
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


@app.route('/donor/profile', methods=['POST'])
@login_required
def update_donor_profile():
    """Allow DONOR user to update own profile fields."""
    if session.get('role_name') != 'DONOR':
        flash('Only donor accounts can update this profile.', 'danger')
        return redirect(url_for('index'))

    user_id = session.get('user_id')
    username = session.get('username')
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    address = request.form.get('address', '').strip()
    profile_image_url = request.form.get('profile_image_url', '').strip()
    profile_image_file = request.files.get('profile_image')
    remove_profile_image = request.form.get('remove_profile_image', '').lower() in ['1', 'true', 'on', 'yes']
    availability = request.form.get('availability', '').strip()
    if not availability and request.form.get('is_available') in ['1', 'true', 'on', 'yes']:
        availability = 'Available'
    elif not availability and request.form.get('is_available') in ['0', 'false', 'off', 'no']:
        availability = 'Not Available'

    if phone and not validate_phone(phone):
        flash('Invalid phone number.', 'danger')
        return redirect(url_for('user_mgmt.dashboard'))
    if email and not validate_email(email):
        flash('Invalid email format.', 'danger')
        return redirect(url_for('user_mgmt.dashboard'))
    if profile_image_url and not (
        profile_image_url.startswith('http://')
        or profile_image_url.startswith('https://')
        or profile_image_url.startswith('/')
    ):
        flash('Profile image URL must start with http://, https://, or /.', 'danger')
        return redirect(url_for('user_mgmt.dashboard'))
    if availability and availability not in ['Available', 'Not Available']:
        flash('Invalid availability value.', 'danger')
        return redirect(url_for('user_mgmt.dashboard'))

    try:
        conn = get_db()
        cursor = conn.cursor()

        # Fetch current user email for donor resolution.
        cursor.execute("SELECT email FROM Users_RBAC WHERE id = %s", (user_id,))
        user_row = cursor.fetchone()
        current_email = user_row[0] if user_row else None

        donor_id = resolve_donor_id_for_user(cursor, user_id, username, current_email)
        if not donor_id:
            conn.close()
            flash('No linked donor profile found for this account.', 'danger')
            return redirect(url_for('user_mgmt.dashboard'))

        donors_has_email = column_exists(cursor, 'Donors', 'email')
        donors_has_availability = column_exists(cursor, 'Donors', 'availability')
        donors_has_address = column_exists(cursor, 'Donors', 'address')
        donors_has_profile_image_url = column_exists(cursor, 'Donors', 'profile_image_url')
        existing_profile_image_url = None
        if donors_has_profile_image_url:
            cursor.execute("SELECT profile_image_url FROM Donors WHERE id = %s", (donor_id,))
            profile_row = cursor.fetchone()
            existing_profile_image_url = profile_row[0] if profile_row else None

        update_fields = []
        params = []

        if phone:
            update_fields.append("phone = %s")
            params.append(phone)
        if donors_has_email and email:
            update_fields.append("email = %s")
            params.append(email)
        if donors_has_address and 'address' in request.form:
            update_fields.append("address = %s")
            params.append(address or None)
        if donors_has_profile_image_url:
            next_profile_image_url = None
            has_profile_image_update = False

            if profile_image_file and profile_image_file.filename:
                uploaded_path, upload_error = save_donor_profile_image(profile_image_file, donor_id)
                if upload_error:
                    conn.close()
                    flash(upload_error, 'danger')
                    return redirect(url_for('user_mgmt.dashboard'))
                next_profile_image_url = uploaded_path
                has_profile_image_update = True
            elif remove_profile_image:
                next_profile_image_url = None
                has_profile_image_update = True
            elif 'profile_image_url' in request.form:
                # Backward compatibility with old form/input.
                next_profile_image_url = profile_image_url or None
                has_profile_image_update = True

            if has_profile_image_update:
                update_fields.append("profile_image_url = %s")
                params.append(next_profile_image_url)
                if (
                    existing_profile_image_url
                    and existing_profile_image_url != next_profile_image_url
                ):
                    remove_local_donor_profile_image(existing_profile_image_url)
        if donors_has_availability and availability:
            update_fields.append("availability = %s")
            params.append(availability)

        if update_fields:
            cursor.execute(
                f"UPDATE Donors SET {', '.join(update_fields)} WHERE id = %s",
                tuple(params + [donor_id])
            )

        if email:
            cursor.execute("UPDATE Users_RBAC SET email = %s WHERE id = %s", (email, user_id))

        conn.commit()
        conn.close()
        flash('Profile updated successfully.', 'success')
    except Error as e:
        if 'Duplicate entry' in str(e):
            flash('Phone or email already exists.', 'danger')
        else:
            flash(f'Error updating profile: {str(e)}', 'danger')
    except Exception as e:
        flash(f'Error updating profile: {str(e)}', 'danger')

    return redirect(url_for('user_mgmt.dashboard'))


@app.route('/donor/availability', methods=['POST'])
@login_required
def update_donor_availability():
    """Toggle donor availability quickly from dashboard."""
    if session.get('role_name') != 'DONOR':
        flash('Only donor accounts can update availability.', 'danger')
        return redirect(url_for('index'))

    user_id = session.get('user_id')
    username = session.get('username')
    raw_value = request.form.get('is_available', '0')
    availability = 'Available' if str(raw_value).strip() in ['1', 'true', 'on', 'yes'] else 'Not Available'

    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT email FROM Users_RBAC WHERE id = %s", (user_id,))
        user_row = cursor.fetchone()
        current_email = user_row[0] if user_row else None

        donor_id = resolve_donor_id_for_user(cursor, user_id, username, current_email)
        if not donor_id:
            conn.close()
            flash('No linked donor profile found for this account.', 'danger')
            return redirect(url_for('user_mgmt.dashboard'))

        if not column_exists(cursor, 'Donors', 'availability'):
            conn.close()
            flash('Availability column is not available in current donor schema.', 'warning')
            return redirect(url_for('user_mgmt.dashboard'))

        if column_exists(cursor, 'Donors', 'last_active_at'):
            cursor.execute(
                "UPDATE Donors SET availability = %s, last_active_at = NOW() WHERE id = %s",
                (availability, donor_id)
            )
        else:
            cursor.execute(
                "UPDATE Donors SET availability = %s WHERE id = %s",
                (availability, donor_id)
            )

        conn.commit()
        conn.close()
        flash(
            'Availability updated: You are now marked as available.'
            if availability == 'Available'
            else 'Availability updated: You are marked as not available.',
            'success'
        )
    except Exception as e:
        flash(f'Error updating availability: {str(e)}', 'danger')

    return redirect(url_for('user_mgmt.dashboard'))


@app.route('/donor/request/<int:request_id>/<action>', methods=['POST'])
@login_required
def donor_request_action(request_id, action):
    """Handle donor accept/decline action for an urgent blood request card."""
    if session.get('role_name') != 'DONOR':
        flash('Only donor accounts can respond to donor requests.', 'danger')
        return redirect(url_for('index'))

    if action not in ['accept', 'decline']:
        flash('Invalid action.', 'danger')
        return redirect(url_for('user_mgmt.dashboard'))

    user_id = session.get('user_id')
    username = session.get('username')

    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT email FROM Users_RBAC WHERE id = %s", (user_id,))
        user_row = cursor.fetchone()
        current_email = user_row[0] if user_row else None

        donor_id = resolve_donor_id_for_user(cursor, user_id, username, current_email)
        if not donor_id:
            conn.close()
            flash('No linked donor profile found for this account.', 'danger')
            return redirect(url_for('user_mgmt.dashboard'))

        cursor.execute("SELECT blood_group FROM Donors WHERE id = %s", (donor_id,))
        donor_row = cursor.fetchone()
        if not donor_row:
            conn.close()
            flash('Donor profile not found.', 'danger')
            return redirect(url_for('user_mgmt.dashboard'))

        donor_blood_group = donor_row[0]

        cursor.execute(
            """
            SELECT br.id, br.status, br.blood_group, h.name
            FROM Blood_Requests br
            LEFT JOIN Hospitals h ON br.hospital_id = h.id
            WHERE br.id = %s
            LIMIT 1
            """,
            (request_id,)
        )
        request_row = cursor.fetchone()
        if not request_row:
            conn.close()
            flash('Blood request not found.', 'danger')
            return redirect(url_for('user_mgmt.dashboard'))

        _, request_status, request_blood_group, hospital_name = request_row
        if request_status != 'Pending':
            conn.close()
            flash('This request is no longer pending.', 'warning')
            return redirect(url_for('user_mgmt.dashboard'))
        if request_blood_group != donor_blood_group:
            conn.close()
            flash('This request does not match your blood group.', 'warning')
            return redirect(url_for('user_mgmt.dashboard'))

        if action == 'accept':
            if column_exists(cursor, 'Donors', 'availability'):
                if column_exists(cursor, 'Donors', 'last_active_at'):
                    cursor.execute(
                        "UPDATE Donors SET availability = 'Available', last_active_at = NOW() WHERE id = %s",
                        (donor_id,)
                    )
                else:
                    cursor.execute(
                        "UPDATE Donors SET availability = 'Available' WHERE id = %s",
                        (donor_id,)
                    )
            conn.commit()
            conn.close()
            flash(
                f'Thank you for accepting. Please contact {hospital_name or "the hospital"} to proceed.',
                'success'
            )
            return redirect(url_for('user_mgmt.dashboard'))

        conn.close()
        flash('Request declined. You can still change availability anytime.', 'warning')
    except Exception as e:
        flash(f'Error handling donor request: {str(e)}', 'danger')

    return redirect(url_for('user_mgmt.dashboard'))

@app.route('/test-dashboard')
def test_dashboard():
    """Test dashboard with minimal HTML"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Dashboard</title>
        <style>
            body { font-family: Arial; background: #fdf6f0; color: #333; margin: 0; padding: 20px; }
            .navbar { background: white; padding: 20px; margin-bottom: 20px; }
            .stat { background: white; padding: 20px; margin: 10px; border-radius: 8px; }
        </style>
    </head>
    <body>
        <div class="navbar">
            <h1>Red Lifeline Dashboard</h1>
            <a href="/logout">Logout</a>
        </div>
        <div class="stat">
            <h3>Total Donors</h3>
            <p>Loading...</p>
        </div>
        <p>If you can see this, the basic layout is working.</p>
    </body>
    </html>
    '''

# ==================== ROUTES ====================

@app.route('/welcome')
def welcome():
    """Public landing page."""
    if session.get('logged_in'):
        return redirect(url_for('index'))
    return render_template('welcome.html')


@app.route('/')
def index():
    """Landing page for guests, dashboard for authenticated users."""
    if not session.get('logged_in'):
        return render_template('welcome.html')

    if session.get('role_name') == 'DONOR':
        return redirect(url_for('user_mgmt.dashboard'))

    conn = get_db()
    cursor = conn.cursor()
    
    # Get statistics
    cursor.execute('SELECT COUNT(*) as count FROM Donors')
    total_donors = dict_from_cursor(cursor, cursor.fetchone())['count']
    
    inventory_summary = get_batch_inventory_summary(cursor)
    total_units = sum(item.get('quantity_units', 0) for item in inventory_summary)
    
    cursor.execute("SELECT COUNT(*) as count FROM Blood_Requests WHERE status=%s", ('Pending',))
    pending_requests = dict_from_cursor(cursor, cursor.fetchone())['count']
    
    out_of_stock = sum(1 for item in inventory_summary if (item.get('quantity_units') or 0) == 0)
    
    # Get inventory details
    inventory = inventory_summary
    
    # Get recent requests
    cursor.execute('''SELECT br.id, h.name as hospital_name, br.blood_group, br.units_required, br.status
                      FROM Blood_Requests br
                      LEFT JOIN Hospitals h ON br.hospital_id = h.id
                      ORDER BY br.request_date DESC LIMIT 10''')
    recent_requests = dict_from_cursor_list(cursor, cursor.fetchall())
    
    # Get monthly donation stats
    cursor.execute('''SELECT MONTH(donation_date) as month, SUM(units) as total_units
                      FROM Donations
                      WHERE YEAR(donation_date) = YEAR(CURDATE())
                      GROUP BY MONTH(donation_date)
                      ORDER BY MONTH(donation_date)''')
    monthly_data = {int(row['month']): (int(row['total_units']) if row['total_units'] else 0) for row in dict_from_cursor_list(cursor, cursor.fetchall())}
    
    # Build full month array (0 for missing months)
    monthly_donations = [monthly_data.get(i, 0) for i in range(1, 13)]
    
    conn.close()
    
    return render_template('index.html', 
                         total_donors=total_donors,
                         total_units=total_units,
                         pending_requests=pending_requests,
                         out_of_stock=out_of_stock,
                         inventory=inventory,
                         recent_requests=recent_requests,
                         monthly_donations=monthly_donations)


@app.route('/add-donor', methods=['GET', 'POST'])
@login_required
@donor_prohibited
def add_donor():
    """Add new donor"""
    if session.get('role_name') == 'HOSPITAL_USER':
        flash('Hospital users cannot add donors.', 'danger')
        return redirect(url_for('user_mgmt.dashboard'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        age = request.form.get('age', type=int, default=None)
        gender = request.form.get('gender', '').strip()
        blood_group = request.form.get('blood_group', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        
        # Validation
        if not all([name, age, gender, blood_group, phone]):
            flash('All fields are required!', 'danger')
            return redirect(url_for('add_donor'))
        
        if age <= 18:
            flash('Donor age must be greater than 18!', 'danger')
            return redirect(url_for('add_donor'))
        
        if not validate_phone(phone):
            flash('Invalid phone number!', 'danger')
            return redirect(url_for('add_donor'))
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            donors_has_email = column_exists(cursor, 'Donors', 'email')
            donors_has_availability = column_exists(cursor, 'Donors', 'availability')

            if donors_has_email and donors_has_availability:
                cursor.execute(
                    '''INSERT INTO Donors (name, age, gender, blood_group, phone, email, status, availability)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
                    (name, age, gender, blood_group, phone, (email or None), 'Active', 'Available')
                )
            elif donors_has_email:
                cursor.execute(
                    '''INSERT INTO Donors (name, age, gender, blood_group, phone, email, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                    (name, age, gender, blood_group, phone, (email or None), 'Active')
                )
            else:
                cursor.execute(
                    '''INSERT INTO Donors (name, age, gender, blood_group, phone, status)
                    VALUES (%s, %s, %s, %s, %s, %s)''',
                    (name, age, gender, blood_group, phone, 'Active')
                )
            conn.commit()
            conn.close()
            flash('Donor added successfully!', 'success')
            return redirect(url_for('view_donors'))
        except Error as e:
            if "Duplicate entry" in str(e):
                flash('Donor with this phone number already exists!', 'danger')
            else:
                flash(f'Error: {str(e)}', 'danger')
            return redirect(url_for('add_donor'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
            return redirect(url_for('add_donor'))
    
    return render_template('add_donor.html')


@app.route('/donors')
@login_required
@donor_prohibited
def view_donors():
    """View all donors with admin filters and donation frequency insights."""
    search = request.args.get('search', '').strip()
    blood_group = request.args.get('blood_group', '').strip()
    status = request.args.get('status', '').strip()
    eligible_only = request.args.get('eligible') == '1'
    inactive_year = request.args.get('inactive_year') == '1'
    sort_by = request.args.get('sort_by', 'last_donation_date').strip()
    order = request.args.get('order', 'desc').strip().lower()
    order_dir = 'DESC' if order == 'desc' else 'ASC'

    allowed_sort_columns = {
        'name': 'd.name',
        'blood_group': 'd.blood_group',
        'status': 'd.status',
        'last_donation_date': 'd.last_donation_date',
        'total_donations': 'total_donations',
        'created_at': 'd.created_at'
    }
    sort_col = allowed_sort_columns.get(sort_by, 'd.last_donation_date')

    conn = get_db()
    cursor = conn.cursor()

    donors_has_email = column_exists(cursor, 'Donors', 'email')
    donors_has_availability = column_exists(cursor, 'Donors', 'availability')

    select_extra = ""
    if donors_has_email:
        select_extra += ", d.email"
    else:
        select_extra += ", NULL as email"
    if donors_has_availability:
        select_extra += ", d.availability"
    else:
        select_extra += ", CASE WHEN d.status='Active' THEN 'Available' ELSE 'Not Available' END as availability"

    where_clauses = ["1=1"]
    params = []

    if search:
        like = f"%{search}%"
        if donors_has_email:
            where_clauses.append("(d.name LIKE %s OR d.phone LIKE %s OR COALESCE(d.email, '') LIKE %s)")
            params.extend([like, like, like])
        else:
            where_clauses.append("(d.name LIKE %s OR d.phone LIKE %s)")
            params.extend([like, like])
    if blood_group:
        where_clauses.append("d.blood_group = %s")
        params.append(blood_group)
    if status:
        where_clauses.append("d.status = %s")
        params.append(status)
    if eligible_only:
        where_clauses.append("(d.last_donation_date IS NULL OR d.last_donation_date <= DATE_SUB(CURDATE(), INTERVAL 90 DAY))")
    if inactive_year:
        where_clauses.append("(d.status = 'Inactive' AND (d.last_donation_date IS NULL OR d.last_donation_date <= DATE_SUB(CURDATE(), INTERVAL 1 YEAR)))")

    query = f"""
        SELECT
            d.id, d.name, d.age, d.gender, d.blood_group, d.phone,
            d.last_donation_date, d.created_at, d.status
            {select_extra},
            COALESCE(ds.total_donations, 0) as total_donations,
            COALESCE(ds.total_units, 0) as total_units
        FROM Donors d
        LEFT JOIN (
            SELECT donor_id, COUNT(*) as total_donations, COALESCE(SUM(units), 0) as total_units
            FROM Donations
            GROUP BY donor_id
        ) ds ON ds.donor_id = d.id
        WHERE {' AND '.join(where_clauses)}
        ORDER BY {sort_col} {order_dir}, d.name ASC
    """
    cursor.execute(query, tuple(params))
    donors = dict_from_cursor_list(cursor, cursor.fetchall())

    cursor.execute("""
        SELECT d.id, d.name, d.blood_group, COUNT(do.id) as total_donations
        FROM Donors d
        JOIN Donations do ON do.donor_id = d.id
        GROUP BY d.id, d.name, d.blood_group
        ORDER BY total_donations DESC, d.name ASC
        LIMIT 5
    """)
    top_frequent_donors = dict_from_cursor_list(cursor, cursor.fetchall())

    cursor.execute("""
        SELECT COUNT(*) as cnt
        FROM Donors
        WHERE status = 'Active'
          AND (last_donation_date IS NULL OR last_donation_date <= DATE_SUB(CURDATE(), INTERVAL 90 DAY))
    """)
    eligible_count = dict_from_cursor(cursor, cursor.fetchone())['cnt']

    conn.close()

    return render_template(
        'view_donors.html',
        donors=donors,
        top_frequent_donors=top_frequent_donors,
        eligible_count=eligible_count,
        filters={
            'search': search,
            'blood_group': blood_group,
            'status': status,
            'eligible': eligible_only,
            'inactive_year': inactive_year,
            'sort_by': sort_by,
            'order': order_dir.lower()
        }
    )


@app.route('/donors/<int:donor_id>/update', methods=['POST'])
@login_required
@donor_prohibited
def update_donor(donor_id):
    """Admin edit donor details."""
    name = request.form.get('name', '').strip()
    age = request.form.get('age', type=int, default=None)
    gender = request.form.get('gender', '').strip()
    blood_group = request.form.get('blood_group', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    availability = request.form.get('availability', '').strip()

    if not all([name, age, gender, blood_group, phone]):
        flash('Name, age, gender, blood group and phone are required.', 'danger')
        return redirect(url_for('view_donors'))
    if age <= 18:
        flash('Donor age must be greater than 18.', 'danger')
        return redirect(url_for('view_donors'))
    if not validate_phone(phone):
        flash('Invalid phone number.', 'danger')
        return redirect(url_for('view_donors'))

    try:
        conn = get_db()
        cursor = conn.cursor()
        donors_has_email = column_exists(cursor, 'Donors', 'email')
        donors_has_availability = column_exists(cursor, 'Donors', 'availability')

        query = """
            UPDATE Donors
            SET name = %s, age = %s, gender = %s, blood_group = %s, phone = %s
        """
        params = [name, age, gender, blood_group, phone]

        if donors_has_email:
            query += ", email = %s"
            params.append(email if email else None)
        if donors_has_availability and availability in ['Available', 'Not Available']:
            query += ", availability = %s"
            params.append(availability)

        query += " WHERE id = %s"
        params.append(donor_id)

        cursor.execute(query, tuple(params))
        conn.commit()
        conn.close()
        flash('Donor details updated successfully.', 'success')
    except Error as e:
        if 'Duplicate entry' in str(e):
            flash('Phone or email already exists for another donor.', 'danger')
        else:
            flash(f'Error updating donor: {str(e)}', 'danger')
    except Exception as e:
        flash(f'Error updating donor: {str(e)}', 'danger')

    return redirect(url_for('view_donors'))


@app.route('/donors/<int:donor_id>/deactivate', methods=['POST'])
@login_required
@donor_prohibited
def deactivate_donor(donor_id):
    """Deactivate donor profile."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        if column_exists(cursor, 'Donors', 'availability'):
            cursor.execute(
                "UPDATE Donors SET status = 'Inactive', availability = 'Not Available', last_active_at = NOW() WHERE id = %s",
                (donor_id,)
            )
        else:
            cursor.execute("UPDATE Donors SET status = 'Inactive' WHERE id = %s", (donor_id,))
        conn.commit()
        conn.close()
        flash('Donor deactivated successfully.', 'success')
    except Exception as e:
        flash(f'Error deactivating donor: {str(e)}', 'danger')
    return redirect(url_for('view_donors'))


@app.route('/donors/<int:donor_id>/reactivate', methods=['POST'])
@login_required
@donor_prohibited
def reactivate_donor(donor_id):
    """Reactivate donor profile."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        if column_exists(cursor, 'Donors', 'availability'):
            cursor.execute(
                "UPDATE Donors SET status = 'Active', availability = 'Available', last_active_at = NOW() WHERE id = %s",
                (donor_id,)
            )
        else:
            cursor.execute("UPDATE Donors SET status = 'Active' WHERE id = %s", (donor_id,))
        conn.commit()
        conn.close()
        flash('Donor reactivated successfully.', 'success')
    except Exception as e:
        flash(f'Error reactivating donor: {str(e)}', 'danger')
    return redirect(url_for('view_donors'))


@app.route('/inventory')
@login_required
@donor_prohibited
def view_inventory():
    """View blood inventory"""
    if session.get('role_name') == 'HOSPITAL_USER':
        flash('Hospital users cannot view exact inventory numbers.', 'warning')
        return redirect(url_for('user_mgmt.dashboard'))
    conn = get_db()
    cursor = conn.cursor()
    inventory = get_batch_inventory_summary(cursor)
    conn.close()
    
    return render_template('view_inventory.html', inventory=inventory, inventory_data=inventory)


@app.route('/add-hospital', methods=['GET', 'POST'])
@login_required
@donor_prohibited
def add_hospital():
    """Add new hospital"""
    if session.get('role_name') == 'HOSPITAL_USER':
        flash('Hospital users cannot add hospitals.', 'danger')
        return redirect(url_for('user_mgmt.dashboard'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        contact = request.form.get('contact', '').strip()
        address = request.form.get('address', '').strip()
        email = request.form.get('email', '').strip()
        
        if not all([name, contact, address, email]):
            flash('All fields are required!', 'danger')
            return redirect(url_for('add_hospital'))
        
        if not validate_email(email):
            flash('Invalid email format!', 'danger')
            return redirect(url_for('add_hospital'))
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO Hospitals (name, contact, address, email)
                            VALUES (%s, %s, %s, %s)''',
                         (name, contact, address, email))
            conn.commit()
            conn.close()
            flash('Hospital added successfully!', 'success')
            return redirect(url_for('view_hospitals'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
            return redirect(url_for('add_hospital'))
    
    return render_template('add_hospital.html')


@app.route('/hospitals')
@login_required
@donor_prohibited
def view_hospitals():
    """View all hospitals"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM Hospitals ORDER BY created_at DESC')
    hospitals = dict_from_cursor_list(cursor, cursor.fetchall())
    conn.close()
    
    return render_template('view_hospitals.html', hospitals=hospitals)


@app.route('/add-donation', methods=['GET', 'POST'])
@login_required
@donor_prohibited
def add_donation():
    """Record blood donation"""
    if request.method == 'POST':
        donor_id = request.form.get('donor_id', type=int)
        units = request.form.get('units', type=int)
        donation_date = request.form.get('donation_date')
        health_status = request.form.get('health_status', '').strip()
        
        if not all([donor_id, units, donation_date, health_status]):
            flash('All fields are required!', 'danger')
            return redirect(url_for('add_donation'))
        
        if units <= 0 or units > 5:
            flash('Invalid units! Must be between 1 and 5.', 'danger')
            return redirect(url_for('add_donation'))
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            
            # Get donor blood group
            cursor.execute('SELECT blood_group FROM Donors WHERE id = %s', (donor_id,))
            result = dict_from_cursor(cursor, cursor.fetchone())
            if not result:
                flash('Donor not found!', 'danger')
                conn.close()
                return redirect(url_for('add_donation'))
            
            blood_group = result['blood_group']
            
            # Add donation record
            cursor.execute('''INSERT INTO Donations (donor_id, units, donation_date, blood_group, health_status)
                            VALUES (%s, %s, %s, %s, %s)''',
                         (donor_id, units, donation_date, blood_group, health_status))
            donation_id = cursor.lastrowid

            # Add batch inventory entry (expiry = donation_date + 35 days)
            try:
                donation_dt = datetime.strptime(donation_date, '%Y-%m-%d').date()
            except ValueError:
                donation_dt = date.today()
            expiry_dt = donation_dt + timedelta(days=35)

            cursor.execute(
                '''INSERT INTO blood_batches
                   (blood_group, units_total, units_remaining, donation_date, expiry_date, donor_id, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                (blood_group, units, units, donation_dt, expiry_dt, donor_id, 'Active')
            )

            # Audit log (optional)
            if table_exists(cursor, 'Audit_Logs'):
                cursor.execute(
                    """INSERT INTO Audit_Logs (user_id, action, resource_type, resource_id, status)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (session.get('user_id'), 'donation:create', 'Donation', donation_id, 'Success')
                )
            
            # Update donor's last donation date
            cursor.execute('''UPDATE Donors SET last_donation_date = %s
                            WHERE id = %s''', (donation_date, donor_id))
            
            conn.commit()
            conn.close()
            flash('Donation recorded successfully! Batch inventory updated.', 'success')
            return redirect(url_for('view_donations'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
            return redirect(url_for('add_donation'))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, blood_group FROM Donors WHERE status=%s', ('Active',))
    donors = dict_from_cursor_list(cursor, cursor.fetchall())
    conn.close()
    
    return render_template('add_donation.html', donors=donors)


@app.route('/donations')
@login_required
@donor_prohibited
def view_donations():
    """View all donations"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''SELECT d.id, d.donor_id, don.name as donor_name, don.phone, d.units, d.donation_date,
                      d.blood_group, d.health_status FROM Donations d
                      LEFT JOIN Donors don ON d.donor_id = don.id
                      ORDER BY d.created_at DESC''')
    donations = dict_from_cursor_list(cursor, cursor.fetchall())
    conn.close()
    
    return render_template('view_donations.html', donations=donations)


@app.route('/blood-request', methods=['GET', 'POST'])
@login_required
@donor_prohibited
def make_request():
    """Make blood request from hospital"""
    if request.method == 'POST':
        role_name = session.get('role_name')
        user_id = session.get('user_id')
        hospital_id = request.form.get('hospital_id', type=int)
        blood_group = request.form.get('blood_group', '').strip()
        units_required = request.form.get('units_required', type=int)
        urgency = request.form.get('urgency', 'Normal').strip()
        notes = request.form.get('notes', '').strip()

        if role_name == 'HOSPITAL_USER':
            hospital_id = get_hospital_id_for_user(user_id)

        if not all([hospital_id, blood_group, units_required]):
            flash('All fields are required!', 'danger')
            return redirect(url_for('make_request'))

        if blood_group not in BLOOD_GROUPS:
            flash('Invalid blood group!', 'danger')
            return redirect(url_for('make_request'))

        if units_required <= 0:
            flash('Units must be greater than 0!', 'danger')
            return redirect(url_for('make_request'))

        if urgency not in ['Normal', 'Emergency']:
            urgency = 'Normal'

        try:
            conn = get_db()
            cursor = conn.cursor()

            available_units = get_available_units_for_group(cursor, blood_group)

            # Hospital users always submit pending. Others may auto-approve if stock allows.
            status = 'Pending'
            approval_date = None

            # Add request with optional columns
            columns = ['hospital_id', 'blood_group', 'units_required', 'status', 'approval_date']
            values = [hospital_id, blood_group, units_required, status, approval_date]

            if column_exists(cursor, 'Blood_Requests', 'urgency'):
                columns.append('urgency')
                values.append(urgency)
            if column_exists(cursor, 'Blood_Requests', 'notes'):
                columns.append('notes')
                values.append(notes if notes else None)

            placeholders = ', '.join(['%s'] * len(values))
            cursor.execute(
                f"INSERT INTO Blood_Requests ({', '.join(columns)}) VALUES ({placeholders})",
                tuple(values)
            )
            request_id = cursor.lastrowid
            
            conn.commit()
            conn.close()
            
            if role_name != 'HOSPITAL_USER' and available_units >= units_required:
                success, result = approve_blood_request(request_id=request_id, action='approve', user_id=session.get('user_id'))
                if success:
                    flash('Request approved and batch inventory updated!', 'success')
                else:
                    flash(result.get('message', 'Request submitted and pending approval.'), 'warning')
            else:
                flash('Request submitted and pending approval.', 'success')

            if role_name == 'HOSPITAL_USER':
                return redirect(url_for('user_mgmt.dashboard'))
            return redirect(url_for('view_requests'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
            return redirect(url_for('make_request'))

    conn = get_db()
    cursor = conn.cursor()
    if session.get('role_name') == 'HOSPITAL_USER':
        hospital_id = get_hospital_id_for_user(session.get('user_id'))
        cursor.execute('SELECT id, name FROM Hospitals WHERE id = %s', (hospital_id,))
    else:
        cursor.execute('SELECT id, name FROM Hospitals')
    hospitals = dict_from_cursor_list(cursor, cursor.fetchall())
    conn.close()

    return render_template('make_request.html', hospitals=hospitals, blood_groups=BLOOD_GROUPS)


@app.route('/hospital/requests/create', methods=['POST'])
@login_required
def create_hospital_request():
    """Create a new blood request for the logged-in hospital user."""
    if session.get('role_name') != 'HOSPITAL_USER':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    user_id = session.get('user_id')
    hospital_id = get_hospital_id_for_user(user_id)
    if not hospital_id:
        flash('Hospital not assigned to this user.', 'danger')
        return redirect(url_for('user_mgmt.dashboard'))

    blood_group = request.form.get('blood_group', '').strip()
    units_required = request.form.get('units_required', type=int)
    urgency = request.form.get('urgency', 'Normal').strip()

    if not all([blood_group, units_required]):
        flash('All fields are required.', 'danger')
        return redirect(url_for('user_mgmt.dashboard'))
    if units_required <= 0:
        flash('Units must be greater than 0.', 'danger')
        return redirect(url_for('user_mgmt.dashboard'))
    if urgency not in ['Normal', 'Emergency']:
        urgency = 'Normal'

    try:
        conn = get_db()
        cursor = conn.cursor()

        if blood_group not in BLOOD_GROUPS:
            flash('Invalid blood group!', 'danger')
            conn.close()
            return redirect(url_for('user_mgmt.dashboard'))

        columns = ['hospital_id', 'blood_group', 'units_required', 'status', 'approval_date']
        values = [hospital_id, blood_group, units_required, 'Pending', None]

        if column_exists(cursor, 'Blood_Requests', 'urgency'):
            columns.append('urgency')
            values.append(urgency)

        placeholders = ', '.join(['%s'] * len(values))
        cursor.execute(
            f"INSERT INTO Blood_Requests ({', '.join(columns)}) VALUES ({placeholders})",
            tuple(values)
        )
        conn.commit()
        conn.close()
        flash('Request submitted and pending approval.', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')

    return redirect(url_for('user_mgmt.dashboard'))


@app.route('/hospital/requests/<int:request_id>', methods=['GET'])
@login_required
def hospital_request_detail(request_id):
    """View a single request for the logged-in hospital user."""
    if session.get('role_name') != 'HOSPITAL_USER':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    user_id = session.get('user_id')
    hospital_id = get_hospital_id_for_user(user_id)
    if not hospital_id:
        flash('Hospital not assigned to this user.', 'danger')
        return redirect(url_for('user_mgmt.dashboard'))

    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

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

        cursor.execute(
            f"SELECT {select_fields} FROM Blood_Requests WHERE id = %s AND hospital_id = %s",
            (request_id, hospital_id)
        )
        request_row = cursor.fetchone()
        conn.close()

        if not request_row:
            flash('Request not found.', 'danger')
            return redirect(url_for('user_mgmt.dashboard'))

        return render_template('hospital_request_detail.html', request_item=request_row)
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('user_mgmt.dashboard'))


@app.route('/hospital/requests/<int:request_id>/edit', methods=['POST'])
@login_required
def hospital_request_edit(request_id):
    """Edit a pending request for the logged-in hospital user."""
    if session.get('role_name') != 'HOSPITAL_USER':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    user_id = session.get('user_id')
    hospital_id = get_hospital_id_for_user(user_id)
    if not hospital_id:
        flash('Hospital not assigned to this user.', 'danger')
        return redirect(url_for('user_mgmt.dashboard'))

    blood_group = request.form.get('blood_group', '').strip()
    units_required = request.form.get('units_required', type=int)
    urgency = request.form.get('urgency', 'Normal').strip()

    if not all([blood_group, units_required]):
        flash('All fields are required.', 'danger')
        return redirect(f'/hospital/requests/{request_id}')
    if units_required <= 0:
        flash('Units must be greater than 0.', 'danger')
        return redirect(f'/hospital/requests/{request_id}')
    if urgency not in ['Normal', 'Emergency']:
        urgency = 'Normal'

    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT status FROM Blood_Requests WHERE id = %s AND hospital_id = %s",
            (request_id, hospital_id)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            flash('Request not found.', 'danger')
            return redirect(url_for('user_mgmt.dashboard'))
        if row[0] != 'Pending':
            conn.close()
            flash('Only pending requests can be edited.', 'warning')
            return redirect(f'/hospital/requests/{request_id}')

        update_fields = ["blood_group = %s", "units_required = %s"]
        params = [blood_group, units_required]
        if column_exists(cursor, 'Blood_Requests', 'urgency'):
            update_fields.append("urgency = %s")
            params.append(urgency)

        params.append(request_id)
        params.append(hospital_id)
        cursor.execute(
            f"UPDATE Blood_Requests SET {', '.join(update_fields)} WHERE id = %s AND hospital_id = %s",
            tuple(params)
        )
        conn.commit()
        conn.close()
        flash('Request updated successfully.', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')

    return redirect(f'/hospital/requests/{request_id}')


@app.route('/hospital/requests/<int:request_id>/cancel', methods=['POST'])
@login_required
def hospital_request_cancel(request_id):
    """Cancel a pending request for the logged-in hospital user."""
    if session.get('role_name') != 'HOSPITAL_USER':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    user_id = session.get('user_id')
    hospital_id = get_hospital_id_for_user(user_id)
    if not hospital_id:
        flash('Hospital not assigned to this user.', 'danger')
        return redirect(url_for('user_mgmt.dashboard'))

    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT status FROM Blood_Requests WHERE id = %s AND hospital_id = %s",
            (request_id, hospital_id)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            flash('Request not found.', 'danger')
            return redirect(url_for('user_mgmt.dashboard'))
        if row[0] != 'Pending':
            conn.close()
            flash('Only pending requests can be cancelled.', 'warning')
            return redirect(f'/hospital/requests/{request_id}')

        if column_exists(cursor, 'Blood_Requests', 'rejection_reason'):
            cursor.execute(
                "UPDATE Blood_Requests SET status = 'Rejected', rejection_reason = %s WHERE id = %s AND hospital_id = %s",
                ('Cancelled by hospital', request_id, hospital_id)
            )
        else:
            cursor.execute(
                "UPDATE Blood_Requests SET status = 'Rejected' WHERE id = %s AND hospital_id = %s",
                (request_id, hospital_id)
            )

        conn.commit()
        conn.close()
        flash('Request cancelled.', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')

    return redirect(url_for('user_mgmt.dashboard'))


@app.route('/admin/bootstrap-accounts', methods=['GET', 'POST'])
@login_required
def bootstrap_accounts():
    """Create login accounts for donors and hospitals (SUPER_ADMIN only)."""
    if session.get('role_name') != 'SUPER_ADMIN':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    if request.method == 'GET':
        return render_template('admin/bootstrap_accounts.html', created=None)

    created = {
        'donors': [],
        'hospitals': []
    }

    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM Roles WHERE role_name = 'DONOR'")
        donor_role = cursor.fetchone()
        cursor.execute("SELECT id FROM Roles WHERE role_name = 'HOSPITAL_USER'")
        hospital_role = cursor.fetchone()

        if not donor_role or not hospital_role:
            conn.close()
            flash('Required roles are missing. Run RBAC setup first.', 'danger')
            return render_template('admin/bootstrap_accounts.html', created=created)

        donor_role_id = donor_role[0]
        hospital_role_id = hospital_role[0]

        has_donor_id = column_exists(cursor, 'Users_RBAC', 'donor_id')
        has_full_name = column_exists(cursor, 'Users_RBAC', 'full_name')
        donors_has_email = column_exists(cursor, 'Donors', 'email')

        # Donor accounts
        donor_select = "id, name, phone, blood_group"
        if donors_has_email:
            donor_select += ", email"
        else:
            donor_select += ", NULL as email"

        cursor.execute(f"SELECT {donor_select} FROM Donors")
        donors = cursor.fetchall()

        for donor in donors:
            donor_id, name, phone, blood_group, email = donor
            username = f"donor{donor_id}"
            login_email = email if email else f"donor{donor_id}@donors.local"

            if has_donor_id:
                cursor.execute(
                    "SELECT id FROM Users_RBAC WHERE donor_id = %s LIMIT 1",
                    (donor_id,)
                )
                if cursor.fetchone():
                    continue
            else:
                cursor.execute(
                    "SELECT id FROM Users_RBAC WHERE username = %s OR email = %s LIMIT 1",
                    (username, login_email)
                )
                if cursor.fetchone():
                    continue

            password_plain = generate_password()
            password_hash = generate_password_hash(password_plain)

            columns = ['username', 'email', 'password_hash', 'role_id', 'is_active', 'created_at']
            values = [username, login_email, password_hash, donor_role_id, True, datetime.now()]

            if has_full_name:
                columns.append('full_name')
                values.append(name)
            if has_donor_id:
                columns.append('donor_id')
                values.append(donor_id)

            placeholders = ', '.join(['%s'] * len(values))
            cursor.execute(
                f"INSERT INTO Users_RBAC ({', '.join(columns)}) VALUES ({placeholders})",
                tuple(values)
            )

            created['donors'].append({
                'name': name,
                'blood_group': blood_group,
                'phone': phone,
                'username': username,
                'email': login_email,
                'password': password_plain
            })

        # Hospital accounts
        cursor.execute("SELECT id, name, email FROM Hospitals")
        hospitals = cursor.fetchall()

        for hospital_id, name, email in hospitals:
            username = f"hospital{hospital_id}"
            login_email = email if email else f"hospital{hospital_id}@hospitals.local"

            cursor.execute(
                "SELECT id FROM Users_RBAC WHERE hospital_id = %s AND role_id = %s LIMIT 1",
                (hospital_id, hospital_role_id)
            )
            if cursor.fetchone():
                continue

            password_plain = generate_password()
            password_hash = generate_password_hash(password_plain)

            columns = ['username', 'email', 'password_hash', 'role_id', 'hospital_id', 'is_active', 'created_at']
            values = [username, login_email, password_hash, hospital_role_id, hospital_id, True, datetime.now()]

            if has_full_name:
                columns.append('full_name')
                values.append(name)

            placeholders = ', '.join(['%s'] * len(values))
            cursor.execute(
                f"INSERT INTO Users_RBAC ({', '.join(columns)}) VALUES ({placeholders})",
                tuple(values)
            )

            created['hospitals'].append({
                'name': name,
                'username': username,
                'email': login_email,
                'password': password_plain
            })

        conn.commit()
        conn.close()

        flash('Bootstrap accounts created successfully.', 'success')
    except Exception as e:
        flash(f'Error creating accounts: {str(e)}', 'danger')

    return render_template('admin/bootstrap_accounts.html', created=created)


@app.route('/requests')
@login_required
@donor_prohibited
def view_requests():
    """View all blood requests"""
    if session.get('role_name') == 'HOSPITAL_USER':
        return redirect(url_for('user_mgmt.dashboard'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''SELECT br.id, br.hospital_id, h.name as hospital_name, br.blood_group,
                      br.units_required, br.status, br.request_date, br.approval_date,
                      COALESCE(bi.total_units, 0) as available_units
                      FROM Blood_Requests br
                      LEFT JOIN Hospitals h ON br.hospital_id = h.id
                      LEFT JOIN (
                          SELECT blood_group, SUM(units_remaining) as total_units
                          FROM blood_batches
                          WHERE expiry_date > CURDATE() AND status = 'Active'
                          GROUP BY blood_group
                      ) bi ON br.blood_group = bi.blood_group
                      ORDER BY br.request_date DESC''')
    requests = dict_from_cursor_list(cursor, cursor.fetchall())
    conn.close()
    
    return render_template('view_requests.html', requests=requests)


@app.route('/update-request/<int:request_id>/<status>', methods=['GET'])
@login_required
@donor_prohibited
def update_request_status(request_id, status):
    """Update blood request status"""
    if session.get('role_name') not in ['BLOOD_BANK_ADMIN', 'SUPER_ADMIN']:
        flash('Only blood bank admins can approve or reject requests.', 'danger')
        return redirect(url_for('view_requests'))
    if status not in ['Approved', 'Rejected']:
        flash('Invalid status!', 'danger')
        return redirect(url_for('view_requests'))
    
    try:
        if status == 'Approved':
            success, result = approve_blood_request(
                request_id=request_id,
                action='approve',
                user_id=session.get('user_id')
            )
            if not success:
                flash(result.get('message', 'Approval failed.'), 'danger')
                return redirect(url_for('view_requests'))
        else:
            conn = get_db()
            cursor = conn.cursor()
            approval_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute(
                '''UPDATE Blood_Requests SET status = %s, approval_date = %s
                   WHERE id = %s''',
                (status, approval_date, request_id)
            )
            conn.commit()
            conn.close()
        
        flash(f'Request {status.lower()} successfully!', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('view_requests'))


@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change password for the logged-in user."""
    if request.method == 'GET':
        return render_template('change_password.html')

    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not current_password or not new_password or not confirm_password:
        flash('All fields are required.', 'danger')
        return redirect(url_for('change_password'))
    if new_password != confirm_password:
        flash('New passwords do not match.', 'danger')
        return redirect(url_for('change_password'))
    if len(new_password) < 8:
        flash('New password must be at least 8 characters.', 'danger')
        return redirect(url_for('change_password'))

    user_id = session.get('user_id')

    try:
        conn = get_db()
        cursor = conn.cursor()

        # Try RBAC user first
        cursor.execute(
            "SELECT password_hash FROM Users_RBAC WHERE id = %s",
            (user_id,)
        )
        row = cursor.fetchone()
        if row:
            stored_hash = row[0]
            password_ok = False
            if stored_hash:
                if stored_hash.startswith(('pbkdf2:', 'scrypt:')):
                    password_ok = check_password_hash(stored_hash, current_password)
                else:
                    password_ok = stored_hash == current_password

            if not password_ok:
                conn.close()
                flash('Current password is incorrect.', 'danger')
                return redirect(url_for('change_password'))

            new_hash = generate_password_hash(new_password)
            if column_exists(cursor, 'Users_RBAC', 'password_changed_at'):
                cursor.execute(
                    "UPDATE Users_RBAC SET password_hash = %s, password_changed_at = NOW() WHERE id = %s",
                    (new_hash, user_id)
                )
            else:
                cursor.execute(
                    "UPDATE Users_RBAC SET password_hash = %s WHERE id = %s",
                    (new_hash, user_id)
                )
            conn.commit()
            conn.close()
            flash('Password updated successfully.', 'success')
            return redirect(url_for('index'))

        # Legacy Users table
        cursor.execute(
            "SELECT password FROM Users WHERE id = %s",
            (user_id,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            flash('User record not found.', 'danger')
            return redirect(url_for('change_password'))

        if row[0] != current_password:
            conn.close()
            flash('Current password is incorrect.', 'danger')
            return redirect(url_for('change_password'))

        cursor.execute(
            "UPDATE Users SET password = %s WHERE id = %s",
            (new_password, user_id)
        )
        conn.commit()
        conn.close()
        flash('Password updated successfully.', 'success')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error updating password: {str(e)}', 'danger')
        return redirect(url_for('change_password'))


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Start password reset flow."""
    if request.method == 'GET':
        return render_template('forgot_password.html', reset_link=None)

    identifier = request.form.get('identifier', '').strip()
    if not identifier:
        flash('Please enter your username or email.', 'danger')
        return render_template('forgot_password.html', reset_link=None)

    reset_link = None

    try:
        conn = get_db()
        cursor = conn.cursor()
        ensure_password_reset_table(cursor)

        # Try RBAC users
        cursor.execute(
            "SELECT id FROM Users_RBAC WHERE username = %s OR email = %s LIMIT 1",
            (identifier, identifier)
        )
        row = cursor.fetchone()
        user_table = None
        user_id = None
        if row:
            user_id = row[0]
            user_table = 'RBAC'
        else:
            cursor.execute(
                "SELECT id FROM Users WHERE username = %s OR email = %s LIMIT 1",
                (identifier, identifier)
            )
            row = cursor.fetchone()
            if row:
                user_id = row[0]
                user_table = 'LEGACY'

        if user_id and user_table:
            raw_token = secrets.token_urlsafe(32)
            token_hash = hash_reset_token(raw_token)
            expires_at = datetime.now() + timedelta(hours=1)

            cursor.execute(
                """
                INSERT INTO Password_Reset_Tokens (user_id, user_table, token_hash, expires_at, used)
                VALUES (%s, %s, %s, %s, FALSE)
                """,
                (user_id, user_table, token_hash, expires_at)
            )
            conn.commit()
            reset_link = url_for('reset_password', token=raw_token)

        conn.close()
        flash('If the account exists, a reset link is available below.', 'success')
    except Exception as e:
        flash(f'Error generating reset link: {str(e)}', 'danger')

    return render_template('forgot_password.html', reset_link=reset_link)


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    """Complete password reset using a token."""
    token = request.args.get('token') if request.method == 'GET' else request.form.get('token')
    if not token:
        flash('Reset token is missing.', 'danger')
        return redirect(url_for('forgot_password'))

    if request.method == 'GET':
        return render_template('reset_password.html', token=token)

    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not new_password or not confirm_password:
        flash('All fields are required.', 'danger')
        return render_template('reset_password.html', token=token)
    if new_password != confirm_password:
        flash('Passwords do not match.', 'danger')
        return render_template('reset_password.html', token=token)
    if len(new_password) < 8:
        flash('Password must be at least 8 characters.', 'danger')
        return render_template('reset_password.html', token=token)

    try:
        conn = get_db()
        cursor = conn.cursor()
        ensure_password_reset_table(cursor)

        token_hash = hash_reset_token(token)
        cursor.execute(
            """
            SELECT id, user_id, user_table, expires_at, used
            FROM Password_Reset_Tokens
            WHERE token_hash = %s
            LIMIT 1
            """,
            (token_hash,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            flash('Invalid or expired token.', 'danger')
            return redirect(url_for('forgot_password'))

        token_id, user_id, user_table, expires_at, used = row
        if used or expires_at < datetime.now():
            conn.close()
            flash('Invalid or expired token.', 'danger')
            return redirect(url_for('forgot_password'))

        if user_table == 'RBAC':
            new_hash = generate_password_hash(new_password)
            if column_exists(cursor, 'Users_RBAC', 'password_changed_at'):
                cursor.execute(
                    "UPDATE Users_RBAC SET password_hash = %s, password_changed_at = NOW(), failed_login_attempts = 0 WHERE id = %s",
                    (new_hash, user_id)
                )
            else:
                cursor.execute(
                    "UPDATE Users_RBAC SET password_hash = %s, failed_login_attempts = 0 WHERE id = %s",
                    (new_hash, user_id)
                )
        else:
            cursor.execute(
                "UPDATE Users SET password = %s WHERE id = %s",
                (new_password, user_id)
            )

        cursor.execute(
            "UPDATE Password_Reset_Tokens SET used = TRUE WHERE id = %s",
            (token_id,)
        )
        conn.commit()
        conn.close()
        flash('Password reset successfully. Please log in.', 'success')
        return redirect(url_for('login'))
    except Exception as e:
        flash(f'Error resetting password: {str(e)}', 'danger')
        return redirect(url_for('forgot_password'))


@app.route('/api/inventory')
@login_required
@donor_prohibited
def api_inventory():
    """API endpoint for inventory data"""
    conn = get_db()
    cursor = conn.cursor()
    inventory = get_batch_inventory_summary(cursor)
    conn.close()
    
    return jsonify(make_serializable(inventory))

@app.route('/api/donors')
@login_required
@donor_prohibited
def api_donors():
    """API endpoint for donors data"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, blood_group, phone, last_donation_date FROM Donors ORDER BY name')
    donors = dict_from_cursor_list(cursor, cursor.fetchall())
    conn.close()
    
    return jsonify(make_serializable(donors))


@app.route('/healthz')
def healthz():
    """Lightweight health check endpoint for deployment probes."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        app.logger.error("Health check failed: %s", str(e))
        return jsonify({'status': 'error', 'message': 'database unavailable'}), 500


@app.route('/audit-logs')
@login_required
@donor_prohibited
def audit_logs():
    """View audit logs (admin only)."""
    if session.get('role_name') not in ['BLOOD_BANK_ADMIN', 'SUPER_ADMIN']:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        if not table_exists(cursor, 'Audit_Logs'):
            conn.close()
            flash('Audit logs not available in this database.', 'warning')
            return render_template('audit_logs.html', logs=[], all_logs=True)

        cursor.execute("""
            SELECT 
                al.id,
                u.username,
                al.action,
                al.resource_type,
                al.resource_id,
                al.status,
                al.created_at
            FROM Audit_Logs al
            LEFT JOIN Users_RBAC u ON al.user_id = u.id
            ORDER BY al.created_at DESC
            LIMIT 200
        """)
        logs = cursor.fetchall() or []
        conn.close()
        return render_template('audit_logs.html', logs=logs, all_logs=True)
    except Exception as e:
        flash(f'Error loading audit logs: {str(e)}', 'danger')
        return redirect(url_for('index'))


# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(error):
    """Handle 500 errors"""
    app.logger.error("Internal server error: %s", error, exc_info=True)
    return render_template('500.html'), 500

@app.route('/search', methods=['GET'])
@login_required
@donor_prohibited
def search():
    """Search functionality for donors, hospitals, and inventory."""
    query = request.args.get('query', '').strip()
    search_type = request.args.get('type', 'donors')

    conn = get_db()
    cursor = conn.cursor()

    if search_type == 'donors':
        cursor.execute('''SELECT * FROM Donors WHERE name LIKE %s OR blood_group LIKE %s''', (f"%{query}%", f"%{query}%"))
    elif search_type == 'hospitals':
        cursor.execute('''SELECT * FROM Hospitals WHERE name LIKE %s OR address LIKE %s''', (f"%{query}%", f"%{query}%"))
    elif search_type == 'inventory':
        summary = get_batch_inventory_summary(cursor)
        results = [item for item in summary if query.lower() in (item.get('blood_group') or '').lower()]
        conn.close()
        return jsonify(make_serializable(results))
    else:
        return jsonify({"error": "Invalid search type"}), 400

    results = dict_from_cursor_list(cursor, cursor.fetchall())
    conn.close()

    return jsonify(make_serializable(results))

@app.route('/filter', methods=['GET'])
@login_required
@donor_prohibited
def filter_data():
    """Filter and sort data for donors and inventory."""
    filter_type = request.args.get('type', 'donors')
    sort_by = request.args.get('sort_by', 'name')
    order = request.args.get('order', 'asc')

    # Whitelist allowed columns to prevent SQL injection
    ALLOWED_DONOR_COLUMNS = {'name', 'age', 'blood_group', 'phone', 'created_at', 'status'}
    ALLOWED_INVENTORY_COLUMNS = {'blood_group', 'quantity_units'}
    order_dir = 'ASC' if order == 'asc' else 'DESC'

    conn = get_db()
    cursor = conn.cursor()

    if filter_type == 'donors':
        if sort_by not in ALLOWED_DONOR_COLUMNS:
            sort_by = 'name'
        query = f"SELECT * FROM Donors ORDER BY {sort_by} {order_dir}"
    elif filter_type == 'inventory':
        if sort_by not in ALLOWED_INVENTORY_COLUMNS:
            sort_by = 'blood_group'
        results = get_batch_inventory_summary(cursor)
        conn.close()
        sorted_results = sorted(
            results,
            key=lambda item: item.get(sort_by) or 0,
            reverse=(order_dir == 'DESC')
        )
        return jsonify(make_serializable(sorted_results))
    else:
        conn.close()
        return jsonify({"error": "Invalid filter type"}), 400

    cursor.execute(query)
    results = dict_from_cursor_list(cursor, cursor.fetchall())
    conn.close()

    return jsonify(make_serializable(results))

# ==================== IMPORT ROUTES ====================
# Import and register route blueprints
try:
    from user_routes import register_user_management_routes
    register_user_management_routes(app)
    print("[OK] User management routes registered")
except ImportError as e:
    print(f"[WARN] Could not import user_routes: {e}")

try:
    from transaction_routes import register_transaction_routes
    register_transaction_routes(app)
    print("[OK] Transaction routes registered")
except ImportError as e:
    print(f"[WARN] Could not import transaction_routes: {e}")

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
