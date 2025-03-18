import os
import pytest

# Get the absolute path of the directory containing this conftest.py
current_dir = os.path.dirname(os.path.abspath(__file__))

def pytest_collection_modifyitems(session, config, items):
    for item in items:
        # Get the absolute path of the test file
        item_path = os.path.abspath(str(item.fspath))
        # If the test file is within the same directory as this conftest.py, mark it
        if item_path.startswith(current_dir):
            item.add_marker(pytest.mark.unit)

