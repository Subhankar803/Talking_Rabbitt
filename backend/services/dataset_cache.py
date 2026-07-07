"""
dataset_cache.py

Cleaned dataframes are expensive to reclean on every request, and MySQL
is not the right place to store thousands of raw rows. This module keeps
an in-memory cache keyed by dataset_id, backed by a parquet file on disk
so it survives a server restart.
"""
from __future__ import annotations

import pandas as pd
from config import settings

_memory_cache: dict[int, pd.DataFrame] = {}


def cache_path_for(dataset_id_placeholder: str) -> str:
    return str(settings.CACHE_DIR / f"{dataset_id_placeholder}.parquet")


def save(dataset_id: int, df: pd.DataFrame) -> str:
    path = str(settings.CACHE_DIR / f"dataset_{dataset_id}.parquet")
    df.to_parquet(path, index=False)
    _memory_cache[dataset_id] = df
    return path


def load(dataset_id: int, cache_path: str) -> pd.DataFrame:
    if dataset_id in _memory_cache:
        return _memory_cache[dataset_id]
    df = pd.read_parquet(cache_path)
    _memory_cache[dataset_id] = df
    return df
