#!/usr/bin/env python3
"""
Migration Script: Move existing admin to new Users_RBAC table
This script migrates your current admin account to the new user management system
"""

import mysql.connector
from werkzeug.security import generate_password_hash
import sys

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'jefrin',
    'database': 'blood_bank_db'
}

def migrate_admin():
    """
    Migrate existing admin account to new Users_RBAC table
    Creates admin as SUPER_ADMIN with password hash
    """
    
    try:
        # Connect to database
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()
        
        print("🔄 Starting admin migration...")
        print()
        
        # Hash the password 'admin123'
        password = 'admin123'
        password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        
        print(f"✓ Password hashed: {password}")
        print(f"✓ Hash: {password_hash[:50]}...")
        print()
        
        # Check if admin already exists in Users_RBAC
        check_query = "SELECT id FROM Users_RBAC WHERE username = 'admin' LIMIT 1"
        cursor.execute(check_query)
        existing = cursor.fetchone()
        
        if existing:
            print("⚠️  Admin already exists in Users_RBAC table!")
            print(f"   ID: {existing[0]}")
            response = input("   Do you want to update it? (yes/no): ").lower()
            
            if response != 'yes':
                print("❌ Migration cancelled.")
                cursor.close()
                connection.close()
                return False
            
            # Update existing admin
            update_query = """
                UPDATE Users_RBAC 
                SET 
                    email = %s,
                    password_hash = %s,
                    role_id = 1,
                    is_active = TRUE,
                    created_at = NOW()
                WHERE username = %s
            """
            cursor.execute(update_query, ('admin@blood.local', password_hash, 'admin'))
            print("✓ Existing admin account updated")
        else:
            # Insert new admin as SUPER_ADMIN (role_id = 1)
            insert_query = """
                INSERT INTO Users_RBAC (username, email, password_hash, role_id, is_active, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
            """
            cursor.execute(insert_query, ('admin', 'admin@blood.local', password_hash, 1, True))
            print("✓ New admin account created in Users_RBAC")
        
        connection.commit()
        
        print()
        print("✅ Migration successful!")
        print()
        print("📋 Admin Account Details:")
        print("   Username: admin")
        print("   Email:    admin@blood.local")
        print("   Password: admin123")
        print("   Role:     SUPER_ADMIN (id=1)")
        print()
        
        # Verify the migration
        verify_query = "SELECT id, username, email, role_id, is_active FROM Users_RBAC WHERE username = 'admin'"
        cursor.execute(verify_query)
        result = cursor.fetchone()
        
        if result:
            print("✓ Verification:")
            print(f"  - ID: {result[0]}")
            print(f"  - Username: {result[1]}")
            print(f"  - Email: {result[2]}")
            print(f"  - Role ID: {result[3]} (SUPER_ADMIN)")
            print(f"  - Active: {result[4]}")
        
        cursor.close()
        connection.close()
        
        return True
        
    except mysql.connector.Error as err:
        print(f"❌ Database error: {err}")
        return False
    except Exception as err:
        print(f"❌ Error: {err}")
        return False


def main():
    """Main function"""
    print("=" * 60)
    print("🔐 Admin Migration Script")
    print("=" * 60)
    print()
    print("This script will migrate your existing admin account")
    print("from the old system to the new Users_RBAC table.")
    print()
    
    # Check database config
    print("Database Configuration:")
    print(f"  Host:     {DB_CONFIG['host']}")
    print(f"  User:     {DB_CONFIG['user']}")
    print(f"  Database: {DB_CONFIG['database']}")
    print()
    
    response = input("Continue with migration? (yes/no): ").lower()
    if response != 'yes':
        print("❌ Migration cancelled.")
        sys.exit(0)
    
    print()
    success = migrate_admin()
    
    if success:
        print()
        print("=" * 60)
        print("🎉 You can now login with:")
        print("   Email/Username: admin")
        print("   Password:       admin123")
        print("=" * 60)
        sys.exit(0)
    else:
        print()
        print("❌ Migration failed. Please check the error above.")
        sys.exit(1)


if __name__ == '__main__':
    main()
