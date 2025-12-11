class LiteModelClient:
    """
    Simple lite model client used as the last-resort fallback model.
    """

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint

    def infer(self, request):
        """
        Dummy inference method that echoes back which model handled the request.
        """
        return {
            "model": "lite",
            "endpoint": self.endpoint,
            "request": request,
        }
