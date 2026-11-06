"""Check SQLite persistence and atomic collection replacement."""

import sqlite3

import pandas as pd
import pytest

from src import MovieStorage
from src.database import get_connection
from src.storage import MOVIE_COLUMNS


def test_collection_survives_new_storage_instance(tmp_path):
    path = tmp_path / "data" / "movies.db"
    original = MovieStorage(path)
    assert original.get().columns.tolist() == MOVIE_COLUMNS

    original.save(pd.DataFrame([["A", 2020, 8.0, None]], columns=MOVIE_COLUMNS))
    reopened = MovieStorage(path)
    assert reopened.count_movies() == 1
    assert reopened.select_columns(["genre"]) == [{"id": 1, "genre": None}]


def test_failed_insert_rolls_back_entire_replacement(tmp_path):
    path = tmp_path / "movies.db"
    storage = MovieStorage(path)
    storage.save(pd.DataFrame([["Original", 2020, 8.0, "Drama"]], columns=MOVIE_COLUMNS))
    connection = get_connection(path)
    try:
        connection.execute("""
            CREATE TRIGGER reject_movie BEFORE INSERT ON movies
            WHEN NEW.title = 'Rejected'
            BEGIN
                SELECT RAISE(ABORT, 'test insert failure');
            END
        """)
    finally:
        connection.close()

    replacement = pd.DataFrame(
        [["New", 2021, 9.0, "Comedy"], ["Rejected", 2022, 8.5, "Drama"]],
        columns=MOVIE_COLUMNS,
    )
    with pytest.raises(sqlite3.IntegrityError):
        storage.save(replacement)
    assert storage.select_columns(["title"]) == [{"id": 1, "title": "Original"}]
