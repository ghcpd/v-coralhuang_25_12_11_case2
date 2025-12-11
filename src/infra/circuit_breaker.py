class CircuitBreaker:
    """
    A very simple in-memory circuit breaker implementation suitable for tests.

    It tracks consecutive failures for a named resource and moves to an 'open'
    state once the failure threshold is reached.
    """

    def __init__(self, name: str, failure_threshold: int = 3) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.failure_count = 0
        self._open = False

    def allow_request(self) -> bool:
        """
        Returns True if the breaker allows a request to be sent to the underlying resource.
        When the breaker is open, it returns False.
        """
        return not self._open

    def record_failure(self) -> None:
        """
        Records a failure and may open the breaker once the threshold is reached.
        """
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self._open = True

    def reset(self) -> None:
        """
        Resets the breaker to the 'closed' state and clears the failure counter.
        """
        self.failure_count = 0
        self._open = False

    def is_open(self) -> bool:
        """
        Returns True if the breaker is currently open.
        """
        return self._open
