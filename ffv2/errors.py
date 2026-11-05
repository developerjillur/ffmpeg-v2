from __future__ import annotations


class FFV2Error(Exception):
    def __init__(self, code, message, *, details=None, retryable=False, exit_code=1):
        super().__init__(message)
        self.code = code
        self.details = details or {}
        self.retryable = retryable
        self.exit_code = exit_code

    def payload(self):
        return {"code": self.code, "message": str(self), "retryable": self.retryable,
                "details": self.details}
