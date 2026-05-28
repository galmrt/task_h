class FailureLogError(Exception):
    """Base exception for the failure-logging substrate."""


class AppendOnlyViolationError(FailureLogError):
    """Raised when an attempt to UPDATE or DELETE a stored failure is made."""


class BypassViolationError(FailureLogError):
    """Raised by the static-analysis check when a direct INSERT into the failures
    table is found outside the sanctioned log_failure -> DAO.insert path."""


class UnknownFailureClassError(FailureLogError, ValueError):
    """Raised when failure_class is outside the closed enumeration from config."""
