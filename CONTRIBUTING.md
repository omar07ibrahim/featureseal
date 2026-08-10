# Contributing to FeatureSeal

Thank you for helping make temporal feature joins easier to audit.

## Development setup

Use a supported CPython version (3.11 through 3.14):

    python -m venv .venv
    . .venv/bin/activate
    python -m pip install --no-deps --require-hashes -r requirements/quality.txt
    python -m pip install --no-build-isolation --no-deps -e .

Run the complete quality gate:

    python -m ruff check .
    python -m ruff format --check .
    python -m mypy
    python -m pytest -q --cov=featureseal --cov-report=term-missing --cov-fail-under=92
    git diff --check

## Change expectations

- Add or update deterministic tests for behavior changes.
- Preserve strict input bounds and exclusive output creation.
- Keep analyzer and SQLite verifier implementations independent.
- Do not weaken canonicalization, exact-field replay, or receipt integrity.
- Use synthetic fixtures only; never commit private events, credentials, or personal data.
- Explain user-visible changes in the changelog.
- Keep commits focused and reviewable.

## Visual evidence

Files under <code>docs/evidence/</code> are generated. Do not edit them by hand.

When a source, scenario, report, or evidence tool changes, open the pull request and let the evidence workflow regenerate the bundle. Review real screenshots, the GIF, SVGs, and manifest together. A valid update must remain source-bound and independently replayable.

## Pull requests

A pull request should state:

- the problem and intended behavior;
- design or trust-boundary changes;
- tests and exact commands run;
- visual/evidence impact;
- compatibility or migration considerations.

Small, linear commits are easiest to review. By contributing, you agree that your contribution is licensed under Apache-2.0.
