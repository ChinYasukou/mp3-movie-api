"""FastAPI endpoints for uploading and retrieving CSV datasets."""

import io
import json
import logging
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from data_pipeline import create_cleaning_report, process_data, validate_dataframe
from src import (
    DatasetInfo,
    DatasetStorage,
    HealthResponse,
    ProcessConfig,
    ProcessingReport,
    log_requests,
    setup_logging,
)


setup_logging(verbose=True)
logger = logging.getLogger(__name__)

app = FastAPI(title="Data Processing API", version="1.0.0")
app.middleware("http")(log_requests)
storage = DatasetStorage()


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Return the application status and version."""
    return HealthResponse(status="ok", version=app.version)


@app.post("/upload", response_model=DatasetInfo)
async def upload_dataset(file: UploadFile = File(...)):
    """Read and store a CSV upload."""
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

    dataset_id = storage.save(df, file.filename)
    logger.info(
        "Uploaded dataset: id=%s, filename=%s, rows=%s",
        dataset_id, file.filename, len(df),
    )
    return DatasetInfo(**storage.get_metadata(dataset_id))


@app.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: int, limit: int = Query(default=100, ge=1)):
    """Return up to limit rows from a stored dataset."""
    df = storage.get(dataset_id)
    if df is None:
        logger.warning("Dataset not found: %s", dataset_id)
        raise HTTPException(status_code=404, detail="Dataset not found.")

    records = json.loads(df.head(limit).to_json(orient="records"))
    logger.info("Retrieved dataset: id=%s, returned_rows=%s", dataset_id, len(records))
    return {"id": dataset_id, "data": records, "total_rows": len(df)}


@app.post("/datasets/{dataset_id}/process", response_model=ProcessingReport)
def process_dataset(dataset_id: int, config: ProcessConfig):
    """Validate and process a stored dataset using MP1 functions."""
    df = storage.get(dataset_id)
    if df is None:
        logger.warning("Dataset not found: %s", dataset_id)
        raise HTTPException(status_code=404, detail="Dataset not found.")

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
        logger.info(
            "Validated dataset: id=%s, validation_removed=%s",
            dataset_id, validation_removed,
        )
        before_processing = validated.copy()
        processed = process_data(validated, settings)
        report = create_cleaning_report(before_processing, processed)
    except ValueError as error:
        logger.warning("Processing rejected: id=%s, error=%s", dataset_id, error)
        raise HTTPException(status_code=400, detail=str(error)) from error

    storage.update(dataset_id, processed)
    logger.info(
        "Processed dataset: id=%s, validation_removed=%s, rows_before=%s, rows_after=%s",
        dataset_id, validation_removed, len(before_processing), len(processed),
    )
    return {
        "id": dataset_id,
        "validation_rows_removed": validation_removed,
        "cleaning_report": report,
    }
