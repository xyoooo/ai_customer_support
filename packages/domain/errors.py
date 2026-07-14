class DomainError(Exception):
    """Base class for expected business-rule failures."""

    status_code = 400
    code = "domain_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class AuthenticationError(DomainError):
    status_code = 401
    code = "authentication_failed"


class AuthorizationError(DomainError):
    status_code = 403
    code = "forbidden"
