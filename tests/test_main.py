"""Tests for main.py startup logging."""

import logging
from unittest.mock import patch

from secondbrain.main import app, lifespan


class TestStartupLogging:
    async def test_logs_vault_path_on_startup(self, tmp_path, caplog):
        with (
            caplog.at_level(logging.INFO, logger="secondbrain.main"),
            patch("secondbrain.main.get_settings") as mock_settings,
        ):
            mock_settings.return_value.vault_path = tmp_path
            mock_settings.return_value.data_path = tmp_path / "data"

            async with lifespan(app):
                pass

        assert "SecondBrain starting" in caplog.text
        assert str(tmp_path) in caplog.text

    async def test_logs_error_when_vault_none(self, caplog, tmp_path):
        with (
            caplog.at_level(logging.ERROR, logger="secondbrain.main"),
            patch("secondbrain.main.get_settings") as mock_settings,
        ):
            mock_settings.return_value.vault_path = None
            mock_settings.return_value.data_path = tmp_path / "data"

            async with lifespan(app):
                pass

        assert "VAULT PATH NOT CONFIGURED" in caplog.text

    async def test_logs_error_when_vault_nonexistent(self, caplog, tmp_path):
        fake_path = tmp_path / "does_not_exist"
        with (
            caplog.at_level(logging.ERROR, logger="secondbrain.main"),
            patch("secondbrain.main.get_settings") as mock_settings,
        ):
            mock_settings.return_value.vault_path = fake_path
            mock_settings.return_value.data_path = tmp_path / "data"

            async with lifespan(app):
                pass

        assert "VAULT PATH NOT CONFIGURED" in caplog.text
