"""Validation functions for pipeline DataFrames."""

import logging

import pandas as pd


logger = logging.getLogger(__name__)


def validate_dataframe(df, required_columns, numeric_columns):
    """Validate required columns and remove invalid numeric values."""
    for column in required_columns:
        if column not in df.columns:
            logger.error("Missing required column: %s", column)
            raise ValueError(f"Missing required column: {column}")

    before = len(df)
    result = df.copy()

    for column in numeric_columns:
        invalid_rows = []
        for index, value in result[column].items():
            if pd.notna(value):
                try:
                    float(value)
                except (TypeError, ValueError):
                    invalid_rows.append(index)

        if invalid_rows:
            logger.warning(
                "Removed %d rows with invalid numeric values in %s",
                len(invalid_rows),
                column,
            )
            result = result.drop(index=invalid_rows)

        result[column] = pd.to_numeric(result[column])

    logger.debug("Validation: %d -> %d rows", before, len(result))
    return result
