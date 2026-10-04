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