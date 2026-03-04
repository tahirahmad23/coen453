from __future__ import annotations


class AppException(Exception):
    """Base exception for application errors."""
    pass

class AuthError(AppException):
    """Authentication or authorization failed."""
    pass

class NotFoundError(AppException):
    """Resource not found."""
    pass

class ForbiddenError(AppException):
    """Access forbidden."""
    pass

class ValidationError(AppException):
    """Input validation failed."""
    pass

class TokenExpiredError(AppException):
    """Temporary token has expired."""
    pass

class TokenAlreadyUsedError(AppException):
    """Token has already been used."""
    pass
