import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from models import ValidationError, validate_request  # noqa: E402

VALID_REQUEST = {
    "name": "demo-vnet",
    "addressSpace": ["10.0.0.0/16"],
    "subnets": [
        {"name": "web", "addressPrefix": "10.0.1.0/24"},
        {"name": "db", "addressPrefix": "10.0.2.0/24"},
    ],
}


def test_valid():
    assert validate_request(VALID_REQUEST)["name"] == "demo-vnet"


def test_outside_space():
    invalid_request = {
        **VALID_REQUEST,
        "subnets": [{"name": "x", "addressPrefix": "192.168.0.0/24"}],
    }
    with pytest.raises(ValidationError):
        validate_request(invalid_request)


def test_overlap():
    invalid_request = {
        **VALID_REQUEST,
        "subnets": [
            {"name": "a", "addressPrefix": "10.0.1.0/24"},
            {"name": "b", "addressPrefix": "10.0.1.0/25"},
        ],
    }
    with pytest.raises(ValidationError):
        validate_request(invalid_request)
