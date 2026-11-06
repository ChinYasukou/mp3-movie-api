"""Verify movie upload, SQL reads, and processing through the API."""

import pytest


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.0.0"}
    assert response.headers["X-Request-ID"]


def test_empty_collection(client):
    assert client.get("/movies").json() == {"data": [], "total_rows": 0}
    assert client.get("/movies/search").json() == []
    assert client.post("/movies/process", json={}).status_code == 400


def test_sample_upload_and_list(client, uploaded_movies):
    assert uploaded_movies == {
        "filename": "sample_movies.csv", "rows": 20, "columns": 4,
        "column_names": ["title", "release_year", "rating", "genre"],
    }
    response = client.get("/movies", params={"limit": 2})
    assert response.json() == {
        "data": [
            {"id": 1, "title": "Movie A", "release_year": 2020, "rating": 8.0, "genre": "Drama"},
            {"id": 2, "title": "Movie B", "release_year": 2021, "rating": 8.5, "genre": "Comedy"},
        ],
        "total_rows": 20,
    }


def test_search_filters_sorts_and_projects(client, uploaded_movies):
    params = [("min_rating", 8.5), ("limit", 2)]
    assert client.get("/movies/search", params=params).json() == [
        {"id": 4, "title": "Movie C"}, {"id": 2, "title": "Movie B"},
    ]
    params += [("columns", "title"), ("columns", "rating")]
    assert client.get("/movies/search", params=params).json() == [
        {"id": 4, "title": "Movie C", "rating": 9.0},
        {"id": 2, "title": "Movie B", "rating": 8.5},
    ]
    assert client.get("/movies/search?min_rating=10").json() == []
    assert client.get("/movies/search", params={"columns": "title FROM movies"}).status_code == 400


@pytest.mark.parametrize("path", ["/movies?limit=0", "/movies/search?min_rating=11", "/movies/search?limit=-1"])
def test_invalid_query_parameters(client, path):
    assert client.get(path).status_code == 422


@pytest.mark.parametrize("filename,contents", [
    ("data.txt", b"title\nA\n"),
    ("data", b"title\nA\n"),
    ("empty.csv", b""),
    ("bad.csv", b'title,release_year,rating,genre\n"unterminated'),
    ("encoding.csv", b"title\n\xff\n"),
    ("wrong_columns.csv", b"title,rating\nA,7\n"),
    ("duplicate_column.csv", b"title,release_year,rating,rating\nA,2020,7,Drama\n"),
    ("headers_only.csv", b"title,release_year,rating,genre\n"),
])
def test_invalid_upload_keeps_previous_collection(client, uploaded_movies, filename, contents):
    assert client.post("/upload", files={"file": (filename, contents)}).status_code == 400
    assert client.get("/movies").json()["total_rows"] == 20
    assert client.get("/health").status_code == 200


def test_upload_replaces_collection_and_preserves_null(client, uploaded_movies):
    contents = b"genre,rating,title,release_year\nDrama,,Replacement,2025\n"
    response = client.post("/upload", files={"file": ("other.CSV", contents)})
    assert response.status_code == 200
    assert client.get("/movies").json() == {
        "data": [{"id": 1, "title": "Replacement", "release_year": 2025,
                  "rating": None, "genre": "Drama"}],
        "total_rows": 1,
    }


def test_process_and_retrieve(client, uploaded_movies):
    response = client.post("/movies/process", json={
        "validation": {"required_columns": ["title", "rating"], "numeric_columns": ["rating"]}
    })
    assert response.status_code == 200
    assert response.json() == {
        "validation_rows_removed": 0,
        "cleaning_report": {
            "rows_before": 20, "rows_after": 18, "rows_removed": 2,
            "columns_before": 4, "columns_after": 4, "columns_removed": 0,
        },
    }
    assert client.get("/movies").json()["total_rows"] == 18


def test_column_cleanup_keeps_fixed_sql_schema(client):
    contents = b"title,release_year,rating,genre\nA,2020,8,Drama\nB,2021,7,\n"
    assert client.post("/upload", files={"file": ("data.csv", contents)}).status_code == 200
    response = client.post("/movies/process", json={"processing": {"missing": {"axis": "columns"}}})
    assert response.json()["cleaning_report"]["columns_removed"] == 1
    assert [row["genre"] for row in client.get("/movies").json()["data"]] == [None, None]


@pytest.mark.parametrize("body", [
    {"validation": {"required_columns": ["absent"]}},
    {"validation": {"numeric_columns": ["absent"]}},
    {"processing": {"outliers": {"enabled": True, "method": "invalid"}}},
    {"processing": {"missing": {"axis": "invalid"}}},
])
def test_rejected_processing_preserves_collection(client, uploaded_movies, body):
    before = client.get("/movies").json()
    assert client.post("/movies/process", json=body).status_code == 400
    assert client.get("/movies").json() == before


def test_repeated_movie_list_uses_cache_by_limit(client, uploaded_movies, monkeypatch):
    import main

    select_columns = main.storage.select_columns
    calls = []

    def track_select(columns, limit):
        calls.append(limit)
        return select_columns(columns, limit)

    monkeypatch.setattr(main.storage, "select_columns", track_select)
    first = client.get("/movies?limit=1").json()
    assert client.get("/movies?limit=1").json() == first
    assert len(client.get("/movies?limit=2").json()["data"]) == 2
    assert calls == [1, 2]


def test_successful_writes_invalidate_all_list_limits(client, uploaded_movies):
    assert client.get("/movies?limit=1").json()["total_rows"] == 20
    assert client.get("/movies?limit=2").json()["total_rows"] == 20

    assert client.post("/movies/process", json={}).status_code == 200
    assert client.get("/movies?limit=1").json()["total_rows"] == 18
    assert client.get("/movies?limit=2").json()["total_rows"] == 18

    contents = b"title,release_year,rating,genre\nNew Movie,2025,9,Drama\n"
    assert client.post("/upload", files={"file": ("new.csv", contents)}).status_code == 200
    assert client.get("/movies?limit=1").json()["data"][0]["title"] == "New Movie"
    assert client.get("/movies?limit=2").json()["total_rows"] == 1
