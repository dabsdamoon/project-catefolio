import json
from pathlib import Path
from typing import Any


class LocalRepository:
    def __init__(self, base_dir: Path | None = None) -> None:
        root = base_dir or Path(__file__).resolve().parents[2]
        self.data_dir = root / "data"
        self.upload_dir = self.data_dir / "uploads"
        self.job_dir = self.data_dir / "jobs"
        self.entity_dir = self.data_dir / "entities"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self.entity_dir.mkdir(parents=True, exist_ok=True)

    def save_job(self, job_id: str, payload: dict[str, Any]) -> None:
        path = self.job_dir / f"{job_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_job(self, job_id: str) -> dict[str, Any] | None:
        path = self.job_dir / f"{job_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save_upload(self, filename: str, content: bytes) -> None:
        if not filename:
            return
        (self.upload_dir / filename).write_bytes(content)

    def save_entity(self, entity: dict[str, str]) -> dict[str, str]:
        entity_id = entity.get("id")
        if not entity_id:
            raise ValueError("Entity requires an id.")
        path = self.entity_dir / f"{entity_id}.json"
        path.write_text(json.dumps(entity, ensure_ascii=False, indent=2), encoding="utf-8")
        return entity

    def list_entities(self) -> list[dict[str, str]]:
        entities: list[dict[str, str]] = []
        for path in sorted(self.entity_dir.glob("*.json")):
            entities.append(json.loads(path.read_text(encoding="utf-8")))
        return entities

    def get_entity(self, entity_id: str) -> dict[str, str] | None:
        path = self.entity_dir / f"{entity_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
