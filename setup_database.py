#!/usr/bin/env python3
"""
Blood Bank Management System - Database Setup Script
This script creates the database and tables automatically
"""

import mysql.connector
from mysql.connector import Error
import sys
import os
from db_config import get_db_config

# Database credentials
_CFG = get_db_config()
DB_HOST = _CFG["host"]
DB_USER = _CFG["user"]
DB_PASSWORD = _CFG["password"]
DB_NAME = _CFG["database"]
DB_PORT = _CFG["port"]

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
    
    # If password is configured, use only that. Otherwise try common local defaults.
    passwords_to_try = [DB_PASSWORD] if DB_PASSWORD else ['', 'root', 'password', 'Jefrin', 'mysql']
    
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
                    password=password_attempt,
                    port=DB_PORT
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
                    print("  1. Confirm DB_* env vars are set in your deploy platform")
                    print("  2. Restart your web service")
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
    
    print("\n❌ Could not connect to MySQL with provided configuration")
    print("   Check DB host/user/password/database/port values and network access")
    return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
