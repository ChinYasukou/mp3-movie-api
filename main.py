"""FastAPI endpoints for uploading, querying, and cleaning movies."""

import io
import logging
from pathlib import Path
from threading import Lock

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from data_pipeline import create_cleaning_report, process_data, validate_dataframe
from src import (
    HealthResponse,
    MovieDataResponse,
    MovieProcessingReport,
    MovieStorage,
    MovieUploadInfo,
    ProcessConfig,
    log_requests,
    setup_logging,
)
from src.cache import MovieCache
from src.storage import MOVIE_COLUMNS


setup_logging(verbose=True)
logger = logging.getLogger(__name__)

app = FastAPI(title="Movie API", version="1.0.0")
app.middleware("http")(log_requests)
storage = MovieStorage()
cache = MovieCache()
# Keep each cache fill and collection replacement atomic within this worker.
collection_lock = Lock()


def replace_movies(df):
    with collection_lock:
        storage.save(df)
        cache.invalidate()


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Return the application status and version."""
    return HealthResponse(status="ok", version=app.version)


@app.post("/upload", response_model=MovieUploadInfo)
async def upload_movies(file: UploadFile = File(...)):
    """Read a CSV and replace the current movie collection."""
    extension = Path(file.filename or "").suffix.lower()
    if extension != ".csv":
        logger.warning("Unsupported file format: %s", extension)
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents))
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        logger.warning("Unable to read CSV file %s: %s", file.filename, exc)
        raise HTTPException(
            status_code=400,
            detail="Unable to read CSV. Provide a UTF-8 CSV with column headers and valid formatting.",
        ) from exc

    if set(df.columns) != set(MOVIE_COLUMNS):
        expected = ", ".join(MOVIE_COLUMNS)
        raise HTTPException(status_code=400, detail=f"Expected these columns: {expected}.")
    if df.empty:
        raise HTTPException(status_code=400, detail="CSV must contain at least one movie.")

    await run_in_threadpool(replace_movies, df[MOVIE_COLUMNS])
    logger.info("Uploaded movies: filename=%s, rows=%s", file.filename, len(df))
    return MovieUploadInfo(
        filename=file.filename,
        rows=len(df),
        columns=len(MOVIE_COLUMNS),
        column_names=MOVIE_COLUMNS,
    )


@app.get("/movies", response_model=MovieDataResponse)
def get_movies(limit: int = Query(default=100, ge=1)):
    """Return up to limit movies in insertion order."""
    with collection_lock:
        cached = cache.get(limit)
        if cached is not None:
            logger.info("Retrieved movies from cache: limit=%s, returned_rows=%s", limit, len(cached["data"]))
            return cached

        records = storage.select_columns(MOVIE_COLUMNS, limit)
        response = {"data": records, "total_rows": storage.count_movies()}
        cache.set(limit, response)
    logger.info("Retrieved movies from SQLite: limit=%s, returned_rows=%s", limit, len(records))
    return response


@app.get("/movies/search", response_model=list[dict])
def query_movies(
    columns: list[str] = Query(default=["title"]),
    min_rating: float = Query(default=0, ge=0, le=10),
    limit: int = Query(default=100, ge=1),
):
    """Find qualifying movies and return the requested fields."""
    try:
        records = storage.query_movies(columns, min_rating, limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    logger.info(
        "Queried movies: columns=%s, min_rating=%s, returned_rows=%s",
        columns, min_rating, len(records),
    )
    return records


@app.post("/movies/process", response_model=MovieProcessingReport)
def process_movies(config: ProcessConfig):
    """Validate and clean the current collection using the MP1 pipeline."""
    with collection_lock:
        df = storage.get()
        if df.empty:
            raise HTTPException(status_code=400, detail="No movies to process.")

        settings = config.model_dump()
        validation = settings["validation"]
        try:
            for column in validation["numeric_columns"]:
                if column not in df.columns:
                    raise ValueError(f"Missing numeric column: {column}")
            validated = validate_dataframe(
                df, validation["required_columns"], validation["numeric_columns"]
            )
            validation_removed = len(df) - len(validated)
            logger.info("Validated movies: validation_removed=%s", validation_removed)
            before_processing = validated.copy()
            processed = process_data(validated, settings)
            report = create_cleaning_report(before_processing, processed)
        except ValueError as error:
            logger.warning("Processing rejected: error=%s", error)
            raise HTTPException(status_code=400, detail=str(error)) from error

        # The SQL schema stays fixed when the cleaner removes a field.
        storage.save(processed.reindex(columns=MOVIE_COLUMNS))
        cache.invalidate()
        logger.info(
            "Processed movies: validation_removed=%s, rows_before=%s, rows_after=%s",
            validation_removed, len(before_processing), len(processed),
        )
        return {"validation_rows_removed": validation_removed, "cleaning_report": report}
