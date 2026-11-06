"""Store and query a single movie collection in SQLite."""

import logging
import sqlite3

import pandas as pd

from .database import get_connection, initialize_database


logger = logging.getLogger(__name__)
MOVIE_COLUMNS = ["title", "release_year", "rating", "genre"]


class MovieStorage:
    def __init__(self, db_path="data/movies.db"):
        self.db_path = db_path
        initialize_database(self.db_path)

    def save(self, df):
        """Replace all movie rows in one transaction."""
        values = df[MOVIE_COLUMNS].replace([float("inf"), float("-inf")], None)
        values = values.astype(object).where(values.notna(), None)
        connection = get_connection(self.db_path)
        try:
            connection.execute("DELETE FROM movies")
            connection.executemany(
                "INSERT INTO movies (title, release_year, rating, genre) VALUES (?, ?, ?, ?)",
                values.itertuples(index=False, name=None),
            )
            connection.commit()
        except sqlite3.Error:
            connection.rollback()
            raise
        finally:
            connection.close()
        logger.debug("Stored movies in SQLite: rows=%s", len(df))

    def get(self):
        """Return the movie fields as a DataFrame in insertion order."""
        connection = get_connection(self.db_path)
        try:
            rows = connection.execute(
                "SELECT title, release_year, rating, genre FROM movies ORDER BY id"
            ).fetchall()
            return pd.DataFrame.from_records(rows, columns=MOVIE_COLUMNS)
        finally:
            connection.close()

    def select_columns(self, columns, limit=5):
        """Return id plus the selected movie fields in insertion order."""
        fields = self._selected_fields(columns)
        connection = get_connection(self.db_path)
        try:
            rows = connection.execute(
                f"SELECT {fields} FROM movies ORDER BY id LIMIT ?", (limit,)
            ).fetchall()
        finally:
            connection.close()
        logger.debug("Selected movies: columns=%s, rows=%s", columns, len(rows))
        return [dict(row) for row in rows]

    def count_movies(self):
        """Return the number of stored movies."""
        connection = get_connection(self.db_path)
        try:
            return connection.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
        finally:
            connection.close()

    def query_movies(self, columns, min_rating, limit):
        """Return selected fields for qualifying movies in descending rating order."""
        fields = self._selected_fields(columns)
        connection = get_connection(self.db_path)
        try:
            rows = connection.execute(
                f"""
                SELECT {fields} FROM movies
                WHERE typeof(rating) IN ('integer', 'real') AND rating >= ?
                ORDER BY rating DESC, id ASC
                LIMIT ?
                """,
                (min_rating, limit),
            ).fetchall()
        finally:
            connection.close()
        logger.debug("Queried movies: columns=%s, rows=%s", columns, len(rows))
        return [dict(row) for row in rows]

    @staticmethod
    def _selected_fields(columns):
        if not columns:
            logger.error("Select at least one column")
            raise ValueError("Select at least one column")
        for column in columns:
            if column not in MOVIE_COLUMNS:
                logger.error("Unsupported column: %s", column)
                raise ValueError(f"Unsupported column: {column}")
        return ", ".join(["id", *columns])
