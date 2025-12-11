# Fallback Coverage Backlog

This is a small backlog of unit test tasks for covering fallback logic in ModelRouter.

- TODO: Cover primary-success happy path
  - File: src/router/model_router.py (infer)
  - Test: Unit
  - Expected outcome: PrimaryModelClient.infer is called and returned value is routed
  - Risk: Low

- TODO: Cover generic Exception on primary -> allow_backup_on_error True
  - File: src/router/model_router.py, src/models/fallback_policy.py
  - Test: Unit
  - Expected outcome: When primary raises Exception and backup is allowed, backup.infer is called
  - Risk: Medium

- TODO: Cover circuit break open due to repeated failures
  - File: src/infra/circuit_breaker.py and src/router/model_router.py
  - Test: Unit (simulate repeated failures) or Integration (call through router)
  - Expected outcome: Router uses backup when breaker opens and is_open True + use_backup_when_open True
  - Risk: High

- TODO: Cover force-lite tenant
  - File: src/models/fallback_policy.py, src/router/model_router.py
  - Test: Unit
  - Expected outcome: Force-lite tenant uses lite.infer only
  - Risk: Medium

- TODO: Cover strict SL behavior when primary times out/errors (incident)
  - File: src/models/fallback_policy.py, src/router/model_router.py
  - Test: Unit
  - Expected outcome: Decide on policy — either prevent backup for strict SL tenants always OR keep current behavior.
  - Risk: High (production incident risk)
