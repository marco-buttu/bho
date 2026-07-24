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

## Configure Hermes for bho

Run:

```bash
bho hermes configure
```

If Docker is missing, stopped, or inaccessible to the current user, the command
offers an explicit guided repair before configuring Hermes. Privileged commands
are displayed first and require confirmation. Adding the user to the `docker`
group requires separate confirmation and a complete logout and login before the
command can continue.

After Docker is ready, the command creates or reuses the isolated Hermes profile
`bho`, opens the official Hermes model wizard, configures the Docker terminal
backend, and runs a minimal live verification. Use `--skip-live-check` to avoid
the inference request. Credentials remain stored only by Hermes.
