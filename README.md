# bho

`bho` is a command-line application for managing Hermes Agent and using it to develop, extend, test, document, and maintain software projects.

The project is intentionally designed to start small. The first goal is not to build a fully autonomous software company, but to create a reliable local workflow in which a user can import a project, describe a task, let Hermes work on it, inspect the result, run tests, and decide whether to keep or discard the changes.

## Purpose

`bho` acts as the control layer between the user, Hermes Agent, and one or more software projects.

It is responsible for:

- installing, configuring, updating, and removing Hermes Agent;
- registering existing software projects;
- creating new projects;
- assigning development tasks to Hermes;
- keeping project and task state separate from Hermes internal memory;
- running project code in isolated Docker environments;
- showing plans, logs, tests, and Git changes;
- requiring user approval before important operations such as commits or merges.

Hermes Agent is the initial agentic engine used by `bho`. It is installed locally on the host machine.

The software projects managed by `bho` are executed in Docker containers whenever possible. This isolates project dependencies and generated code from the host system.

## Initial architecture

```text
Host machine
├── bho
├── Hermes Agent
├── bho local state
└── Docker
    └── isolated project environments
```

The first version will use:

- Python for the `bho` CLI;
- Hermes Agent as the agentic engine;
- Git for version control;
- Docker for project isolation;
- SQLite for local application state;
- a configurable remote language model.

No workflow engine, Kubernetes cluster, message queue, vector database, or microservice architecture is required for the first version.

## Core concepts

### Hermes Agent

Hermes Agent is installed and managed by `bho`. It performs analysis, planning, coding, testing, documentation, and review tasks.

### Project

A project is a software codebase managed by `bho`.

A project can initially come from:

- an existing local directory;
- a Git repository;
- a new empty project created by `bho`.

Adding a project does not mean installing it directly on the host system. It means registering the project and preparing a controlled environment in which Hermes can work.

### Task

A task is a requested change to a project, such as:

- adding a feature;
- fixing a bug;
- creating tests;
- refactoring code;
- updating documentation.

Each task should have its own status, logs, plan, Git branch, test results, and final diff.

## Initial commands

The following commands define the first minimal interface. Their exact options may change during implementation.

### General commands

#### `bho version`

Show the installed version of `bho`.

#### `bho status`

Show a summary of the local installation, including Hermes, Docker, configured model, registered projects, and active tasks.

#### `bho doctor`

Check whether the required components are installed and correctly configured.

The command should verify at least:

- Python environment;
- Git;
- Docker;
- Hermes Agent;
- model provider configuration;
- access to registered projects;
- local database availability.

### Hermes commands

#### `bho hermes install`

Install Hermes Agent locally on the host machine using the official Hermes installer. The command runs the installer with `--skip-setup` and `--non-interactive`, so provider setup, gateway setup, messaging bridges, and systemd services are not started. Existing installations are not overwritten. The external installer is subject to a timeout and its final state is always reconciled.

The first version does not offer a Docker installation mode for Hermes.

#### `bho hermes uninstall`

Remove a recognized Hermes Agent installation by invoking the official Hermes uninstaller. The command requires confirmation unless `--yes` is used.

User data, sessions, memory, credentials, and configuration are preserved because `bho` never passes the destructive `--full` option. After uninstall, `bho hermes status` still reports whether the preserved Hermes data directory exists.

#### `bho hermes configure`

Configure Hermes Agent and the selected language model provider.

The command may be interactive and should avoid exposing API keys in logs.

#### `bho hermes status`

Show whether Hermes Agent is installed and whether configuration or user data is present. Installed systems report the executable, version, bho management state, installer source, and the installation method reported by Hermes.

#### `bho hermes update`

Update Hermes Agent to a supported version.

This command is not required for the first implementation, but it belongs to the initial CLI design.

### Project commands

#### `bho project add PATH`

Register an existing local software project.

Example:

```bash
bho project add /home/user/projects/weather-server
```

The command should:

- verify that the path exists;
- detect whether it is a Git repository;
- store the project in the local `bho` database;
- avoid changing project files without approval.

Optional explicit name:

```bash
bho project add /home/user/projects/weather-server --name weather-server
```

#### `bho project clone URL`

Clone and register a Git repository.

Example:

```bash
bho project clone https://github.com/example/weather-server.git
```

This command can be implemented after local project registration is stable.

#### `bho project create NAME`

Create and register a new software project.

Initially, this may create only an empty Git repository and basic project metadata. Project design and code generation will be added later.

#### `bho project list`

List all registered projects.

#### `bho project show PROJECT`

Show information about a registered project, including:

- local path;
- Git status;
- detected language;
- test command;
- Docker environment status;
- recent tasks.

#### `bho project remove PROJECT`

Remove a project from the `bho` registry.

By default, this command must not delete the original project files.

#### `bho project analyze PROJECT`

Ask Hermes to analyze the project and produce an initial project summary.

The summary should include:

- project purpose;
- languages and frameworks;
- main modules;
- setup procedure;
- test procedure;
- important architectural decisions;
- relevant risks or missing information.

This command can be added after the basic project registry is working.

### Task commands

#### `bho task create PROJECT`

Create a new task for a project.

The command should start an interactive description unless title and description are provided directly.

Example:

```bash
bho task create weather-server \
  --title "Add CSV export" \
  --description "Allow users to export weather results as CSV"
```

#### `bho task plan TASK_ID`

Ask Hermes to analyze the task and produce an implementation plan without modifying the code.

The plan should identify:

- affected components;
- proposed changes;
- tests to add or update;
- documentation changes;
- risks and assumptions.

#### `bho task run TASK_ID`

Execute an approved task.

Hermes should work on a dedicated Git branch and use the configured Docker project environment.

#### `bho task status TASK_ID`

Show the current task state.

Possible initial states:

```text
created
planning
waiting_for_approval
running
failed
completed
cancelled
```

#### `bho task logs TASK_ID`

Show the actions, commands, errors, and relevant Hermes output associated with a task.

#### `bho task cancel TASK_ID`

Stop a task that has not yet been accepted.

Cancellation must not silently delete useful logs or Git changes.

### Test commands

#### `bho test run PROJECT`

Run the configured test suite for a project in its isolated environment.

#### `bho test run-task TASK_ID`

Run the tests associated with a task and store the results.

The first version may implement only `bho test run PROJECT`.

### Git commands

#### `bho git diff TASK_ID`

Show the changes produced by a task.

#### `bho git commit TASK_ID`

Create a Git commit after the user has reviewed the diff and test results.

#### `bho git discard TASK_ID`

Discard the uncommitted changes produced by a task.

This command must require explicit confirmation.

A future version may add pull requests, merge operations, and remote Git hosting integration.

## Minimal workflow

The first useful workflow should be:

```bash
bho hermes install
bho hermes configure
bho project add /path/to/project
bho task create PROJECT
bho task plan TASK_ID
bho task run TASK_ID
bho test run PROJECT
bho git diff TASK_ID
bho git commit TASK_ID
```

## Design principles

- Keep the first version local and simple.
- Do not duplicate capabilities already provided by Hermes Agent.
- Keep `bho` project state independent from Hermes internal memory.
- Do not execute project code directly on the host when Docker isolation is available.
- Use Git branches for every task.
- Require explicit approval before destructive or irreversible operations.
- Prefer observable steps over hidden autonomous behavior.
- Add new infrastructure only when a real requirement appears.

## TODO

### Phase 1: CLI foundation

- [x] Create the Python package.
- [x] Define the `bho` console entry point.
- [x] Implement `bho version`.
- [ ] Implement global configuration paths.
- [ ] Add structured error handling.
- [ ] Add basic command logging.
- [x] Add automated tests for the CLI.

### Phase 2: Hermes management

- [x] Implement `bho hermes install`.
- [x] Detect an existing Hermes installation.
- [x] Store the installed Hermes version.
- [x] Implement `bho hermes status`.
- [ ] Implement `bho hermes configure`.
- [x] Implement `bho hermes uninstall`.
- [x] Preserve Hermes data by default during uninstall.
- [ ] Add `bho hermes update`.

### Phase 3: Project registry

- [ ] Create the local SQLite database.
- [ ] Implement `bho project add`.
- [ ] Implement `bho project list`.
- [ ] Implement `bho project show`.
- [ ] Implement `bho project remove`.
- [ ] Detect Git repositories.
- [ ] Detect basic project metadata.
- [ ] Add `bho project clone`.
- [ ] Add `bho project create`.

### Phase 4: Docker project environments

- [ ] Verify that Docker is available.
- [ ] Define the initial project container strategy.
- [ ] Mount only the required project directory.
- [ ] Prevent access to unrelated host directories.
- [ ] Implement project environment creation.
- [ ] Implement project environment cleanup.
- [ ] Store project-specific setup and test commands.

### Phase 5: Task lifecycle

- [ ] Implement task persistence.
- [ ] Implement `bho task create`.
- [ ] Implement task states.
- [ ] Implement `bho task plan`.
- [ ] Add human approval before execution.
- [ ] Implement `bho task run`.
- [ ] Implement `bho task status`.
- [ ] Implement `bho task logs`.
- [ ] Implement `bho task cancel`.

### Phase 6: Git integration

- [ ] Create a dedicated branch for each task.
- [ ] Store the base commit for each task.
- [ ] Implement `bho git diff`.
- [ ] Implement `bho git commit`.
- [ ] Implement `bho git discard`.
- [ ] Protect the main branch from direct agent changes.

### Phase 7: Tests and verification

- [ ] Implement `bho test run`.
- [ ] Store test commands per project.
- [ ] Store test results per task.
- [ ] Prevent commits when required tests fail.
- [ ] Add an independent review step.
- [ ] Separate test generation from implementation when needed.

### Phase 8: Project knowledge

- [ ] Implement `bho project analyze`.
- [ ] Store a concise project summary.
- [ ] Track the Git commit on which the summary is based.
- [ ] Refresh the summary after major changes.
- [ ] Store architectural decisions separately from conversational memory.

### Later, only if required

- [ ] GitHub integration.
- [ ] Pull request creation.
- [ ] GitHub Actions integration.
- [ ] Multiple users.
- [ ] Web interface.
- [ ] Remote workers.
- [ ] Hermes Docker installation mode.
- [ ] Multiple agent engines.
- [ ] Fully automatic bug intake.
- [ ] Automatic deployment.
