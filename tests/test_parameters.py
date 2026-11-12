import pytest
from pydantic import ValidationError

from src.model.parameters import Parameters


def test_valid_parameters():
    p = Parameters(accuracy=1e-6, max_iterations=100)
    assert (p.accuracy, p.max_iterations) == (1e-6, 100)


@pytest.mark.parametrize("accuracy", [0, -1e-6, 1_000_001])
def test_invalid_accuracy(accuracy):
    with pytest.raises(ValidationError):
        Parameters(accuracy=accuracy, max_iterations=10)


@pytest.mark.parametrize("max_iterations", [0, -1, 1_000_001, 1.5])
def test_invalid_max_iterations(max_iterations):
    with pytest.raises(ValidationError):
        Parameters(accuracy=1e-6, max_iterations=max_iterations)


def test_boundary_values_are_allowed():
    assert Parameters(accuracy=1_000_000, max_iterations=1_000_000).accuracy == 1_000_000

def test_damping_default():
    assert Parameters(accuracy=1e-6, max_iterations=10).damping == 1.0
