"""
Cloud Storage Service

Handles file uploads and downloads using Google Cloud Storage.
Files are organized by user_id: uploads/{user_id}/{filename}
"""

import os
from datetime import timedelta
from typing import Optional

from google.cloud import storage


class CloudStorageService:
    """Service for managing files in Google Cloud Storage."""

    def __init__(self, bucket_name: Optional[str] = None) -> None:
        """
        Initialize Cloud Storage service.

        Args:
            bucket_name: GCS bucket name. Defaults to STORAGE_BUCKET env var
                        or "{project_id}-uploads"
        """
        self.client = storage.Client()

        if bucket_name:
            self.bucket_name = bucket_name
        else:
            self.bucket_name = os.environ.get(
                "STORAGE_BUCKET",
                f"{self.client.project}-uploads"
            )

        self._bucket: Optional[storage.Bucket] = None

    @property
    def bucket(self) -> storage.Bucket:
        """Get or create the storage bucket."""
        if self._bucket is None:
            try:
                self._bucket = self.client.get_bucket(self.bucket_name)
            except Exception:
                # Bucket doesn't exist, create it
                self._bucket = self.client.create_bucket(
                    self.bucket_name,
                    location="us-central1"
                )
        return self._bucket

    def _get_blob_path(self, user_id: str, filename: str) -> str:
        """Generate blob path for a user's file."""
        return f"uploads/{user_id}/{filename}"

    def upload_file(
        self,
        user_id: str,
        filename: str,
        content: bytes,
        content_type: Optional[str] = None,
    ) -> str:
        """
        Upload a file to Cloud Storage.

        Args:
            user_id: User's unique identifier
            filename: Original filename
            content: File content as bytes
            content_type: MIME type (optional)

        Returns:
            The blob path (uploads/{user_id}/{filename})
        """
        blob_path = self._get_blob_path(user_id, filename)
        blob = self.bucket.blob(blob_path)

        blob.upload_from_string(
            content,
            content_type=content_type or "application/octet-stream"
        )

        return blob_path

    def download_file(self, user_id: str, filename: str) -> Optional[bytes]:
        """
        Download a file from Cloud Storage.

        Args:
            user_id: User's unique identifier
            filename: Filename to download

        Returns:
            File content as bytes, or None if not found
        """
        blob_path = self._get_blob_path(user_id, filename)
        blob = self.bucket.blob(blob_path)

        if not blob.exists():
            return None

        return blob.download_as_bytes()

    def delete_file(self, user_id: str, filename: str) -> bool:
        """
        Delete a file from Cloud Storage.

        Args:
            user_id: User's unique identifier
            filename: Filename to delete

        Returns:
            True if deleted, False if not found
        """
        blob_path = self._get_blob_path(user_id, filename)
        blob = self.bucket.blob(blob_path)

        if not blob.exists():
            return False

        blob.delete()
        return True

    def get_signed_url(
        self,
        user_id: str,
        filename: str,
        expiration_minutes: int = 60,
    ) -> Optional[str]:
        """
        Generate a signed URL for temporary access to a file.

        Args:
            user_id: User's unique identifier
            filename: Filename
            expiration_minutes: URL validity duration in minutes

        Returns:
            Signed URL string, or None if file not found
        """
        blob_path = self._get_blob_path(user_id, filename)
        blob = self.bucket.blob(blob_path)

        if not blob.exists():
            return None

        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiration_minutes),
            method="GET",
        )

        return url

    def list_user_files(self, user_id: str) -> list[str]:
        """
        List all files for a user.

        Args:
            user_id: User's unique identifier

        Returns:
            List of filenames
        """
        prefix = f"uploads/{user_id}/"
        blobs = self.bucket.list_blobs(prefix=prefix)

        filenames = []
        for blob in blobs:
            # Extract filename from path
            filename = blob.name.replace(prefix, "")
            if filename:  # Skip if empty (the directory itself)
                filenames.append(filename)

        return filenames
