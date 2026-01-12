"""
Firestore Migration Runner

A simple migration system for Firestore that tracks executed migrations
in a _migrations collection.

Usage:
    python -m migrations.runner migrate      # Run pending migrations
    python -m migrations.runner status       # Show migration status
    python -m migrations.runner create NAME  # Create new migration file
"""

import argparse
import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import firebase_admin
from firebase_admin import firestore

# Initialize Firebase if not already done
if not firebase_admin._apps:
    firebase_admin.initialize_app()

db = firestore.client()
MIGRATIONS_COLLECTION = "_migrations"


def get_executed_migrations() -> set[str]:
    """Get set of already executed migration IDs."""
    docs = db.collection(MIGRATIONS_COLLECTION).stream()
    return {doc.id for doc in docs}


def mark_migration_executed(migration_id: str) -> None:
    """Mark a migration as executed."""
    db.collection(MIGRATIONS_COLLECTION).document(migration_id).set({
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
    })


def get_pending_migrations() -> list[tuple[str, Path]]:
    """Get list of pending migrations (not yet executed)."""
    migrations_dir = Path(__file__).parent
    executed = get_executed_migrations()

    pending = []
    for file in sorted(migrations_dir.glob("m_*.py")):
        migration_id = file.stem  # e.g., "m_20260112_001_add_user_id"
        if migration_id not in executed:
            pending.append((migration_id, file))

    return pending


def run_migration(migration_id: str, file_path: Path) -> bool:
    """Run a single migration."""
    print(f"Running migration: {migration_id}")

    try:
        # Import the migration module
        spec = importlib.util.spec_from_file_location(migration_id, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Run the upgrade function
        if hasattr(module, "upgrade"):
            module.upgrade(db)
            mark_migration_executed(migration_id)
            print(f"  ✓ Completed: {migration_id}")
            return True
        else:
            print(f"  ✗ Error: {migration_id} has no 'upgrade' function")
            return False

    except Exception as e:
        print(f"  ✗ Error running {migration_id}: {e}")
        return False


def cmd_migrate() -> None:
    """Run all pending migrations."""
    pending = get_pending_migrations()

    if not pending:
        print("No pending migrations.")
        return

    print(f"Found {len(pending)} pending migration(s):\n")

    success_count = 0
    for migration_id, file_path in pending:
        if run_migration(migration_id, file_path):
            success_count += 1
        else:
            print("\nStopping due to error.")
            break

    print(f"\nCompleted {success_count}/{len(pending)} migrations.")


def cmd_status() -> None:
    """Show migration status."""
    migrations_dir = Path(__file__).parent
    executed = get_executed_migrations()

    all_migrations = sorted(migrations_dir.glob("m_*.py"))

    if not all_migrations:
        print("No migrations found.")
        return

    print("Migration Status:\n")
    for file in all_migrations:
        migration_id = file.stem
        status = "✓ executed" if migration_id in executed else "○ pending"
        print(f"  {status}  {migration_id}")


def cmd_create(name: str) -> None:
    """Create a new migration file."""
    migrations_dir = Path(__file__).parent

    # Generate migration ID with timestamp
    timestamp = datetime.now().strftime("%Y%m%d")

    # Find next sequence number for today
    existing = list(migrations_dir.glob(f"m_{timestamp}_*.py"))
    seq = len(existing) + 1

    # Sanitize name
    safe_name = name.lower().replace(" ", "_").replace("-", "_")
    migration_id = f"m_{timestamp}_{seq:03d}_{safe_name}"

    file_path = migrations_dir / f"{migration_id}.py"

    template = f'''"""
Migration: {name}
Created: {datetime.now().isoformat()}

Description:
    TODO: Describe what this migration does
"""

from google.cloud.firestore_v1 import Client


def upgrade(db: Client) -> None:
    """
    Run the migration.

    Args:
        db: Firestore client instance
    """
    # TODO: Implement migration logic
    # Example: Add a field to all documents in a collection
    #
    # docs = db.collection("jobs").stream()
    # for doc in docs:
    #     doc.reference.update({{"new_field": "default_value"}})

    pass


def downgrade(db: Client) -> None:
    """
    Reverse the migration (optional).

    Args:
        db: Firestore client instance
    """
    # TODO: Implement rollback logic if needed
    pass
'''

    file_path.write_text(template)
    print(f"Created migration: {file_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Firestore Migration Runner")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # migrate command
    subparsers.add_parser("migrate", help="Run pending migrations")

    # status command
    subparsers.add_parser("status", help="Show migration status")

    # create command
    create_parser = subparsers.add_parser("create", help="Create new migration")
    create_parser.add_argument("name", help="Migration name (e.g., 'add_user_id')")

    args = parser.parse_args()

    if args.command == "migrate":
        cmd_migrate()
    elif args.command == "status":
        cmd_status()
    elif args.command == "create":
        cmd_create(args.name)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
