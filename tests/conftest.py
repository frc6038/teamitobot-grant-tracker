"""
Test ortamı için gerekli environment değişkenlerini sağlar
"""

import os

import pytest

from tests.fakes.telegram_fakes import FakeApplication, FakeContext, FakeUpdate

# These values intentionally replace ambient credentials before application imports.
# The reserved .invalid host cannot resolve to a production or staging database.
os.environ["TELEGRAM_BOT_TOKEN"] = "123456789:dummy-token"
os.environ["DATABASE_URL"] = "postgresql://test:test@database.invalid:5432/itobot_test"
os.environ["ENVIRONMENT"] = "test"


@pytest.fixture
def fake_update():
    """Fixture for creating fake Telegram Update objects"""

    def _create_update(chat_id=123, username="testuser", text=None):
        return FakeUpdate(chat_id=chat_id, username=username, text=text)

    return _create_update


@pytest.fixture
def fake_context():
    """Fixture for creating fake Telegram Context objects"""
    return FakeContext()


@pytest.fixture
def fake_application():
    """Fixture for creating fake Telegram Application objects"""
    return FakeApplication()
