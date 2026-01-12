"""
Migration: transactions_to_subcollection
Created: 2026-01-12

Description:
    Migrates jobs with embedded transactions array to use sub-collections.

    Before:
        jobs/{job_id}
        └── transactions: [{...}, {...}, ...]  (embedded array)

    After:
        jobs/{job_id}
        ├── transaction_count: N
        └── transactions (sub-collection)
            ├── 00000000: {...}
            ├── 00000001: {...}
            └── ...
"""

from google.cloud.firestore_v1 import Client

BATCH_SIZE = 500


def upgrade(db: Client) -> None:
    """
    Migrate embedded transactions to sub-collections.

    Args:
        db: Firestore client instance
    """
    jobs_ref = db.collection("jobs")
    jobs = jobs_ref.stream()

    migrated_count = 0
    skipped_count = 0

    for job_doc in jobs:
        job_data = job_doc.to_dict()
        job_id = job_doc.id

        # Check if this job has embedded transactions
        transactions = job_data.get("transactions")

        if not transactions or not isinstance(transactions, list):
            # Already migrated or no transactions
            skipped_count += 1
            continue

        print(f"  Migrating job {job_id}: {len(transactions)} transactions")

        # Get reference to the job document
        job_ref = jobs_ref.document(job_id)

        # Save transactions to sub-collection in batches
        transactions_ref = job_ref.collection("transactions")

        for i in range(0, len(transactions), BATCH_SIZE):
            batch = db.batch()
            batch_transactions = transactions[i:i + BATCH_SIZE]

            for idx, txn in enumerate(batch_transactions):
                txn_id = f"{i + idx:08d}"
                txn_ref = transactions_ref.document(txn_id)
                txn["_index"] = i + idx
                batch.set(txn_ref, txn)

            batch.commit()

        # Update job document: remove embedded transactions, add count
        job_ref.update({
            "transactions": firestore.DELETE_FIELD,
            "transaction_count": len(transactions),
        })

        migrated_count += 1

    print(f"  Migrated {migrated_count} jobs, skipped {skipped_count}")


def downgrade(db: Client) -> None:
    """
    Reverse: move transactions from sub-collections back to embedded array.

    Args:
        db: Firestore client instance
    """
    jobs_ref = db.collection("jobs")
    jobs = jobs_ref.stream()

    reverted_count = 0

    for job_doc in jobs:
        job_data = job_doc.to_dict()
        job_id = job_doc.id

        # Skip if already has embedded transactions
        if "transactions" in job_data and isinstance(job_data["transactions"], list):
            continue

        job_ref = jobs_ref.document(job_id)
        transactions_ref = job_ref.collection("transactions")

        # Load transactions from sub-collection
        transactions = []
        for txn_doc in transactions_ref.order_by("_index").stream():
            txn = txn_doc.to_dict()
            txn.pop("_index", None)
            transactions.append(txn)

        if not transactions:
            continue

        print(f"  Reverting job {job_id}: {len(transactions)} transactions")

        # Update job document with embedded transactions
        job_ref.update({
            "transactions": transactions,
        })

        # Delete sub-collection
        for txn_doc in transactions_ref.stream():
            txn_doc.reference.delete()

        # Remove transaction_count field
        job_ref.update({
            "transaction_count": firestore.DELETE_FIELD,
        })

        reverted_count += 1

    print(f"  Reverted {reverted_count} jobs")


# Import firestore for DELETE_FIELD
from google.cloud import firestore
