#!/usr/bin/env python3
"""
Blood Bank Management System - Database Setup Script
This script creates the database and tables automatically
"""

import mysql.connector
from mysql.connector import Error
import sys

# Database credentials
DB_HOST = 'localhost'
DB_USER = 'root'
DB_PASSWORD = 'jefrin'  # Default password - change if needed
DB_NAME = 'blood_bank_db'

def run_sql_file(connection, filepath):
    """Execute SQL commands from a file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # Split by ; to handle multiple statements
        statements = [s.strip() for s in sql_content.split(';') if s.strip()]
        
        cursor = connection.cursor()
        
        for statement in statements:
            if statement:
                try:
                    print(f"Executing: {statement[:80]}...")
                    cursor.execute(statement)
                    connection.commit()
                except Error as e:
                    # Some statements might fail if already exist, that's OK
                    if "already exists" in str(e) or "Trigger" in str(e):
                        print(f"  ℹ️  Skipped (already exists): {str(e)[:60]}")
                    else:
                        print(f"  ⚠️  Error: {e}")
        
        cursor.close()
        print("✅ Database setup completed!")
        return True
        
    except Error as e:
        print(f"❌ Error executing SQL: {e}")
        return False

def main():
    """Main setup function"""
    print("="*70)
    print("🩸 Blood Bank Management System - Database Setup")
    print("="*70)
    
    # Try multiple password options
    passwords_to_try = ['jefrin', 'root', 'password', '123456', 'mysql']
    
    connection = None
    
    for password_attempt in passwords_to_try:
        try:
            # Try to connect to MySQL
            print(f"\n📡 Attempting connection to MySQL as {DB_USER}@{DB_HOST}...")
            print(f"   Password: {'(empty)' if not password_attempt else '(masked)'}")
            
            try:
                connection = mysql.connector.connect(
                    host=DB_HOST,
                    user=DB_USER,
                    password=password_attempt
                )
                print("✅ Connected to MySQL!")
                
                # Update the global password
                globals()['DB_PASSWORD'] = password_attempt
                
                # Execute schema.sql
                print(f"\n📝 Setting up database schema from schema.sql...")
                if run_sql_file(connection, 'd:\\BBMS\\schema.sql'):
                    print("\n✅ Database setup successful!")
                    print("\n" + "="*70)
                    print("Next steps:")
                    print(f"  1. Update password in app.py line 20: DB_PASSWORD = '{password_attempt}'")
                    print("  2. Run: python app.py")
                    print("  3. Open: http://localhost:5000")
                    print("="*70)
                    return True
                else:
                    return False
                    
            except Error as e:
                if "Access denied" in str(e):
                    print(f"  ❌ Access denied with this password")
                    continue
                raise
                
        except Exception as e:
            continue
        finally:
            if connection and connection.is_connected():
                connection.close()
    
    print("\n❌ Could not connect to MySQL with any default password")
    print("   Please ensure MySQL is running and check your credentials")
    return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
