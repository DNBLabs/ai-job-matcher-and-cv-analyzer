# Single pytest run, no per-task named CI steps

The backend CI job previously ran 14 named `pytest` steps (one per feature task) followed by a full `pytest -v` catch-all, running every test twice. We replaced all of them with a single `alembic upgrade head` then `pytest -v`.

**Considered alternative:** keep named steps for labelled CI failure output (e.g. "Auth session tests failed"). Rejected because pytest's own output already identifies the failing test precisely; the labels added no signal that wasn't already in the test name. The duplication doubled backend job time for zero benefit.

**Consequence:** new tests added to the suite are automatically covered. There is no per-task grouping to maintain.
