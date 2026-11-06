"""Reusable, configuration-driven data-cleaning functions."""

import logging

import pandas as pd


logger = logging.getLogger(__name__)


def remove_duplicates(df):
    """Remove duplicate rows."""
    before = len(df)
    result = df.drop_duplicates()
    logger.debug("remove_duplicates: %d -> %d rows", before, len(result))
    return result


def handle_missing(df, axis="rows"):
    """Drop rows or columns containing missing values."""
    if axis == "rows":
        before = len(df)
        result = df.dropna()
        logger.debug("handle_missing: %d -> %d rows", before, len(result))
        return result

    if axis == "columns":
        before = len(df.columns)
        result = df.dropna(axis=1)
        logger.debug("handle_missing: %d -> %d columns", before, len(result.columns))
        return result

    logger.error("Unsupported missing-value axis: %s", axis)
    raise ValueError(f"Unsupported missing-value axis: {axis}")


def remove_outliers(df, columns, method, threshold):
    """Remove outliers from the specified numeric columns."""
    if method not in {"iqr", "zscore"}:
        logger.error("Unsupported outlier method: %s", method)
        raise ValueError(f"Unsupported outlier method: {method}")

    result = df
    for column in columns:
        if column not in result.columns:
            logger.warning("Column not found: %s", column)
            continue

        if not pd.api.types.is_numeric_dtype(result[column]):
            logger.warning("Column is not numeric: %s", column)
            continue

        before = len(result)
        if method == "iqr":
            first_quartile = result[column].quantile(0.25)
            third_quartile = result[column].quantile(0.75)
            iqr = third_quartile - first_quartile
            lower = first_quartile - threshold * iqr
            upper = third_quartile + threshold * iqr
            within_bounds = result[column].between(lower, upper)
            result = result[result[column].isna() | within_bounds]
        else:
            mean = result[column].mean()
            standard_deviation = result[column].std(ddof=0)
            if standard_deviation == 0:
                result = result.copy()
            else:
                z_scores = (result[column] - mean).abs() / standard_deviation
                result = result[result[column].isna() | (z_scores <= threshold)]

        logger.debug(
            "%s: method=%s, threshold=%s, removed=%d",
            column,
            method,
            threshold,
            before - len(result),
        )

    return result


def process_data(df, config):
    """Apply the processing steps enabled in the configuration."""
    processing = config["processing"]
    result = df

    if processing["remove_duplicates"]:
        result = remove_duplicates(result)

    missing = processing["missing"]
    if missing["enabled"]:
        result = handle_missing(result, axis=missing["axis"])

    outliers = processing["outliers"]
    if outliers["enabled"]:
        result = remove_outliers(
            result,
            columns=outliers["columns"],
            method=outliers["method"],
            threshold=outliers["threshold"],
        )

    return result


def create_cleaning_report(df_before, df_after):
    """Return a dictionary summarizing the cleaning results."""
    rows_before, columns_before = df_before.shape
    rows_after, columns_after = df_after.shape
    return {
        "rows_before": rows_before,
        "rows_after": rows_after,
        "rows_removed": rows_before - rows_after,
        "columns_before": columns_before,
        "columns_after": columns_after,
        "columns_removed": columns_before - columns_after,
    }
