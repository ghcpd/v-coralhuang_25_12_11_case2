Test README

How to run
----------

1. Install pytest (only dependency):

   pip install pytest

2. Run tests from the project root:

   pytest -q

Repository layout expected:

.
├── src/
│   └── ... (production code is under src/ and is importable during tests)
└── tests/
    ├── test_model_router.py
    └── README.md

Notes on tests and mocking strategy
----------------------------------

- Tests use unittest.mock.Mock and pytest to monkeypatch model client behaviors.
- We simulate TimeoutError and generic exceptions by setting side_effect on the primary model's .infer method.
- The circuit breaker is manipulated directly (setting _open) to simulate an open state for some tests.
- Assertions verify which model client `.infer()` was called and that other clients were not invoked.
