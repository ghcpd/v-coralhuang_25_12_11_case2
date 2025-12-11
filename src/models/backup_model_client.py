class BackupModelClient:
    """
    Simple backup model client used for testing fallback behavior.
    """

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint

    def infer(self, request):
        """
        Dummy inference method that echoes back which model handled the request.
        """
        return {
            "model": "backup",
            "endpoint": self.endpoint,
            "request": request,
        }
