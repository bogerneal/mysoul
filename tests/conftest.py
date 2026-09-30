import pytest

from weather.demo import load_demo_document


@pytest.fixture
def document():
    return load_demo_document()
