from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse

from app.auth.firebase_auth import FirebaseUser, get_current_user, get_optional_user
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
_repo = FirestoreRepository()
_service = TransactionService(_repo)
_template_service = TemplateService(Path(__file__).resolve().parents[3] / "test_template" / "계좌관리_template.xlsx")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/upload", response_model=UploadResponse)
async def upload_files(
    files: list[UploadFile] = File(...),
    categorize: bool = False,
    user: FirebaseUser = Depends(get_current_user),
) -> UploadResponse:
    """Upload and process transaction files.

    Args:
        files: List of CSV/XLS/XLSX files to process
        categorize: Whether to run AI categorization (default: False, as it's in testing)
        user: Authenticated user (from Firebase Auth or demo mode)
    """
    payload = _service.process_upload(files, categorize=categorize, user_id=user.uid)
    return UploadResponse(
        job_id=payload["job_id"],
        status=payload["status"],
        files_received=len(files),
        created_at=payload["created_at"],
    )


@router.get("/result/{job_id}", response_model=ResultResponse)
def get_result(
    job_id: str,
    user: FirebaseUser = Depends(get_current_user),
) -> ResultResponse:
    """Get processed transaction results for a job."""
    job = _service.get_job(job_id, user_id=user.uid)
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
    job = _service.get_job(job_id, user_id=user.uid)
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
    job = _service.get_job(job_id, user_id=user.uid)
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
    entities = _repo.list_entities(user_id=user.uid)
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
    saved = _repo.save_entity(entity, user_id=user.uid)
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
    result, raw_text = _service.inference.infer_graph(transaction, root_context=payload.root_context)
    response = GraphInferenceResponse(**result)
    if debug:
        response.raw_text = raw_text
    return response


@router.post("/template/convert")
async def convert_template(
    files: list[UploadFile] = File(...),
    categorize: bool = False,
    user: FirebaseUser = Depends(get_current_user),
) -> StreamingResponse:
    """Convert transaction files to Excel template format.

    Args:
        files: List of CSV/XLS/XLSX files to process
        categorize: Whether to run AI categorization (default: False)
        user: Authenticated user
    """
    payload = _service.process_upload(files, categorize=categorize, user_id=user.uid)
    template_bytes = _template_service.build_template_bytes(payload["transactions"])
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
    data = _repo.get_categories(user_id=user_id)
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
    _repo.save_categories(data, user_id=user.uid)
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
