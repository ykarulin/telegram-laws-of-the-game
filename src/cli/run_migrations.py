#!/usr/bin/env python3
"""Database migration runner."""

import psycopg2
import os
import sys

def split_sql_statements(sql_content):
    """Split SQL content into individual statements."""
    # Remove comments and normalize whitespace
    lines = []
    for line in sql_content.split('\n'):
        # Remove SQL comments
        if '--' in line:
            line = line[:line.index('--')]
        line = line.strip()
        if line:
            lines.append(line)

    # Join lines and split by semicolon
    content = ' '.join(lines)
    statements = [s.strip() for s in content.split(';') if s.strip()]
    return statements

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
            "migrations/004_rename_metadata_column.sql",
            "migrations/005_convert_telegram_ids_to_bigint.sql",
        ]

        for migration_file in files:
            try:
                with open(migration_file) as f:
                    sql_content = f.read()

                # Split and execute individual statements
                statements = split_sql_statements(sql_content)
                for stmt in statements:
                    try:
                        cursor.execute(stmt)
                    except psycopg2.Error as e:
                        # Skip "already exists" errors for idempotent operations
                        error_msg = str(e).lower()
                        if "already exists" in error_msg or "duplicate key" in error_msg:
                            print(f"  ⚠️  Skipped (already exists): {stmt[:50]}...")
                            conn.rollback()
                            cursor = conn.cursor()
                            continue
                        else:
                            raise

                print(f"✓ Executed {migration_file} ({len(statements)} statements)")
            except FileNotFoundError:
                print(f"⚠️  Migration file not found: {migration_file}")
                continue
            except psycopg2.Error as e:
                print(f"✗ Error executing {migration_file}: {e}")
                print(f"   (This may indicate a partially migrated or corrupted schema)")
                sys.exit(1)

        cursor.close()
        conn.close()
        print("✅ Migrations completed!")

    except psycopg2.Error as e:
        print(f"ERROR: Database connection failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migrations()
