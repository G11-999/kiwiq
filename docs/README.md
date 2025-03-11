# Monorepo setup

## Repository Structure

```text
.
├── services/      # Microservices
├── libs/         # Shared libraries
├── infra/        # Infrastructure code
├── scripts/      # Utility scripts
├── libs/db/      # database
├── docs/         # Documentation
└── tests/        # Common test utilities
```

## Python version
- We use Python 3.12 since airflow supports that version, and not 3.13 for now


## Production build for packages with poetry
TODO: `poetry build`


## Installation

1. Install Poetry:

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

2. Install dependencies:

```bash
poetry install
```

## Local Libs (X-service dependencies)

1. Within `libs` folder in project root, create a `pyproject.toml` file including all packages within `libs`. All packages must be in `libs/src`!

*libs/pyproject.toml*
```ini
[tool.poetry]
name = "libs"
version = "0.1.0"
description = "Central package for all local libraries"
# No need to define a single package; you list multiple subpackages.

packages = [
    { include = "global_config", from = "src" },
    # ... Other libs!
]
```

2. In central poetry environment which is shared throughout the project, add libs as such:

*pyproject.toml*
```ini
[tool.poetry.dependencies]
# ... other 3rd party libs

# Include local libraries as editable dependencies
libs = { path = "./libs", develop = true }
```

3. `poetry install` to install added local deps

4. With above steps, you can directly import your libs. VS code may have trouble resolving paths during linting, for that include the following in your .env file for VS code to recognize `libs` imports:

```bash
PYTHONPATH=./libs
```

Also ensure the following setting in your VS code settings: (it should be there by default)

```json
{
  "python.envFile": "${workspaceFolder}/.env"
}
```

## DB
