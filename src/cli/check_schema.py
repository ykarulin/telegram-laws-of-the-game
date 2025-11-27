#!/usr/bin/env python3
"""Check current database schema."""

import psycopg2
import os
import sys

def check_schema():
    """Check what tables and columns exist in the database."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)

    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()

        # Check if messages table exists
        cursor.execute("""
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables
                WHERE table_name='messages'
            )
        """)
        messages_exists = cursor.fetchone()[0]
        print(f"Messages table exists: {messages_exists}")

        if messages_exists:
            # Get columns in messages table
            cursor.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name='messages'
                ORDER BY ordinal_position
            """)
            print("\nMessages table columns:")
            for col_name, col_type in cursor.fetchall():
                print(f"  - {col_name}: {col_type}")

        # Check if documents table exists
        cursor.execute("""
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables
                WHERE table_name='documents'
            )
        """)
        documents_exists = cursor.fetchone()[0]
        print(f"\nDocuments table exists: {documents_exists}")

        if documents_exists:
            # Get columns in documents table
            cursor.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name='documents'
                ORDER BY ordinal_position
            """)
            print("\nDocuments table columns:")
            for col_name, col_type in cursor.fetchall():
                print(f"  - {col_name}: {col_type}")

        cursor.close()
        conn.close()

    except psycopg2.Error as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    check_schema()
