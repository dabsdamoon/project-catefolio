from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse

from app.repositories.local_repo import LocalRepository
from app.schemas.models import (
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
_repo = LocalRepository()
_service = TransactionService(_repo)
_template_service = TemplateService(Path(__file__).resolve().parents[3] / "test_template" / "계좌관리_template.xlsx")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/upload", response_model=UploadResponse)
async def upload_files(
    files: list[UploadFile] = File(...),
    categorize: bool = False,
) -> UploadResponse:
    """Upload and process transaction files.

    Args:
        files: List of CSV/XLS/XLSX files to process
        categorize: Whether to run AI categorization (default: False, as it's in testing)
    """
    payload = _service.process_upload(files, categorize=categorize)
    return UploadResponse(
        job_id=payload["job_id"],
        status=payload["status"],
        files_received=len(files),
        created_at=payload["created_at"],
    )


@router.get("/result/{job_id}", response_model=ResultResponse)
def get_result(job_id: str) -> ResultResponse:
    job = _service.get_job(job_id)
    return ResultResponse(
        job_id=job_id,
        status=job["status"],
        summary=job["summary"],
        transactions=job["transactions"],
    )


@router.get("/report/{job_id}", response_model=ReportResponse)
def get_report(job_id: str) -> ReportResponse:
    job = _service.get_job(job_id)
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
def get_visualize(job_id: str) -> VisualizationResponse:
    job = _service.get_job(job_id)
    return VisualizationResponse(
        job_id=job_id,
        status=job["status"],
        charts=job["charts"],
    )


@router.get("/entities", response_model=list[EntityResponse])
def list_entities() -> list[EntityResponse]:
    entities = _repo.list_entities()
    return [EntityResponse(**entity) for entity in entities]


@router.post("/entities", response_model=EntityResponse)
def create_entity(payload: EntityCreate) -> EntityResponse:
    entity = {
        "id": str(uuid4()),
        "name": payload.name.strip(),
        "aliases": payload.aliases,
        "description": payload.description,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    saved = _repo.save_entity(entity)
    return EntityResponse(**saved)


@router.post("/infer/graph", response_model=GraphInferenceResponse)
def infer_graph(payload: TransactionInput, debug: bool = False) -> GraphInferenceResponse:
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
) -> StreamingResponse:
    """Convert transaction files to Excel template format.

    Args:
        files: List of CSV/XLS/XLSX files to process
        categorize: Whether to run AI categorization (default: False)
    """
    payload = _service.process_upload(files, categorize=categorize)
    template_bytes = _template_service.build_template_bytes(payload["transactions"])
    filename = "account_template_output.xlsx"
    return StreamingResponse(
        BytesIO(template_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
