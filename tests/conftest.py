"""Fresh storage and reusable inputs for each API test."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app, storage


@pytest.fixture
def client():
    storage.clear()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        storage.clear()


@pytest.fixture
def sample_csv_bytes():
    return (Path(__file__).resolve().parents[1] / "fixtures" / "sample_data.csv").read_bytes()


@pytest.fixture
def uploaded_dataset_id(client, sample_csv_bytes):
    response = client.post(
        "/upload", files={"file": ("sample_data.csv", sample_csv_bytes, "text/csv")}
    )
    assert response.status_code == 200
    return response.json()["id"]


@pytest.fixture
def processing_body():
    return {
        "validation": {
            "required_columns": ["student_id", "score"],
            "numeric_columns": ["score"],
        },
        "processing": {
            "remove_duplicates": True,
            "missing": {"enabled": True, "axis": "rows"},
            "outliers": {
                "enabled": False, "columns": [], "method": "iqr", "threshold": 1.5,
            },
        },
    }
