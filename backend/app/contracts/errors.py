from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = {}
    correlation_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, details: dict | None = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)
