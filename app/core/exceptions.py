"""Application exceptions and shared error response helpers."""

from typing import Any


class AppError(Exception):
    """Base application error that maps to the shared error JSON shape."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)

    def to_dict(self) -> dict[str, str]:
        return {"error": self.code, "message": self.message}


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__("not_found", message, status_code=404)


class ConflictError(AppError):
    def __init__(self, message: str = "Conflict") -> None:
        super().__init__("conflict", message, status_code=409)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Unauthorized") -> None:
        super().__init__("unauthorized", message, status_code=401)


class BadRequestError(AppError):
    def __init__(self, message: str = "Bad request") -> None:
        super().__init__("bad_request", message, status_code=400)
