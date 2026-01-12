"""
Migration: add_user_id_field
Created: 2026-01-12T16:01:06.026963

Description:
    Adds user_id field to all existing documents in jobs and entities collections.
    Documents without user_id will be assigned a default "system" user_id for
    backward compatibility.

    This migration prepares the database for multi-tenant support.
"""

from google.cloud.firestore_v1 import Client

# Default user_id for existing documents without owner
DEFAULT_USER_ID = "system"


def upgrade(db: Client) -> None:
    """
    Add user_id field to existing documents.

    Args:
        db: Firestore client instance
    """
    collections_to_update = ["jobs", "entities"]

    for collection_name in collections_to_update:
        print(f"  Processing collection: {collection_name}")
        updated_count = 0

        docs = db.collection(collection_name).stream()
        for doc in docs:
            data = doc.to_dict()
            if "user_id" not in data:
                doc.reference.update({"user_id": DEFAULT_USER_ID})
                updated_count += 1

        print(f"    Updated {updated_count} documents")


def downgrade(db: Client) -> None:
    """
    Remove user_id field from documents (rollback).

    Args:
        db: Firestore client instance
    """
    from google.cloud.firestore_v1 import DELETE_FIELD

    collections_to_update = ["jobs", "entities"]

    for collection_name in collections_to_update:
        print(f"  Processing collection: {collection_name}")
        updated_count = 0

        docs = db.collection(collection_name).stream()
        for doc in docs:
            data = doc.to_dict()
            if data.get("user_id") == DEFAULT_USER_ID:
                doc.reference.update({"user_id": DELETE_FIELD})
                updated_count += 1

        print(f"    Removed user_id from {updated_count} documents")
