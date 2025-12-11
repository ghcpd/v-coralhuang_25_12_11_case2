class FallbackPolicy:
    """
    Fallback policy reads configuration and decides which fallback behavior
    is allowed for a given tenant.

    The `config` object is expected to have the following attributes:
      - enable_backup: bool
      - blacklist_backup: a collection of tenant_ids
      - tenants_force_lite: a collection of tenant_ids
      - tenants_strict_sl: a collection of tenant_ids
    """

    def __init__(self, config) -> None:
        self.config = config

    def force_lite(self, tenant_id: str) -> bool:
        """
        If true, the request should always go to the lite model for this tenant.
        """
        return tenant_id in getattr(self.config, "tenants_force_lite", set())

    def allow_backup_on_timeout(self, tenant_id: str) -> bool:
        """
        Whether this tenant is allowed to use the backup model when a timeout occurs.
        """
        enable_backup = getattr(self.config, "enable_backup", False)
        blacklist_backup = getattr(self.config, "blacklist_backup", set())
        return enable_backup and tenant_id not in blacklist_backup

    def allow_backup_on_error(self, tenant_id: str) -> bool:
        """
        Whether this tenant is allowed to use the backup model when a generic exception occurs.
        """
        enable_backup = getattr(self.config, "enable_backup", False)
        blacklist_backup = getattr(self.config, "blacklist_backup", set())
        return enable_backup and tenant_id not in blacklist_backup

    def use_backup_when_open(self, tenant_id: str) -> bool:
        """
        When the circuit breaker is open for the primary model, this decides whether
        the router should use the backup model or degrade directly to the lite model.
        """
        tenants_strict_sl = getattr(self.config, "tenants_strict_sl", set())
        if tenant_id in tenants_strict_sl:
            # Strict service level tenants may not be allowed to use backup.
            return False

        enable_backup = getattr(self.config, "enable_backup", False)
        return enable_backup
