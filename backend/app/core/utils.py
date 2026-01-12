"""
Core utilities for Catefolio backend.
"""

from __future__ import annotations

import hashlib
from typing import Any


def transaction_signature(txn: dict[str, Any]) -> str:
    """Generate a unique signature for a transaction based on date, description, amount.

    This is used for deduplication across all transaction-related operations.

    Args:
        txn: Transaction dictionary with date, description, and amount fields

    Returns:
        MD5 hex digest of the transaction key
    """
    key = f"{txn.get('date', '')}|{txn.get('description', '')}|{txn.get('amount', 0)}"
    return hashlib.md5(key.encode()).hexdigest()
