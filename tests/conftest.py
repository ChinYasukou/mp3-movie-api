"""Isolate the SQLite collection for every API test."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "movies.db"
    monkeypatch.setattr(main, "storage", main.MovieStorage(db_path))
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def sample_csv_bytes():
    return (Path(__file__).resolve().parents[1] / "fixtures" / "sample_movies.csv").read_bytes()


@pytest.fixture
def uploaded_movies(client, sample_csv_bytes):
    response = client.post("/upload", files={"file": ("sample_movies.csv", sample_csv_bytes)})
    assert response.status_code == 200
    return response.json()
