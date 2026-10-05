"""Custom exceptions for ai-release-contract."""


class InputError(Exception):
    """Raised for exit-code-2 conditions (missing files, bad schema, config errors)."""

    def __init__(self, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code
