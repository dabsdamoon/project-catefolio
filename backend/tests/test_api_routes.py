"""Integration tests for API routes."""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_services():
    """Mock all service dependencies."""
    mock_repo = MagicMock()
    mock_service = MagicMock()
    mock_template = MagicMock()

    mock_repo.list_entities.return_value = []
    mock_repo.save_entity.side_effect = lambda e, user_id=None: e
    mock_repo.list_jobs.return_value = []
    mock_repo.delete_job.return_value = True
    mock_repo.load_job.return_value = None
    mock_repo.get_categories.return_value = {}

    mock_service.process_upload.return_value = {
        "job_id": "test-job-123",
        "status": "processed",
        "files": ["test.csv"],
        "created_at": "2024-01-15T00:00:00Z",
        "summary": {"total_income": 1000, "total_expenses": 500, "net_savings": 500, "entity_counts": {}},
        "transactions": [],
        "charts": {},
        "rules": [],
        "categories": [],
        "narrative": "Test narrative",
    }

    mock_service.check_duplicates.return_value = None

    mock_service.get_job.return_value = {
        "status": "processed",
        "summary": {"total_income": 1000, "total_expenses": 500, "net_savings": 500, "entity_counts": {}},
        "transactions": [],
        "charts": {},
        "narrative": "Test narrative",
    }

    mock_service.inference = MagicMock()
    mock_service.inference.infer_graph.return_value = (
        {"entities": [], "relationships": []},
        "raw",
    )

    mock_template.build_template_bytes.return_value = b"excel content"

    with patch("app.api.routes.get_repo", return_value=mock_repo), \
         patch("app.api.routes.get_service", return_value=mock_service), \
         patch("app.api.routes.get_template_service", return_value=mock_template):
        yield {
            "repo": mock_repo,
            "service": mock_service,
            "template": mock_template,
        }


@pytest.fixture
def mock_team_repo():
    """Mock TeamRepository for testing without GCP credentials."""
    mock_repo = MagicMock()
    mock_repo.get_user_membership.return_value = None
    mock_repo.get_team.return_value = None
    mock_repo.list_team_members.return_value = []
    mock_repo.list_team_invites.return_value = []
    return mock_repo


@pytest.fixture
def client(mock_services, mock_team_repo) -> TestClient:
    """Create test client with mocked services and demo auth."""
    from app.main import app
    from app.repositories.team_repo import get_team_repo

    # Override team repo dependency to avoid GCP credential requirement
    app.dependency_overrides[get_team_repo] = lambda: mock_team_repo

    client = TestClient(app)
    # Use demo mode for authentication
    client.headers["X-Demo-User-Id"] = "test-user"
    yield client

    # Clean up override
    app.dependency_overrides.pop(get_team_repo, None)


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestUploadEndpoint:
    """Tests for file upload endpoint."""

    def test_upload_single_file(self, client, mock_services):
        csv_content = b"date,description,amount\n2024-01-15,Test,-100"
        files = {"files": ("test.csv", BytesIO(csv_content), "text/csv")}

        response = client.post("/upload", files=files)
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "test-job-123"
        assert data["status"] == "processed"
        assert data["files_received"] == 1

    def test_upload_multiple_files(self, client, mock_services):
        csv_content = b"date,description,amount\n2024-01-15,Test,-100"
        files = [
            ("files", ("test1.csv", BytesIO(csv_content), "text/csv")),
            ("files", ("test2.csv", BytesIO(csv_content), "text/csv")),
        ]

        response = client.post("/upload", files=files)
        assert response.status_code == 200
        data = response.json()
        assert data["files_received"] == 2


class TestResultEndpoint:
    """Tests for result retrieval endpoint."""

    def test_get_result_success(self, client, mock_services):
        response = client.get("/result/test-job-123")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "test-job-123"
        assert data["status"] == "processed"
        assert "summary" in data
        assert "transactions" in data

    def test_get_result_not_found(self, client, mock_services):
        from fastapi import HTTPException

        mock_services["service"].get_job.side_effect = HTTPException(status_code=404, detail="Job not found")

        response = client.get("/result/nonexistent")
        assert response.status_code == 404


class TestReportEndpoint:
    """Tests for report endpoint."""

    def test_get_report(self, client, mock_services):
        response = client.get("/report/test-job-123")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "test-job-123"
        assert "narrative" in data
        assert "export_links" in data


class TestVisualizeEndpoint:
    """Tests for visualization endpoint."""

    def test_get_visualize(self, client, mock_services):
        response = client.get("/visualize/test-job-123")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "test-job-123"
        assert "charts" in data


class TestEntitiesEndpoint:
    """Tests for entities endpoints."""

    def test_list_entities_empty(self, client, mock_services):
        response = client.get("/entities")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_entities_with_data(self, client, mock_services):
        mock_services["repo"].list_entities.return_value = [
            {
                "id": "1",
                "name": "Amazon",
                "aliases": ["AMZN"],
                "description": "E-commerce",
                "created_at": "2024-01-01T00:00:00Z",
            }
        ]

        response = client.get("/entities")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Amazon"

    def test_create_entity(self, client, mock_services):
        payload = {
            "name": "New Entity",
            "aliases": ["NE", "Entity"],
            "description": "A new entity",
        }

        response = client.post("/entities", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Entity"
        assert "id" in data
        assert "created_at" in data


class TestInferGraphEndpoint:
    """Tests for graph inference endpoint."""

    def test_infer_graph_basic(self, client, mock_services):
        payload = {
            "description": "Amazon Purchase",
            "amount": -99.99,
        }

        response = client.post("/infer/graph", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "entities" in data
        assert "relationships" in data

    def test_infer_graph_with_context(self, client, mock_services):
        payload = {
            "description": "Amazon Purchase",
            "amount": -99.99,
            "root_context": "Personal expenses",
        }

        response = client.post("/infer/graph", json=payload)
        assert response.status_code == 200

    def test_infer_graph_with_debug(self, client, mock_services):
        payload = {
            "description": "Amazon Purchase",
            "amount": -99.99,
        }

        response = client.post("/infer/graph?debug=true", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "raw_text" in data


class TestTemplateConvertEndpoint:
    """Tests for template conversion endpoint."""

    def test_convert_template(self, client, mock_services):
        csv_content = b"date,description,amount\n2024-01-15,Test,-100"
        files = {"files": ("test.csv", BytesIO(csv_content), "text/csv")}

        response = client.post("/template/convert", files=files)
        assert response.status_code == 200
        assert (
            response.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert "content-disposition" in response.headers


class TestCORS:
    """Tests for CORS configuration."""

    def test_cors_headers_present(self, client):
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5175",
                "Access-Control-Request-Method": "GET",
            },
        )
        # CORS preflight should return 200
        assert response.status_code == 200


class TestErrorHandling:
    """Tests for error handling in routes."""

    def test_invalid_json_body(self, client):
        response = client.post(
            "/entities",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

    def test_missing_required_field(self, client):
        payload = {"aliases": []}  # Missing 'name'

        response = client.post("/entities", json=payload)
        assert response.status_code == 422
