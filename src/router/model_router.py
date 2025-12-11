from models.primary_model_client import PrimaryModelClient
from models.backup_model_client import BackupModelClient
from models.lite_model_client import LiteModelClient
from models.fallback_policy import FallbackPolicy
from infra.circuit_breaker import CircuitBreaker


class ModelRouter:
    """
    ModelRouter exposes a single `infer` method and routes traffic
    between primary, backup, and lite models according to the fallback policy
    and circuit breaker state.

    The `config` object is expected to have at least:
      - primary_endpoint: str
      - backup_endpoint: str
      - lite_endpoint: str
      - enable_backup: bool
      - blacklist_backup: collection
      - tenants_force_lite: collection
      - tenants_strict_sl: collection
    """

    def __init__(self, config) -> None:
        self.primary = PrimaryModelClient(config.primary_endpoint)
        self.backup = BackupModelClient(config.backup_endpoint)
        self.lite = LiteModelClient(config.lite_endpoint)

        # FallbackPolicy uses the same config instance.
        self.fallback_policy = FallbackPolicy(config)

        # A simple circuit breaker for the primary model.
        self.circuit_breaker = CircuitBreaker("primary_model")

    def infer(self, request, tenant_id: str):
        """
        Route the inference request according to:
          - force-lite policy
          - circuit breaker state
          - backup and lite fallback rules on exceptions / timeouts
        """

        # 1. Hard force to lite model for some tenants.
        if self.fallback_policy.force_lite(tenant_id):
            return self.lite.infer(request)

        # 2. Try primary model if circuit breaker allows it.
        try:
            if self.circuit_breaker.allow_request():
                return self.primary.infer(request)
        except TimeoutError:
            # Record failure and decide whether to use backup or lite.
            self.circuit_breaker.record_failure()
            if self.fallback_policy.allow_backup_on_timeout(tenant_id):
                return self.backup.infer(request)
            return self.lite.infer(request)
        except Exception:
            # Record failure and decide whether to use backup or lite.
            self.circuit_breaker.record_failure()
            if self.fallback_policy.allow_backup_on_error(tenant_id):
                return self.backup.infer(request)
            return self.lite.infer(request)

        # 3. If primary is not allowed anymore (breaker open), decide backup vs lite.
        if self.fallback_policy.use_backup_when_open(tenant_id) and \
                self.circuit_breaker.is_open():
            return self.backup.infer(request)

        if self.circuit_breaker.is_open():
            # Breaker open and backup not allowed -> use lite.
            return self.lite.infer(request)

        # 4. Safety net: if for any reason none of the above returned,
        #    degrade to lite model.
        return self.lite.infer(request)
