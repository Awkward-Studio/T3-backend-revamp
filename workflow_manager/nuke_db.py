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
    print("WARNING: This script will drop ALL tables and views in your database and rerun all migrations!")
    
    force = "--force" in sys.argv or os.getenv("FORCE_NUKE") == "True"
    if not force:
        try:
            confirm = input("Are you sure you want to continue? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("Aborted.")
                return
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            return

    db_config = settings.DATABASES.get("default", {})
    engine = db_config.get("ENGINE", "")

    if "sqlite" in engine:
        sqlite_path = Path(db_config.get("NAME"))
        if sqlite_path.exists():
            try:
                sqlite_path.unlink()
                print(f"Deleted SQLite database file at {sqlite_path}")
            except Exception as e:
                print(f"Error deleting SQLite file: {e}")
                sys.exit(1)
        else:
            print("SQLite database file does not exist yet.")
    elif "postgresql" in engine or "postgres" in engine:
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
        print(f"Unsupported database engine ({engine}). Cannot drop tables.")
        sys.exit(1)

    print("Re-running all migrations...")
    try:
        call_command("migrate", no_input=True)
        print("Migrations rerun successfully!")
    except Exception as e:
        print(f"Error running migrations: {e}")
        sys.exit(1)

    # Automatically re-seed roles and default users
    try:
        print("Seeding default roles...")
        call_command("seed_roles")
        print("Seeding default users...")
        call_command("seed_default_users")
        print("Database seeded successfully!")
    except Exception as e:
        print(f"Error seeding database: {e}")

if __name__ == "__main__":
    main()
