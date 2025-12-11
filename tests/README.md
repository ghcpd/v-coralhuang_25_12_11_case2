Test suite README

How to install dependencies

1. Create a Python virtual environment (recommended):

   python -m venv .venv
   .\.venv\Scripts\activate   (Windows)

2. Install pytest only:

   pip install pytest


How to run the tests

From the project root (the folder that contains `src/` and `tests/`), run:

   pytest -q

The test run assumes `src/` is importable. The included `tests/conftest.py` also ensures `src/` is added to sys.path when running locally.

Expected directory structure

project-root/
  src/
    router/
      model_router.py
    models/
      primary_model_client.py
      backup_model_client.py
      lite_model_client.py
      fallback_policy.py
    infra/
      circuit_breaker.py
  tests/
    conftest.py
    test_model_router.py
    README.md

Notes on what the tests validate (fallback logic)

- Primary timeout -> when `enable_backup` is True and tenant is not blacklisted, the router falls back to the backup model.
- Primary generic exception -> when `enable_backup` is False, the router falls back to the lite model.
- Circuit breaker open transitions -> when the breaker is open and the tenant is marked as `strict_sl`, the router degrades to lite and does not call backup or primary.
- Force-lite tenant -> the router immediately routes to lite and does not call primary or backup.

Notes about mocking strategies used in tests

- Tests do not modify production code. They replace the `infer` callables on the instantiated `ModelRouter`'s client attributes (router.primary, router.backup, router.lite) with plain functions or unittest.mock.Mock instances to simulate success, TimeoutError, or generic Exception.
- Circuit breaker state is manipulated via the public `record_failure()` method to open the breaker (this simulates consecutive failures) or by asserting `is_open()` when needed.
- The tests create a minimal config object using `types.SimpleNamespace` with only the attributes read by `FallbackPolicy` and `ModelRouter`.

Why this is safe and minimal

- The production model client implementations in `src/models/*` are simple, synchronous, and do not perform network I/O during construction; tests still stub `infer` to assert call behavior and to simulate failures.
- Tests keep topology and initialization identical to production usage (ModelRouter(config)) while controlling external behavior via monkeypatching/mocking.
