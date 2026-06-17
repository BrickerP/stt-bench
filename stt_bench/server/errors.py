"""API error envelope."""

from fastapi import HTTPException


class APIError(HTTPException):
    def __init__(self, code: str, message: str, status_code: int = 400, details: dict | None = None):
        super().__init__(
            status_code=status_code,
            detail={"error": {"code": code, "message": message, "details": details or {}}},
        )
