from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.auth.firebase_auth import FirebaseUser, get_current_user, get_optional_user
from app.core.utils import transaction_signature
from app.repositories.firestore_repo import FirestoreRepository
from app.schemas.models import (
    CategoryItem,
    EntityCreate,
    EntityResponse,
    GraphInferenceResponse,
    ReportResponse,
    ResultResponse,
    TransactionInput,
    UploadResponse,
    VisualizationResponse,
)
from app.services.transaction_service import TransactionService
from app.services.template_service import TemplateService

router = APIRouter()

# Lazy initialization to avoid Firebase connection at import time (breaks tests)
_repo: FirestoreRepository | None = None
_service: TransactionService | None = None
_template_service: TemplateService | None = None


def get_repo() -> FirestoreRepository:
    global _repo
    if _repo is None:
        _repo = FirestoreRepository()
    return _repo


def get_service() -> TransactionService:
    global _service
    if _service is None:
        _service = TransactionService(get_repo())
    return _service


def get_template_service() -> TemplateService:
    global _template_service
    if _template_service is None:
        _template_service = TemplateService(
            Path(__file__).resolve().parents[3] / "test_template" / "계좌관리_template.xlsx"
        )
    return _template_service


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/upload", response_model=UploadResponse)
async def upload_files(
    files: list[UploadFile] = File(...),
    categorize: bool = False,
    force_reprocess: bool = False,
    user: FirebaseUser = Depends(get_current_user),
) -> UploadResponse:
    """Upload and process transaction files.

    Args:
        files: List of CSV/XLS/XLSX files to process
        categorize: Whether to run AI categorization (default: False, as it's in testing)
        force_reprocess: If True, delete existing duplicate and re-process
        user: Authenticated user (from Firebase Auth or demo mode)

    Returns:
        UploadResponse with job info. Returns existing job if duplicate found.
    """
    # Check for duplicates
    for f in files:
        f.file.seek(0)
    duplicate = get_service().check_duplicates(files, user_id=user.uid)

    if duplicate and not force_reprocess:
        # Return existing job info - no need to re-process
        return UploadResponse(
            job_id=duplicate["job_id"],
            status="existing",
            files_received=len(files),
            created_at=duplicate["created_at"],
            is_duplicate=True,
            was_categorized=duplicate["categorized"],
        )

    # Reset file positions for processing
    for f in files:
        f.file.seek(0)

    # If force_reprocess and duplicate exists, delete the old one
    overwrite_job_id = duplicate["job_id"] if duplicate and force_reprocess else None

    payload = get_service().process_upload(
        files,
        categorize=categorize,
        user_id=user.uid,
        overwrite_job_id=overwrite_job_id,
    )
    return UploadResponse(
        job_id=payload["job_id"],
        status=payload["status"],
        files_received=len(files),
        created_at=payload["created_at"],
        is_duplicate=False,
        was_categorized=payload.get("categorized", False),
        duplicates_skipped=payload.get("duplicates_skipped", 0),
    )


@router.get("/result/{job_id}", response_model=ResultResponse)
def get_result(
    job_id: str,
    user: FirebaseUser = Depends(get_current_user),
) -> ResultResponse:
    """Get processed transaction results for a job."""
    job = get_service().get_job(job_id, user_id=user.uid)
    return ResultResponse(
        job_id=job_id,
        status=job["status"],
        summary=job["summary"],
        transactions=job["transactions"],
    )


@router.get("/report/{job_id}", response_model=ReportResponse)
def get_report(
    job_id: str,
    user: FirebaseUser = Depends(get_current_user),
) -> ReportResponse:
    """Get report/narrative for a job."""
    job = get_service().get_job(job_id, user_id=user.uid)
    return ReportResponse(
        job_id=job_id,
        status=job["status"],
        narrative=job["narrative"],
        export_links={
            "excel": f"https://example.com/reports/{job_id}.xlsx",
            "pdf": f"https://example.com/reports/{job_id}.pdf",
        },
    )


@router.get("/visualize/{job_id}", response_model=VisualizationResponse)
def get_visualize(
    job_id: str,
    user: FirebaseUser = Depends(get_current_user),
) -> VisualizationResponse:
    """Get visualization data for a job."""
    job = get_service().get_job(job_id, user_id=user.uid)
    return VisualizationResponse(
        job_id=job_id,
        status=job["status"],
        charts=job["charts"],
    )


@router.get("/entities", response_model=list[EntityResponse])
def list_entities(
    user: FirebaseUser = Depends(get_current_user),
) -> list[EntityResponse]:
    """List all entities for the current user."""
    entities = get_repo().list_entities(user_id=user.uid)
    return [EntityResponse(**entity) for entity in entities]


@router.post("/entities", response_model=EntityResponse)
def create_entity(
    payload: EntityCreate,
    user: FirebaseUser = Depends(get_current_user),
) -> EntityResponse:
    """Create a new entity for the current user."""
    entity = {
        "id": str(uuid4()),
        "name": payload.name.strip(),
        "aliases": payload.aliases,
        "description": payload.description,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    saved = get_repo().save_entity(entity, user_id=user.uid)
    return EntityResponse(**saved)


@router.post("/infer/graph", response_model=GraphInferenceResponse)
def infer_graph(
    payload: TransactionInput,
    debug: bool = False,
    user: FirebaseUser = Depends(get_current_user),
) -> GraphInferenceResponse:
    """Infer entity graph from a transaction."""
    transaction = {
        "description": payload.description,
        "amount": payload.amount,
        "raw": {
            "note": payload.note or "",
            "display": payload.display or "",
            "memo": payload.memo or "",
        },
    }
    result, raw_text = get_service().inference.infer_graph(transaction, root_context=payload.root_context)
    response = GraphInferenceResponse(**result)
    if debug:
        response.raw_text = raw_text
    return response


@router.post("/template/convert")
async def convert_template(
    files: list[UploadFile] = File(...),
    categorize: bool = False,
    force_reprocess: bool = False,
    user: FirebaseUser = Depends(get_current_user),
) -> StreamingResponse:
    """Convert transaction files to Excel template format.

    Args:
        files: List of CSV/XLS/XLSX files to process
        categorize: Whether to run AI categorization (default: False)
        force_reprocess: If True, delete existing duplicate and re-process
        user: Authenticated user

    Returns:
        Excel file. If duplicate found, returns template from existing job data.
    """
    # Check for duplicates
    for f in files:
        f.file.seek(0)
    duplicate = get_service().check_duplicates(files, user_id=user.uid)

    if duplicate and not force_reprocess:
        # Use existing job's transactions for template
        existing_job = get_service().get_job(duplicate["job_id"], user_id=user.uid)
        template_bytes = get_template_service().build_template_bytes(existing_job["transactions"])
    else:
        # Reset file positions for processing
        for f in files:
            f.file.seek(0)

        # If force_reprocess and duplicate exists, delete the old one
        overwrite_job_id = duplicate["job_id"] if duplicate and force_reprocess else None

        payload = get_service().process_upload(
            files,
            categorize=categorize,
            user_id=user.uid,
            overwrite_job_id=overwrite_job_id,
        )
        template_bytes = get_template_service().build_template_bytes(payload["transactions"])

    filename = "account_template_output.xlsx"
    return StreamingResponse(
        BytesIO(template_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/categories", response_model=list[CategoryItem])
def get_categories(
    user: Optional[FirebaseUser] = Depends(get_optional_user),
) -> list[CategoryItem]:
    """Get all expense categories with their keywords.

    Categories are user-specific if authenticated, otherwise returns defaults.
    """
    user_id = user.uid if user else None
    data = get_repo().get_categories(user_id=user_id)
    if not data:
        return []
    return [
        CategoryItem(id=cat_id, name=cat["name"], keywords=cat.get("keywords", []))
        for cat_id, cat in data.items()
    ]


@router.put("/categories", response_model=list[CategoryItem])
def update_categories(
    categories: list[CategoryItem],
    user: FirebaseUser = Depends(get_current_user),
) -> list[CategoryItem]:
    """Update expense categories with their keywords for the current user."""
    data = {
        cat.id: {"name": cat.name, "keywords": cat.keywords}
        for cat in categories
    }
    get_repo().save_categories(data, user_id=user.uid)
    return categories


# =============================================================================
# User Info Endpoint
# =============================================================================

@router.get("/me")
def get_current_user_info(
    user: FirebaseUser = Depends(get_current_user),
) -> dict:
    """Get information about the current authenticated user."""
    return {
        "uid": user.uid,
        "email": user.email,
        "name": user.name,
        "is_demo": user.is_demo,
    }


@router.get("/jobs")
def list_jobs(
    user: FirebaseUser = Depends(get_current_user),
) -> list[dict]:
    """List all jobs for the current user (metadata only, no transactions)."""
    jobs = get_repo().list_jobs(user_id=user.uid)
    return jobs


@router.delete("/jobs/{job_id}")
def delete_job(
    job_id: str,
    user: FirebaseUser = Depends(get_current_user),
) -> dict:
    """Delete a specific job and its transactions."""
    deleted = get_repo().delete_job(job_id, user_id=user.uid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "deleted", "job_id": job_id}


@router.delete("/jobs")
def delete_all_jobs(
    user: FirebaseUser = Depends(get_current_user),
) -> dict:
    """Delete all jobs for the current user. Use with caution."""
    jobs = get_repo().list_jobs(user_id=user.uid)
    deleted_count = 0
    for job in jobs:
        job_id = job.get("id")
        if job_id and get_repo().delete_job(job_id, user_id=user.uid):
            deleted_count += 1
    return {"status": "deleted", "deleted_count": deleted_count}


@router.get("/transactions")
def get_all_transactions(
    user: FirebaseUser = Depends(get_current_user),
) -> dict:
    """Get all transactions across all jobs for the current user (deduplicated).

    Transactions are deduplicated based on date + description + amount signature.

    Returns:
        Dictionary with summary and deduplicated transactions list
    """
    jobs = get_repo().list_jobs(user_id=user.uid)

    seen_signatures: set[str] = set()
    unique_transactions: list[dict] = []
    duplicate_count = 0

    for job_meta in jobs:
        job_id = job_meta.get("id")
        if not job_id:
            continue

        job = get_repo().load_job(job_id, user_id=user.uid)
        if not job:
            continue

        transactions = job.get("transactions", [])
        for txn in transactions:
            sig = transaction_signature(txn)
            if sig not in seen_signatures:
                seen_signatures.add(sig)
                unique_transactions.append(txn)
            else:
                duplicate_count += 1

    # Compute summary from deduplicated transactions
    total_income = sum(t["amount"] for t in unique_transactions if t.get("amount", 0) > 0)
    total_expenses = sum(abs(t["amount"]) for t in unique_transactions if t.get("amount", 0) < 0)

    return {
        "summary": {
            "total_income": round(total_income, 2),
            "total_expenses": round(total_expenses, 2),
            "net_savings": round(total_income - total_expenses, 2),
        },
        "transactions": unique_transactions,
        "job_count": len(jobs),
        "duplicate_count": duplicate_count,
    }
