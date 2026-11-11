# MP3 Movie API

This FastAPI application uploads, searches, and cleans one movie collection. The endpoints in `main.py` connect the request models in `src/models.py` with SQLite storage and caching. An upload must contain the four movie columns and at least one data row, and each successful upload replaces the current collection in one transaction. The `src/database.py` module creates `data/movies.db`, while `src/storage.py` uses SQL to retrieve, count, and filter movies across server restarts. Processing reuses the MP1 functions in `data_pipeline/` to validate numeric values, remove duplicates, handle missing values, and remove outliers. The `src/cache.py` module caches complete `GET /movies` responses in a dedicated fakeredis instance for 90 seconds using a separate key for each limit. Successful uploads and processing invalidate all cached limits immediately after saving, and failed operations preserve the existing cache. Search requests read directly from SQLite, and middleware and cache logs record request details, cache hits, misses, and invalidation.

## Run locally

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Open [Swagger UI](http://127.0.0.1:8000/docs) and upload `fixtures/sample_movies.csv` using the multipart `file` field of `POST /upload`. Run with a single Uvicorn worker because fakeredis is local to that process. SQLite data persists when the server restarts, and the cache starts empty.

| Request | Behavior |
| --- | --- |
| `GET /health` | Return the API status and version. |
| `GET /movies?limit=100` | Return movies in insertion order and the total count. Repeated calls use the cache. |
| `GET /movies?limit=1` | Use a separate cache entry for this limit. |
| `GET /movies/search?columns=title&columns=rating&min_rating=8.5&limit=2` | Return Movie C and Movie B, ordered by rating and then ID. |
| `POST /movies/process` | Validate and clean the stored collection using the request below. |

## Sample processing request

After uploading the original 20-row sample, send this JSON to `POST /movies/process`.

```json
{
  "validation": {
    "required_columns": ["title", "release_year", "rating", "genre"],
    "numeric_columns": ["release_year", "rating"]
  },
  "processing": {
    "remove_duplicates": true,
    "missing": {"enabled": true, "axis": "rows"},
    "outliers": {
      "enabled": true,
      "columns": ["rating"],
      "method": "iqr",
      "threshold": 1.5
    }
  }
}
```

The expected response is below. Duplicate removal deletes two rows, and IQR filtering removes the two low-rated outliers.

```json
{
  "validation_rows_removed": 0,
  "cleaning_report": {
    "rows_before": 20,
    "rows_after": 16,
    "rows_removed": 4,
    "columns_before": 4,
    "columns_after": 4,
    "columns_removed": 0
  }
}
```

Retrieve `GET /movies?limit=100` again to see a cache miss and 16 records, Movie A through Movie P with IDs 1 through 16. Repeat the request for a cache hit, then restart the server to verify that SQLite still contains 16 rows. Upload the sample again to replace the collection with 20 rows and invalidate all cached limits.

## Tests

```bash
python -m pytest tests -v
```

The suite includes the three required Part 2 tests for persistence, cache invalidation after processing, and cache hits that skip both SQL reads. Additional tests cover cache keys and lifetime, invalid input, failed writes, SQL rollback, and middleware diagnostics.
