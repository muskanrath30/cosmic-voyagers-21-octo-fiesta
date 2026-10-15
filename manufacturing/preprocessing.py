from __future__ import annotations


NUMERIC_FEATURES = [
    "Air temperature",
    "Process temperature",
    "Rotational speed",
    "Torque",
    "Tool wear",
]

CATEGORICAL_FEATURES = [
    "Type",
]

TARGET = "Machine failure"


def prepare_dataframe(df):
    """
    Clean the AI4I 2020 dataset.

    Removes:
    - UDI/Product ID if present
    - Failure-type indicator columns

    Keeps the actual sensor features used by our ML model.
    """

    df = df.copy()

    columns_to_drop = [
        "UDI",
        "Product ID",
        "TWF",
        "HDF",
        "PWF",
        "OSF",
        "RNF",
    ]

    for column in columns_to_drop:
        if column in df.columns:
            df = df.drop(columns=[column])

    return df

# ---------------------------------------------------------------------------
# Record validation (used by model_scoring before any record reaches a model
# or a prompt)
# ---------------------------------------------------------------------------

import math


class InvalidRecordError(ValueError):
    """The sensor record is malformed, non-numeric or too incomplete."""


def build_feature_row(
    features: list[str],
    categorical: list[str],
    record: dict,
    defaults: dict | None = None,
    min_fraction: float = 0.7,
    allowed_categories: dict | None = None,
) -> dict:
    """
    Validate one record and return {feature: value} in model order.

    - numeric features must be finite numbers
    - missing numeric features are filled from `defaults` (training medians);
      the record is rejected if fewer than `min_fraction` of features are given
    - categorical features must be a short alphanumeric token
    """

    if not isinstance(record, dict):
        raise InvalidRecordError("record must be an object")

    defaults = defaults or {}
    allowed_categories = allowed_categories or {}

    row: dict = {}
    provided = 0

    for name in features:

        value = record.get(name)

        if name in categorical:
            if value is None:
                if name in defaults:
                    row[name] = defaults[name]
                    continue
                raise InvalidRecordError(f"missing categorical field '{name}'")
            token = str(value).strip()
            if not token.isalnum() or len(token) > 8:
                raise InvalidRecordError(f"invalid value for '{name}'")
            allowed = allowed_categories.get(name)
            if allowed and token not in allowed:
                raise InvalidRecordError(
                    f"'{name}' must be one of {sorted(allowed)}"
                )
            row[name] = token
            provided += 1
            continue

        if value is None or value == "":
            if name in defaults:
                row[name] = float(defaults[name])
                continue
            raise InvalidRecordError(f"missing field '{name}'")

        try:
            number = float(value)
        except (TypeError, ValueError):
            raise InvalidRecordError(f"'{name}' is not numeric") from None

        if not math.isfinite(number):
            raise InvalidRecordError(f"'{name}' is not finite")

        row[name] = number
        provided += 1

    if features and provided / len(features) < min_fraction:
        raise InvalidRecordError(
            f"only {provided}/{len(features)} required fields were provided"
        )

    return row
