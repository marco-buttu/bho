# Local development setup

Extract this archive inside the repository root, then run:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Verify the command:

```bash
bho version
```

Run the tests:

```bash
pytest
```
