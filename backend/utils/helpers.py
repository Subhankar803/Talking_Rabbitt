"""
helpers.py
Small generic utilities used across services.
"""
import uuid
from datetime import datetime

import numpy as np
import pandas as pd


def generate_unique_filename(original_name: str) -> str:
    ext = original_name.rsplit(".", 1)[-1].lower()
    return f"{uuid.uuid4().hex}_{int(datetime.utcnow().timestamp())}.{ext}"


def json_safe(value):
    """Recursively convert numpy/pandas types into plain JSON-serializable Python types."""
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else round(float(value), 4)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, float):
        return None if np.isnan(value) else round(value, 4)
    if pd.isna(value) if not isinstance(value, (list, dict)) else False:
        return None
    return value


def dataframe_preview(df: pd.DataFrame, n: int = 10) -> list[dict]:
    return json_safe(df.head(n).to_dict(orient="records"))
