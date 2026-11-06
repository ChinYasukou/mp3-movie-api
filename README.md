# MP3 Movie API

A FastAPI application for uploading, searching, and cleaning one movie collection. SQLite stores the collection across server restarts.

## Run locally

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Open [Swagger UI](http://127.0.0.1:8000/docs). The app creates `data/movies.db` on startup.

| Request | Behavior |
| --- | --- |
| `GET /health` | Return the API status and version. |
| `POST /upload` | Upload `fixtures/sample_movies.csv` as multipart field `file`. Each successful upload replaces the collection. |
| `GET /movies?limit=2` | Return two movies in insertion order and the total stored count. The sample contains 20 rows. |
| `GET /movies/search?columns=title&columns=rating&min_rating=8.5&limit=2` | Return Movie C and Movie B, ordered by rating and then ID. |
| `POST /movies/process` | Run the MP2 validation and cleaning pipeline. An empty JSON object uses the defaults and reduces the sample from 20 to 18 rows. |

The single Uvicorn worker caches `GET /movies` responses in fakeredis for 60 seconds, keyed by limit. Successful uploads and processing clear all cached limits after saving to SQLite. Search queries read directly from SQLite. If cleaning drops a column, the fixed movie schema stores it as SQL NULL and the cleaning report records the removal.

## Tests

```bash
python -m pytest -q
```
