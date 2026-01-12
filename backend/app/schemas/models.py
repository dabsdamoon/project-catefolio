from typing import Any

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    job_id: str = Field(..., description="Unique job identifier for this upload batch.")
    status: str
    files_received: int
    created_at: str
    is_duplicate: bool = False
    was_categorized: bool = False


class ResultResponse(BaseModel):
    job_id: str
    status: str
    summary: dict[str, Any]
    transactions: list[dict[str, Any]]


class ReportResponse(BaseModel):
    job_id: str
    status: str
    narrative: str
    export_links: dict[str, str]


class VisualizationResponse(BaseModel):
    job_id: str
    status: str
    charts: dict[str, Any]


class EntityCreate(BaseModel):
    name: str
    aliases: list[str] = []
    description: str | None = None


class EntityResponse(BaseModel):
    id: str
    name: str
    aliases: list[str] = []
    description: str | None = None
    created_at: str


class TransactionInput(BaseModel):
    description: str
    amount: float
    note: str | None = None
    display: str | None = None
    memo: str | None = None
    root_context: str | None = None


class GraphInferenceResponse(BaseModel):
    entities: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    raw_text: str | None = None


class CategoryItem(BaseModel):
    id: str
    name: str
    keywords: list[str] = []
