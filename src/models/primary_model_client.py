class PrimaryModelClient:
    """
    Simple primary model client used for testing.
    The default implementation does not raise exceptions.
    Tests can monkeypatch or mock `infer` to simulate failures.
    """

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint

    def infer(self, request):
        """
        Dummy inference method that echoes back which model handled the request.
        """
        return {
            "model": "primary",
            "endpoint": self.endpoint,
            "request": request,
        }
