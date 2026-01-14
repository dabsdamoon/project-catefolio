"""
Firestore Repository

Repository implementation using Firestore for data persistence.
Supports multi-tenancy with user_id filtering.

Data Structure:
    jobs/{job_id}                     - Job metadata (status, summary, charts, etc.)
    jobs/{job_id}/transactions/{txn_id} - Individual transactions (sub-collection)
    entities/{entity_id}              - User-defined entities
    categories/{user_id|default}      - Expense categories
"""

from typing import Any, Optional
from uuid import uuid4

import firebase_admin
from firebase_admin import firestore
from google.cloud.firestore_v1 import FieldFilter

from app.core.utils import transaction_signature
from app.storage.cloud_storage import CloudStorageService


class FirestoreRepository:
    """Repository using Firestore for data persistence with multi-tenant support."""

    # Firestore batch write limit
    BATCH_SIZE = 500

    def __init__(self) -> None:
        # Initialize Firebase Admin SDK with Application Default Credentials
        if not firebase_admin._apps:
            firebase_admin.initialize_app()

        self.db = firestore.client()
        self.storage = CloudStorageService()

        # Collection references
        self.jobs_collection = "jobs"
        self.entities_collection = "entities"
        self.categories_collection = "categories"

    # =========================================================================
    # Job Methods (with transactions as sub-collection)
    # =========================================================================

    def save_job(
        self,
        job_id: str,
        payload: dict[str, Any],
        user_id: Optional[str] = None,
    ) -> None:
        """
        Save a job document to Firestore with transactions as sub-collection.

        Args:
            job_id: Unique job identifier
            payload: Job data (including transactions list)
            user_id: Owner's user ID (optional for backward compatibility)
        """
        # Extract transactions from payload
        transactions = payload.pop("transactions", [])

        # Add user_id to job metadata
        if user_id:
            payload["user_id"] = user_id

        # Store transaction count in metadata for reference
        payload["transaction_count"] = len(transactions)

        # Save job metadata
        job_ref = self.db.collection(self.jobs_collection).document(job_id)
        job_ref.set(payload)

        # Save transactions to sub-collection in batches
        if transactions:
            self._save_transactions_batch(job_ref, transactions)

    def _save_transactions_batch(
        self,
        job_ref,
        transactions: list[dict[str, Any]],
    ) -> None:
        """Save transactions to sub-collection using batch writes."""
        transactions_ref = job_ref.collection("transactions")

        # Process in batches to stay within Firestore limits
        for i in range(0, len(transactions), self.BATCH_SIZE):
            batch = self.db.batch()
            batch_transactions = transactions[i:i + self.BATCH_SIZE]

            for idx, txn in enumerate(batch_transactions):
                # Use sequential IDs for ordering
                txn_id = f"{i + idx:08d}"
                txn_ref = transactions_ref.document(txn_id)
                # Add index for ordering
                txn["_index"] = i + idx
                batch.set(txn_ref, txn)

            batch.commit()

    def load_job(
        self,
        job_id: str,
        user_id: Optional[str] = None,
    ) -> dict[str, Any] | None:
        """
        Load a job document from Firestore with transactions from sub-collection.

        Args:
            job_id: Unique job identifier
            user_id: If provided, verify ownership

        Returns:
            Job data with transactions, or None if not found/unauthorized
        """
        job_ref = self.db.collection(self.jobs_collection).document(job_id)
        doc = job_ref.get()

        if not doc.exists:
            return None

        data = doc.to_dict()

        # If user_id provided, verify ownership
        if user_id and data.get("user_id") and data["user_id"] != user_id:
            return None

        # Load transactions from sub-collection
        transactions = self._load_transactions(job_ref)
        data["transactions"] = transactions

        return data

    def _load_transactions(self, job_ref) -> list[dict[str, Any]]:
        """Load all transactions from sub-collection, ordered by index."""
        transactions_ref = job_ref.collection("transactions")
        # Order by document ID (which is sequential)
        docs = transactions_ref.order_by("_index").stream()

        transactions = []
        for doc in docs:
            txn = doc.to_dict()
            # Remove internal index field
            txn.pop("_index", None)
            transactions.append(txn)

        return transactions

    def list_jobs(self, user_id: str) -> list[dict[str, Any]]:
        """
        List all jobs for a user (metadata only, no transactions).

        Args:
            user_id: User's unique identifier

        Returns:
            List of job documents (without transactions for performance)
        """
        query = self.db.collection(self.jobs_collection).where(
            filter=FieldFilter("user_id", "==", user_id)
        )
        return [doc.to_dict() | {"id": doc.id} for doc in query.stream()]

    def list_jobs_for_users(self, user_ids: list[str]) -> list[dict[str, Any]]:
        """
        List all jobs for multiple users (team data access).

        Firestore 'in' query supports up to 30 values, so we batch for larger teams.

        Args:
            user_ids: List of user IDs

        Returns:
            List of job documents (without transactions for performance)
        """
        if not user_ids:
            return []

        all_jobs = []
        # Firestore 'in' query limited to 30 values
        for i in range(0, len(user_ids), 30):
            batch_ids = user_ids[i:i + 30]
            query = self.db.collection(self.jobs_collection).where(
                filter=FieldFilter("user_id", "in", batch_ids)
            )
            all_jobs.extend([doc.to_dict() | {"id": doc.id} for doc in query.stream()])

        return all_jobs

    def get_all_transaction_signatures(self, user_id: str) -> set[str]:
        """
        Get all transaction signatures for a user across all jobs.

        Used for deduplication during upload.

        Args:
            user_id: User's unique identifier

        Returns:
            Set of transaction signatures (md5 hashes of date|description|amount)
        """
        signatures: set[str] = set()
        jobs = self.list_jobs(user_id)

        for job_meta in jobs:
            job_id = job_meta.get("id")
            if not job_id:
                continue

            job_ref = self.db.collection(self.jobs_collection).document(job_id)
            transactions = self._load_transactions(job_ref)

            for txn in transactions:
                sig = transaction_signature(txn)
                signatures.add(sig)

        return signatures

    def find_job_by_signature(
        self,
        content_signature: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        """
        Find an existing job by content signature for a user.

        Args:
            content_signature: Hash of transaction content
            user_id: User's unique identifier

        Returns:
            Job data with id, or None if not found
        """
        query = (
            self.db.collection(self.jobs_collection)
            .where(filter=FieldFilter("user_id", "==", user_id))
            .where(filter=FieldFilter("content_signature", "==", content_signature))
            .limit(1)
        )
        docs = list(query.stream())
        if not docs:
            return None
        doc = docs[0]
        data = doc.to_dict()
        data["id"] = doc.id
        return data

    def delete_job(self, job_id: str, user_id: Optional[str] = None) -> bool:
        """
        Delete a job document and its transactions sub-collection.

        Args:
            job_id: Unique job identifier
            user_id: If provided, verify ownership before deletion

        Returns:
            True if deleted, False otherwise
        """
        job_ref = self.db.collection(self.jobs_collection).document(job_id)
        doc = job_ref.get()

        if not doc.exists:
            return False

        if user_id:
            data = doc.to_dict()
            if data.get("user_id") and data["user_id"] != user_id:
                return False

        # Delete transactions sub-collection first
        self._delete_collection(job_ref.collection("transactions"))

        # Delete job document
        job_ref.delete()
        return True

    def _delete_collection(self, collection_ref, batch_size: int = 500) -> None:
        """Delete all documents in a collection."""
        docs = collection_ref.limit(batch_size).stream()
        deleted = 0

        for doc in docs:
            doc.reference.delete()
            deleted += 1

        # Recurse if there are more documents
        if deleted >= batch_size:
            self._delete_collection(collection_ref, batch_size)

    # =========================================================================
    # Entity Methods (with user_id support)
    # =========================================================================

    def save_entity(
        self,
        entity: dict[str, Any],
        user_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Save an entity document to Firestore.

        Args:
            entity: Entity data (must include 'id')
            user_id: Owner's user ID (optional for backward compatibility)

        Returns:
            Saved entity data
        """
        entity_id = entity.get("id")
        if not entity_id:
            raise ValueError("Entity requires an id.")

        if user_id:
            entity["user_id"] = user_id

        self.db.collection(self.entities_collection).document(entity_id).set(entity)
        return entity

    def list_entities(self, user_id: Optional[str] = None) -> list[dict[str, Any]]:
        """
        List entity documents from Firestore.

        Args:
            user_id: If provided, filter by user. Otherwise return all.

        Returns:
            List of entity documents
        """
        if user_id:
            query = self.db.collection(self.entities_collection).where(
                filter=FieldFilter("user_id", "==", user_id)
            )
            return [doc.to_dict() for doc in query.stream()]
        else:
            # Backward compatibility: return all entities
            return [doc.to_dict() for doc in self.db.collection(self.entities_collection).stream()]

    def list_entities_for_users(self, user_ids: list[str]) -> list[dict[str, Any]]:
        """
        List all entities for multiple users (team data access).

        Args:
            user_ids: List of user IDs

        Returns:
            List of entity documents
        """
        if not user_ids:
            return []

        all_entities = []
        # Firestore 'in' query limited to 30 values
        for i in range(0, len(user_ids), 30):
            batch_ids = user_ids[i:i + 30]
            query = self.db.collection(self.entities_collection).where(
                filter=FieldFilter("user_id", "in", batch_ids)
            )
            all_entities.extend([doc.to_dict() for doc in query.stream()])

        return all_entities

    def get_entity(
        self,
        entity_id: str,
        user_id: Optional[str] = None,
    ) -> dict[str, Any] | None:
        """
        Get a single entity document from Firestore.

        Args:
            entity_id: Entity's unique identifier
            user_id: If provided, verify ownership

        Returns:
            Entity data or None if not found/unauthorized
        """
        doc = self.db.collection(self.entities_collection).document(entity_id).get()
        if not doc.exists:
            return None

        data = doc.to_dict()

        if user_id and data.get("user_id") and data["user_id"] != user_id:
            return None

        return data

    def delete_entity(self, entity_id: str, user_id: Optional[str] = None) -> bool:
        """
        Delete an entity document.

        Args:
            entity_id: Entity's unique identifier
            user_id: If provided, verify ownership before deletion

        Returns:
            True if deleted, False otherwise
        """
        doc_ref = self.db.collection(self.entities_collection).document(entity_id)
        doc = doc_ref.get()

        if not doc.exists:
            return False

        if user_id:
            data = doc.to_dict()
            if data.get("user_id") and data["user_id"] != user_id:
                return False

        doc_ref.delete()
        return True

    # =========================================================================
    # Category Methods (with user_id support)
    # =========================================================================

    def get_categories(self, user_id: Optional[str] = None) -> dict[str, Any] | None:
        """
        Get categories document from Firestore.

        Args:
            user_id: If provided, get user-specific categories.
                    Otherwise get default categories.

        Returns:
            Categories data or None if not found
        """
        doc_id = user_id if user_id else "default"
        doc = self.db.collection(self.categories_collection).document(doc_id).get()

        if not doc.exists:
            # If user-specific not found, fall back to default
            if user_id:
                return self.get_categories(user_id=None)
            return None

        return doc.to_dict()

    def save_categories(
        self,
        categories: dict[str, Any],
        user_id: Optional[str] = None,
    ) -> None:
        """
        Save categories document to Firestore.

        Args:
            categories: Categories data
            user_id: If provided, save as user-specific categories.
                    Otherwise save as default.
        """
        doc_id = user_id if user_id else "default"
        self.db.collection(self.categories_collection).document(doc_id).set(categories)

    # =========================================================================
    # File Upload Methods (using Cloud Storage)
    # =========================================================================

    def save_upload(
        self,
        filename: str,
        content: bytes,
        user_id: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> Optional[str]:
        """
        Save uploaded file to Cloud Storage.

        Args:
            filename: Original filename
            content: File content as bytes
            user_id: Owner's user ID (required for Cloud Storage)
            content_type: MIME type (optional)

        Returns:
            Blob path if saved, None if skipped
        """
        if not filename:
            return None

        if not user_id:
            # For backward compatibility, skip cloud storage if no user
            return None

        return self.storage.upload_file(
            user_id=user_id,
            filename=filename,
            content=content,
            content_type=content_type,
        )

    def get_upload(
        self,
        filename: str,
        user_id: str,
    ) -> Optional[bytes]:
        """
        Get uploaded file from Cloud Storage.

        Args:
            filename: Filename to retrieve
            user_id: Owner's user ID

        Returns:
            File content as bytes, or None if not found
        """
        return self.storage.download_file(user_id=user_id, filename=filename)

    def list_uploads(self, user_id: str) -> list[str]:
        """
        List all uploaded files for a user.

        Args:
            user_id: User's unique identifier

        Returns:
            List of filenames
        """
        return self.storage.list_user_files(user_id=user_id)

    def get_upload_url(
        self,
        filename: str,
        user_id: str,
        expiration_minutes: int = 60,
    ) -> Optional[str]:
        """
        Get a signed URL for a file.

        Args:
            filename: Filename
            user_id: Owner's user ID
            expiration_minutes: URL validity duration

        Returns:
            Signed URL or None if not found
        """
        return self.storage.get_signed_url(
            user_id=user_id,
            filename=filename,
            expiration_minutes=expiration_minutes,
        )
