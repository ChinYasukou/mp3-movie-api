"""In-memory storage for uploaded datasets."""

import logging


logger = logging.getLogger(__name__)


class DatasetStorage:
    def __init__(self):
        self._store = {}
        self._counter = 0

    def save(self, df, filename):
        """Store a copy of the data and return a new integer ID."""
        self._counter += 1
        dataset_id = self._counter
        self._store[dataset_id] = {"filename": filename, "df": df.copy()}
        logger.debug("Stored dataset: id=%s, rows=%s", dataset_id, len(df))
        return dataset_id

    def get(self, dataset_id):
        """Return a copy of the stored DataFrame, or None."""
        dataset = self._store.get(dataset_id)
        if dataset is None:
            logger.debug("Dataset not found for retrieval: id=%s", dataset_id)
            return None
        df = dataset["df"].copy()
        logger.debug("Retrieved dataset copy: id=%s, rows=%s", dataset_id, len(df))
        return df

    def get_metadata(self, dataset_id):
        """Return metadata calculated from the current dataset, or None."""
        dataset = self._store.get(dataset_id)
        if dataset is None:
            logger.debug("Dataset not found for metadata: id=%s", dataset_id)
            return None
        df = dataset["df"]
        logger.debug("Retrieved dataset metadata: id=%s", dataset_id)
        return {
            "id": dataset_id,
            "filename": dataset["filename"],
            "rows": df.shape[0],
            "columns": df.shape[1],
            "column_names": df.columns.tolist(),
        }

    def update(self, dataset_id, df):
        """Replace an existing dataset; return True, or False if missing."""
        if dataset_id not in self._store:
            logger.debug("Dataset not found for update: id=%s", dataset_id)
            return False
        self._store[dataset_id]["df"] = df.copy()
        logger.debug("Updated dataset: id=%s, rows=%s", dataset_id, len(df))
        return True

    def clear(self):
        """Clear all data and reset the ID counter."""
        self._store.clear()
        self._counter = 0
        logger.debug("Cleared all datasets and reset ID counter")
