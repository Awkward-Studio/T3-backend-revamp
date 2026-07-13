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
        flag_file = Path(volume_path) / ".db_wiped"
    else:
        flag_file = settings.BASE_DIR / ".db_wiped"

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
        # For other databases (like Postgres), we migrate first, then flush
        print(f"Non-SQLite database detected ({engine}). Running migrations and flushing...")
        try:
            call_command("migrate", noinput=True)
            call_command("flush", noinput=True)
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
