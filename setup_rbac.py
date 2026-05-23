#!/usr/bin/env python3
"""
Blood Bank RBAC System - Quick Setup Script
Run this after running rbac_schema.sql to populate test data
"""

import mysql.connector
from mysql.connector import Error
import os
from db_config import get_db_config

DB_CONFIG = {
    **get_db_config()
}

def create_test_users():
    """Create test users with different roles"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        test_users = [
            # (username, email, password, full_name, role_name, hospital_id)
            ('super_admin', 'super@bloodbank.com', 'admin123', 'Super Administrator', 'SUPER_ADMIN', None),
            ('bank_admin', 'admin@bloodbank.com', 'admin123', 'Blood Bank Administrator', 'BLOOD_BANK_ADMIN', None),
            ('hospital_user_1', 'user@hospital1.com', 'user123', 'Hospital 1 Staff', 'HOSPITAL_USER', 1),
            ('hospital_user_2', 'user@hospital2.com', 'user123', 'Hospital 2 Staff', 'HOSPITAL_USER', 2),
            ('staff', 'staff@bloodbank.com', 'staff123', 'Data Entry Staff', 'STAFF_MEMBER', None),
            ('donor_blood', 'donor@example.com', 'donor123', 'John Donor', 'DONOR', None),
        ]
        
        for username, email, password, full_name, role_name, hospital_id in test_users:
            # Get role ID
            cursor.execute("SELECT id FROM Roles WHERE role_name = %s", (role_name,))
            role = cursor.fetchone()
            
            if not role:
                print(f"❌ Role '{role_name}' not found!")
                continue
            
            role_id = role[0]
            
            # Check if user already exists
            cursor.execute("SELECT id FROM Users_RBAC WHERE username = %s", (username,))
            if cursor.fetchone():
                print(f"⏭️  User '{username}' already exists")
                continue
            
            # Create user
            cursor.execute("""
                INSERT INTO Users_RBAC 
                (username, email, password_hash, full_name, role_id, hospital_id, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            """, (username, email, password, full_name, role_id, hospital_id))
            
            print(f"✅ Created user: {username} ({role_name})")
        
        conn.commit()
        cursor.close()
        conn.close()
        print("\n✅ Test users created successfully!")
        
    except Error as e:
        print(f"❌ Error: {e}")

def verify_setup():
    """Verify RBAC tables exist"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        tables_to_check = [
            'Roles',
            'Permissions',
            'Role_Permissions',
            'Users_RBAC',
            'Audit_Logs'
        ]
        
        print("\n🔍 Verifying RBAC tables...")
        for table in tables_to_check:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"   ✅ {table}: {count} records")
        
        cursor.close()
        conn.close()
        return True
        
    except Error as e:
        print(f"❌ Verification failed: {e}")
        return False

def main():
    """Main setup flow"""
    print("="*60)
    print("🔐 Blood Bank RBAC System - Setup")
    print("="*60)
    
    print("\n1️⃣  Verifying database...")
    if not verify_setup():
        print("\n❌ RBAC tables not found!")
        print("   Please run this first:")
        print("   mysql -u root -p blood_bank_db < rbac_schema.sql")
        return
    
    print("\n2️⃣  Creating test users...")
    create_test_users()
    
    print("\n" + "="*60)
    print("✅ Setup Complete!")
    print("="*60)
    print("\n📋 TEST USERS CREATED:")
    print("   1. super_admin / admin123 (SUPER_ADMIN)")
    print("   2. bank_admin / admin123 (BLOOD_BANK_ADMIN)")
    print("   3. hospital_user_1 / user123 (HOSPITAL_USER - Hospital 1)")
    print("   4. hospital_user_2 / user123 (HOSPITAL_USER - Hospital 2)")
    print("   5. staff / staff123 (STAFF_MEMBER)")
    print("   6. donor_blood / donor123 (DONOR)")
    
    print("\n🚀 Next Steps:")
    print("   1. Update app.py to import RBAC modules")
    print("   2. Register RBAC routes: register_secure_routes(app)")
    print("   3. Update database credentials in rbac.py")
    print("   4. Start Flask: python app.py")
    print("   5. Login at http://localhost:5000/login")
    
    print("\n📚 Documentation:")
    print("   - RBAC_INTEGRATION_GUIDE.md (Complete integration)")
    print("   - RBAC_CHEATSHEET.md (Quick reference)")
    print("   - RBAC_IMPLEMENTATION_SUMMARY.md (Architecture & concepts)")
    
    print("\n🧪 To Test Security:")
    print("   1. Login as hospital_user_1")
    print("   2. Create a blood request")
    print("   3. Try to approve it → Should be DENIED")
    print("   4. Login as bank_admin")
    print("   5. Approve the request → Should SUCCEED")
    print("   6. Check audit logs for complete trail")
    
    print("\n" + "="*60)

if __name__ == '__main__':
    main()
