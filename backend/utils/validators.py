"""
validators.py
Input validation helpers shared across routes.
"""
from fastapi import HTTPException

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def validate_file_extension(filename: str):
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    return ext


def validate_file_size(size_bytes: int, max_mb: int):
    max_bytes = max_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds {max_mb}MB limit.",
        )


def validate_dataset_exists(dataset):
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found. Upload a file first.")
