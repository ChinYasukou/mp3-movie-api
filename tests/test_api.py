"""Exercise the API through HTTP requests without starting a server."""

import pytest

import main


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.0.0"}


def test_upload_and_retrieve_preserve_order_missing_values_and_storage(client):
    contents = b"student_id,score\n1,80\n2,90\n2,90\n3,\n4,unknown\n5,85\n"
    response = client.post("/upload", files={"file": ("sample.CSV", contents, "text/csv")})
    assert response.status_code == 200
    assert response.json() == {
        "id": 1, "filename": "sample.CSV", "rows": 6, "columns": 2,
        "column_names": ["student_id", "score"],
    }
    limited = client.get("/datasets/1", params={"limit": 2})
    assert limited.status_code == 200
    assert limited.json() == {
        "id": 1,
        "data": [{"student_id": 1, "score": "80"}, {"student_id": 2, "score": "90"}],
        "total_rows": 6,
    }
    full = client.get("/datasets/1").json()
    assert len(full["data"]) == full["total_rows"] == 6
    assert full["data"][2] == full["data"][1]
    assert full["data"][3]["score"] is None


@pytest.mark.parametrize("filename,contents", [
    ("data.txt", b"a\n1\n"),
    ("data", b"a\n1\n"),
    ("empty.csv", b""),
    ("bad.csv", b'a,b\n"unterminated'),
    ("encoding.csv", b"a\n\xff\n"),
])
def test_invalid_uploads_return_400_without_saving(client, filename, contents):
    response = client.post("/upload", files={"file": (filename, contents)})
    assert response.status_code == 400
    assert response.json()["detail"]
    assert main.storage.get(1) is None


def test_retrieve_missing_dataset(client):
    assert client.get("/datasets/999").status_code == 404


@pytest.mark.parametrize("limit", [0, -1, "invalid"])
def test_invalid_limit_returns_422(client, limit):
    assert client.get("/datasets/1", params={"limit": limit}).status_code == 422


def test_default_limit_is_100(client):
    contents = "number\n" + "\n".join(str(i) for i in range(105))
    response = client.post("/upload", files={"file": ("numbers.csv", contents)})
    assert response.status_code == 200
    result = client.get("/datasets/1").json()
    assert len(result["data"]) == 100
    assert result["total_rows"] == 105


def test_upload_csv(client, sample_csv_bytes):
    response = client.post(
        "/upload", files={"file": ("sample_data.csv", sample_csv_bytes, "text/csv")}
    )
    assert response.status_code == 200
    result = response.json()
    assert result["rows"] == 6
    assert result["columns"] == 2
    assert isinstance(result["id"], int) and result["id"] > 0


def test_process_and_retrieve(client, uploaded_dataset_id, processing_body):
    response = client.post(
        f"/datasets/{uploaded_dataset_id}/process", json=processing_body
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": uploaded_dataset_id,
        "validation_rows_removed": 1,
        "cleaning_report": {
            "rows_before": 5, "rows_after": 3, "rows_removed": 2,
            "columns_before": 2, "columns_after": 2, "columns_removed": 0,
        },
    }
    retrieved = client.get(f"/datasets/{uploaded_dataset_id}")
    assert retrieved.status_code == 200
    assert retrieved.json()["total_rows"] == 3
    assert retrieved.json()["data"] == [
        {"student_id": 1, "score": 80},
        {"student_id": 2, "score": 90},
        {"student_id": 5, "score": 85},
    ]
    assert main.storage.get_metadata(uploaded_dataset_id)["rows"] == 3


def test_process_missing_dataset(client):
    assert client.post("/datasets/999/process", json={}).status_code == 404


@pytest.mark.parametrize("body", [
    {"validation": {"required_columns": ["absent"]}},
    {"validation": {"numeric_columns": ["absent"]}},
    {"processing": {"outliers": {"enabled": True, "method": "invalid"}}},
    {"processing": {"missing": {"axis": "invalid"}}},
])
def test_rejected_processing_preserves_storage(client, uploaded_dataset_id, body):
    before = main.storage.get(uploaded_dataset_id)
    response = client.post(f"/datasets/{uploaded_dataset_id}/process", json=body)
    assert response.status_code == 400
    assert response.json()["detail"]
    assert main.storage.get(uploaded_dataset_id).equals(before)


def test_malformed_processing_body(client, uploaded_dataset_id):
    response = client.post(
        f"/datasets/{uploaded_dataset_id}/process", json={"validation": []}
    )
    assert response.status_code == 422
    assert len(main.storage.get(uploaded_dataset_id)) == 6


def test_request_ids_and_log_levels(client, caplog):
    import logging
    import re

    with caplog.at_level(logging.INFO, logger="src.middleware"):
        responses = [
            client.get("/health"),
            client.post("/upload", files={"file": ("wrong.txt", b"a")}),
            client.get("/datasets/999"),
            client.get("/datasets/1?limit=0"),
        ]
    assert [r.status_code for r in responses] == [200, 400, 404, 422]
    ids = [r.headers["X-Request-ID"] for r in responses]
    assert all(re.fullmatch(r"[0-9a-f]{8}", value) for value in ids)
    assert len(set(ids)) == len(ids)
    logs = [record for record in caplog.records if record.name == "src.middleware"]
    assert [record.levelno for record in logs] == [
        logging.INFO, logging.WARNING, logging.WARNING, logging.WARNING,
    ]
    for record, response, request_id in zip(logs, responses, ids):
        message = record.getMessage()
        assert f"request_id={request_id}" in message
        assert response.request.method in message
        assert response.request.url.path in message
        assert f"status={response.status_code}" in message
        assert re.search(r"duration=\d+\.\dms", message)
