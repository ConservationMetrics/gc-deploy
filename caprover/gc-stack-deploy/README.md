# gc-stack-deploy

## Development install

From this directory, create a virtual environment and install the package in editable mode, with the dev dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

This puts a `gc-stack-deploy` command at `.venv/bin/gc-stack-deploy`. Edits under `src/` take effect without reinstalling.

(`make -C ../tests setup-venv` does the same thing, but puts the venv at `caprover/tests/.venv` and omits the dev dependencies. It is not needed for development.)

## Tests

See [`caprover/tests/README.md`](../tests/README.md) for how to run unit and end-to-end tests.
