#!/usr/bin/env python3
"""Database migration runner."""

import psycopg2
import os
import sys

def run_migrations():
    """Execute all migration files in order."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)

    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cursor = conn.cursor()

        files = [
            "migrations/001_initial_schema.sql",
            "migrations/002_add_documents_table.sql",
            "migrations/003_add_relative_path_to_documents.sql",
        ]

        for migration_file in files:
            try:
                with open(migration_file) as f:
                    sql_content = f.read()
                cursor.execute(sql_content)
                print(f"✓ Executed {migration_file}")
            except FileNotFoundError:
                print(f"⚠️  Migration file not found: {migration_file}")
                continue
            except psycopg2.Error as e:
                print(f"✗ Error executing {migration_file}: {e}")
                sys.exit(1)

        cursor.close()
        conn.close()
        print("✅ Migrations completed!")

    except psycopg2.Error as e:
        print(f"ERROR: Database connection failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migrations()
