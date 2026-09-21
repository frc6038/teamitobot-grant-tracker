"""
Ana modüllerin hatasız import edildiğini doğrulayan duman testleri
"""

import importlib
import os


def test_config_imports():
    config_module = importlib.import_module("config")

    assert os.environ["ENVIRONMENT"] == "test"
    assert config_module.config.BOT_TOKEN == "123456789:dummy-token"
    assert config_module.config.DATABASE_URL.endswith(
        "@database.invalid:5432/itobot_test"
    )


def test_database_imports():
    importlib.import_module("database")


def test_scraper_imports():
    importlib.import_module("scraper")


def test_bot_imports():
    importlib.import_module("bot")
