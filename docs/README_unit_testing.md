# BaseSchema Tests

This directory contains unit tests for the `BaseSchema` class and its implementations. The tests cover basic functionality, nested schemas, field types and modifiers, and various edge cases.

## Test Files

- `test_base.py`: Tests for basic functionality of the `BaseSchema` class
- `test_example_schemas.py`: Tests for example schemas defined in `base.py`
- `test_edge_cases.py`: Tests for edge cases and complex scenarios

## Running Tests

The tests use pytest for test execution. You can run the tests in several ways:

1. Run all tests:
```bash
PYTHONPATH=.:./services pytest
```

2. Run tests with verbose output:
```bash
PYTHONPATH=.:./services pytest -v
```

3. Run a specific test file:
```bash
PYTHONPATH=.:./services pytest test_base.py
```

4. Run a specific test function:
```bash
PYTHONPATH=.:./services pytest test_base.py::test_simple_schema_instantiation
```

5. Run tests with coverage report:
```bash
PYTHONPATH=.:./services pytest --cov=services.workflow_service.registry.schemas.base
```

## Test Coverage

The tests cover the following aspects:

1. Basic Functionality
   - Schema instantiation
   - Field validation
   - Default values
   - Optional fields
   - Extra fields handling

2. Schema Metadata
   - Field types
   - Default values
   - Deprecated fields
   - User editable fields
   - Field exclusions

3. Nested Schemas
   - Simple nesting
   - Deep nesting
   - Optional nested fields
   - Recursive references

4. Field Types and Modifiers
   - Basic types (str, int, bool)
   - Complex types (Enum, Union, Literal)
   - Date and time fields
   - Lists and dictionaries
   - SkipJsonSchema fields
   - Field validators
   - Model validators

5. Edge Cases
   - Empty schemas
   - All optional fields
   - Circular dependencies
   - Default factories
   - Nested SkipJsonSchema
   - Complex type validation
   - Schema differences

## Adding New Tests

When adding new tests:

1. Create test functions with descriptive names prefixed with `test_`
2. Use pytest fixtures when appropriate for test setup
3. Write clear docstrings explaining the test purpose
4. Use assertions to verify expected behavior
5. Test both valid and invalid cases
6. Test edge cases and error conditions
7. Keep test files organized by functionality
8. Follow the existing test structure and naming conventions

## Test Organization

The tests are organized into three main files:

1. `test_base.py`: Core functionality tests
   - Basic schema operations
   - Field validation
   - Schema metadata
   - JSON operations

2. `test_example_schemas.py`: Example schema tests
   - TestSchema and variants
   - Nested schema relationships
   - User editable fields
   - Schema differences

3. `test_edge_cases.py`: Edge case tests
   - Complex field types
   - Validators
   - Empty schemas
   - Optional fields
   - Circular dependencies
   - Default factories
   - Nested SkipJsonSchema 
