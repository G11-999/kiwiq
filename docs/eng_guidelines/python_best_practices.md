# IDE

- **IDE:** Use **Cursor AI IDE (preferred)** or **VS Code with GitHub Copilot** (both in privacy mode) for enhanced productivity and code suggestions while maintaining security.
    - use some of these prompt instructions in IDE as system prompt so the outputed code is good quality and compliant out of the box
    - eg **IDE System prompt**:
    
    ```python
    Write python with typed objects and typing lib
    Comment in the code extensively explaining steps while also document caveats, watch outs and key design decisions in code.
    Always use detailed docstrings.
    Write easy to read, clear, crisp, pythonic code.  
    ```
    

## General coding Principles

- Follow **PEP 8** as the baseline style guide. Use linters like `flake8` and
    - auto-formatters like `black` or `isort` to enforce consistent coding standards.
- Keep the code **readable, modular, and maintainable**.
- Use **meaningful names** for variables, functions, and classes.
- Stick to **consistent formatting** (e.g., indentation, spacing, and line lengths).
- Document code properly using **docstrings and comments** where necessary.
- Use **type hints: typing library for each variable (including functions and classes)** to improve code clarity and maintainability.

---

## Project MonoRepo Structure

```
# Monorepo structure
monorepo/
├── library-one/
│   └── library_one/
├── library-two/
│   └── library_two/
├── service-one/            # Note: diff between libraries and services ->       # services are expected to run by themselves, using
│   └── service-one/        #   libraries as dependencies; other services
├── poetry.lock             #   shoudn't use a service as a dependency
├── pyproject.toml
│── README.md
│── .gitignore
└── docs/                   # Central monorepo Docs

# Each project / library structure
monorepo/
|──	library-one/
|		│── library-one/
|		│   ├── my_package/
|		│   │   ├── __init__.py
|		│   │   ├── module_a.py
|		│   │   └── module_b.py
|		│   |── config/
|		|   |   ├── settings.py
|		│   │   └── logging_config.py
|		│   └── main.py
|		│── tests/
|		│   ├── test_module_a.py
|		│   └── test_module_b.py
|		│── README.md
|		└── docs/                   # Project Docs (Optionally, have all docs
...                                 #    in once place centrally above)
```

- **Separate concerns:** Divide the code into modules and packages based on functionality.
- **Configuration in one place:** Use `settings.py` for managing configurations.
- **Keep main.py clean:** The entry point (`main.py`) should only be responsible for initializing and starting the application.
- **Use a logging configuration file:** Avoid print statements and use proper logging instead.

---

## Dependency Management

- Setup **virtual environments ( `poetry`)** and maintain dependencies using that.
    
    ```bash
    curl -sSL https://install.python-poetry.org | python3 -
    ```
    
- Install your module in editable mode via poetry so you can import it anywhere in code
    - `[tool.poetry]
    packages = [{include = "*", from="src"}]`
- Use latest python version: `3.13.1`
- Regularly **update dependencies** to patch security issues.

## Settings & Configurations

```python
# settings.py
import os

class Settings:
    DEBUG = os.getenv("DEBUG", False)
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///default.db")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

settings = Settings()

```

- **Use environment variables** instead of hardcoded values.
- **Keep secrets out of the codebase** (use `.env` files and `dotenv` package to load them in code).
- **Encapsulate settings in a class** to maintain organization and prevent accidental changes.

## Python Security Best Practices

- Use `dotenv` package and a project repo `.env` file to manage secrets via environment variables autoloaded in your code
- **Use environment variables** for sensitive data. NEVER push api keys or sensitive data like username / password to code repo.

---

## Object-Oriented Design (Class-Based Inheritance)

```python
class BaseService:
    def __init__(self, name):
        self.name = name

    def process(self):
        raise NotImplementedError("Subclasses must implement this method")

class UserService(BaseService):
    def process(self):
        print(f"Processing user service for {self.name}")

service = UserService("Alice")
service.process()

```

- **Use inheritance wisely:** Only when there’s a clear hierarchical relationship.
- **Prefer composition over inheritance** when possible. (Read more on chatgpt)
- **Encapsulate shared functionality in base classes** to avoid code duplication.

---

## Modular Code

```python
# modules/math_operations.py

def add(a: int, b: int) -> int:
    return a + b

def subtract(a: int, b: int) -> int:
    return a - b

# main.py
from modules.math_operations import add, subtract

result = add(10, 5)
print(result)

```

- **Keep functions and classes small.** A function should ideally do one thing well.
- **Follow the single-responsibility principle (SRP).**
- **Organize related functionalities into separate modules.**
- **Use `__init__.py` to organize modules into packages.**

---

## Exception Handling

```python
try:
    result = 10 / 0
except ZeroDivisionError as e:
    print(f"Error: {e}")
finally:
    print("Execution completed.")

```

- **Catch specific exceptions** instead of using a generic `except`.
- **Log errors** instead of printing them.
- **Use `finally` for cleanup actions** (e.g., closing files or database connections).

---

## Logging Best Practices

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.info("Application started")

```

- **Avoid print statements.** Use logging instead.
- **Set different log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL).**
- **Log errors with stack traces (`exc_info=True`).**

---

## Testing

- Use **pytest** for unit tests.
- Follow the **AAA (Arrange, Act, Assert)** testing pattern.
- Maintain **test coverage above 80%**.

Example:

```python
import pytest
from modules.math_operations import add

def test_add():
    assert add(2, 3) == 5

```

Run tests with:

```
pytest tests/

```

---

## GIT: Code Reviews & Collaboration

- Use **Git with feature branches** (`feature/new-feature`, `fix/bug-name`).
- Require **code reviews (PR-based development)**.
    - Never commit to `main` branch directly
    - ping in `waiting-pr` slack channel for code review and resolve comments before merging and merge after LGTM (looks good to me)
- Follow **conventional commit messages** (e.g., `feat: add new login method`).
- Use **pre-commit hooks** to enforce linting and formatting.
- use .gitignore file (default below)

[.gitignore](https://www.notion.so/gitignore-19112cba067e81f89c42f9b9f3d1dbeb?pvs=21)

---

##
