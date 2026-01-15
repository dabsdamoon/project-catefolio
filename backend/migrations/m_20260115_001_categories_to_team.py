"""
Migration: categories_to_team
Created: 2026-01-15

Description:
    Moves categories from owner's user_id to team_id.
    This enables all team members to edit the same category document.

    Before: categories/{owner_user_id}
    After:  categories/{team_id}

    For each team:
    1. Look up owner_id from teams collection
    2. If categories exist under categories/{owner_id}, copy to categories/{team_id}
    3. Delete the old categories/{owner_id} document
"""

from google.cloud.firestore_v1 import Client


def upgrade(db: Client) -> None:
    """
    Move categories from owner's user_id to team_id.

    Args:
        db: Firestore client instance
    """
    print("  Migrating categories from owner_id to team_id...")
    migrated_count = 0
    skipped_count = 0

    # Get all teams
    teams = db.collection("teams").stream()

    for team_doc in teams:
        team_data = team_doc.to_dict()
        team_id = team_doc.id
        owner_id = team_data.get("owner_id")
        team_name = team_data.get("name", "Unknown")

        if not owner_id:
            print(f"    Skipping team {team_name}: no owner_id")
            skipped_count += 1
            continue

        # Check if categories exist under owner's user_id
        owner_categories_ref = db.collection("categories").document(owner_id)
        owner_categories_doc = owner_categories_ref.get()

        if not owner_categories_doc.exists:
            print(f"    Skipping team {team_name}: no categories under owner {owner_id}")
            skipped_count += 1
            continue

        # Check if team already has categories (don't overwrite)
        team_categories_ref = db.collection("categories").document(team_id)
        team_categories_doc = team_categories_ref.get()

        if team_categories_doc.exists:
            print(f"    Skipping team {team_name}: already has categories under team_id")
            skipped_count += 1
            continue

        # Copy categories from owner to team
        categories_data = owner_categories_doc.to_dict()
        team_categories_ref.set(categories_data)

        # Delete old categories under owner_id
        owner_categories_ref.delete()

        print(f"    Migrated team {team_name}: {owner_id} -> {team_id}")
        migrated_count += 1

    print(f"  Migration complete: {migrated_count} migrated, {skipped_count} skipped")


def downgrade(db: Client) -> None:
    """
    Move categories back from team_id to owner's user_id.

    Args:
        db: Firestore client instance
    """
    print("  Rolling back categories from team_id to owner_id...")
    rolled_back_count = 0

    # Get all teams
    teams = db.collection("teams").stream()

    for team_doc in teams:
        team_data = team_doc.to_dict()
        team_id = team_doc.id
        owner_id = team_data.get("owner_id")
        team_name = team_data.get("name", "Unknown")

        if not owner_id:
            continue

        # Check if categories exist under team_id
        team_categories_ref = db.collection("categories").document(team_id)
        team_categories_doc = team_categories_ref.get()

        if not team_categories_doc.exists:
            continue

        # Check if owner already has categories (don't overwrite)
        owner_categories_ref = db.collection("categories").document(owner_id)
        owner_categories_doc = owner_categories_ref.get()

        if owner_categories_doc.exists:
            print(f"    Skipping team {team_name}: owner already has categories")
            continue

        # Copy categories from team to owner
        categories_data = team_categories_doc.to_dict()
        owner_categories_ref.set(categories_data)

        # Delete categories under team_id
        team_categories_ref.delete()

        print(f"    Rolled back team {team_name}: {team_id} -> {owner_id}")
        rolled_back_count += 1

    print(f"  Rollback complete: {rolled_back_count} rolled back")
