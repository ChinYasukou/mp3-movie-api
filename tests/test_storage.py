"""Verify storage isolation, metadata updates, and dataset lifecycle."""

import logging

import pandas as pd

from src import storage as storage_module


def test_save_assigns_sequential_ids_and_copies_input():
    storage = storage_module.DatasetStorage()
    original = pd.DataFrame({"score": [80, 90]})
    first_id = storage.save(original, "first.csv")
    second_id = storage.save(original, "second.csv")
    original.loc[0, "score"] = 0

    assert (first_id, second_id) == (1, 2)
    assert storage.get(first_id).loc[0, "score"] == 80


def test_get_returns_a_copy_until_update_is_called():
    storage = storage_module.DatasetStorage()
    dataset_id = storage.save(pd.DataFrame({"score": [80, 90]}), "scores.csv")
    retrieved = storage.get(dataset_id)
    retrieved.loc[0, "score"] = 100

    assert storage.get(dataset_id).loc[0, "score"] == 80
    assert storage.update(dataset_id, retrieved) is True
    assert storage.get(dataset_id).loc[0, "score"] == 100
    retrieved.loc[0, "score"] = 0
    assert storage.get(dataset_id).loc[0, "score"] == 100


def test_metadata_reflects_current_dataframe_and_preserves_filename():
    storage = storage_module.DatasetStorage()
    dataset_id = storage.save(pd.DataFrame({"score": [80, 90]}), "scores.csv")
    storage.update(dataset_id, pd.DataFrame({"score": [80], "passed": [True]}))

    assert storage.get_metadata(dataset_id) == {
        "id": dataset_id,
        "filename": "scores.csv",
        "rows": 1,
        "columns": 2,
        "column_names": ["score", "passed"],
    }


def test_missing_datasets_and_clear_reset():
    storage = storage_module.DatasetStorage()
    data = pd.DataFrame({"score": [80]})

    assert storage.get(999) is None
    assert storage.get_metadata(999) is None
    assert storage.update(999, data) is False
    assert storage.save(data, "scores.csv") == 1
    storage.clear()
    assert storage.get(1) is None
    assert storage.get_metadata(1) is None
    assert storage.save(data, "new.csv") == 1


def test_storage_operations_log_at_debug(caplog):
    storage = storage_module.DatasetStorage()
    data = pd.DataFrame({"score": [80]})
    with caplog.at_level(logging.DEBUG, logger="src.storage"):
        dataset_id = storage.save(data, "scores.csv")
        storage.get(dataset_id)
        storage.get_metadata(dataset_id)
        storage.update(dataset_id, data)
        storage.clear()

    assert len(caplog.records) == 5
    assert all(record.levelno == logging.DEBUG for record in caplog.records)
