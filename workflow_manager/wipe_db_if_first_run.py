import os
import sys
from pathlib import Path
import django

# Add the current directory to sys.path so we can import settings
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "workflow_manager.settings")
django.setup()

from django.conf import settings
from django.core.management import call_command

def main():
    # Determine the flag file location
    # If RAILWAY_VOLUME_MOUNT_PATH is defined, store it there to persist across deploys
    # Otherwise, store it in the base directory of the project
    volume_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    if volume_path:
        flag_file = Path(volume_path) / ".db_wiped_fr"
    else:
        flag_file = settings.BASE_DIR / ".db_wiped_fr"

    if flag_file.exists():
        print("Database has already been wiped on first run. Skipping.")
        return

    print("First run detected: wiping database...")
    db_config = settings.DATABASES.get("default", {})
    engine = db_config.get("ENGINE", "")

    if "sqlite" in engine:
        sqlite_path = Path(db_config.get("NAME"))
        if sqlite_path.exists():
            try:
                sqlite_path.unlink()
                print(f"Deleted SQLite database at {sqlite_path}")
            except Exception as e:
                print(f"Error deleting SQLite file: {e}")
        else:
            print("SQLite database file does not exist yet. It will be created by migrations.")
    else:
        # For non-SQLite databases (like Postgres), we drop all tables/views to wipe the entire database schema
        if "postgresql" in engine or "postgres" in engine:
            print(f"PostgreSQL database detected ({engine}). Dropping all tables and views...")
            try:
                from django.db import connection
                with connection.cursor() as cursor:
                    # Drop views first
                    cursor.execute("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_type = 'VIEW';
                    """)
                    views = [row[0] for row in cursor.fetchall()]
                    if views:
                        views_str = ", ".join([f'"{v}"' for v in views])
                        cursor.execute(f"DROP VIEW IF EXISTS {views_str} CASCADE;")
                        print(f"Dropped views: {views_str}")

                    # Drop tables
                    cursor.execute("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_type = 'BASE TABLE';
                    """)
                    tables = [row[0] for row in cursor.fetchall()]
                    if tables:
                        tables_str = ", ".join([f'"{t}"' for t in tables])
                        cursor.execute(f"DROP TABLE IF EXISTS {tables_str} CASCADE;")
                        print(f"Dropped tables: {tables_str}")
                    else:
                        print("No tables found to drop.")
            except Exception as e:
                print(f"Error dropping PostgreSQL tables/views: {e}")
                sys.exit(1)
        else:
            # Fallback to flush for any other database engines
            print(f"Non-SQLite/Non-Postgres database detected ({engine}). Flushing data...")
            try:
                call_command("migrate", no_input=True)
                call_command("flush", no_input=True)
                print("Database flushed successfully.")
            except Exception as e:
                print(f"Error flushing database: {e}")
                sys.exit(1)

    # Create the flag file to prevent future wipes
    try:
        flag_file.touch()
        print(f"Created flag file at {flag_file}")
    except Exception as e:
        print(f"Error creating flag file: {e}")

if __name__ == "__main__":
    main()
