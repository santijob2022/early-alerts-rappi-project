"""Unit tests for app/agent/context_source.py."""
from __future__ import annotations

import pytest

from app.agent.context_source import ContextSourceService
from tests.conftest import DOCS_CONTENT, RULES_CONTENT


class TestContextSourceService:
    def test_loads_rules_content(self, test_settings):
        svc = ContextSourceService(test_settings)
        assert RULES_CONTENT in svc.get_motor_context()

    def test_loads_docs_content(self, test_settings):
        svc = ContextSourceService(test_settings)
        assert DOCS_CONTENT in svc.get_motor_context()

    def test_combined_output_has_separator(self, test_settings):
        svc = ContextSourceService(test_settings)
        ctx = svc.get_motor_context()
        assert "\n\n---\n\n" in ctx

    def test_rules_appear_before_docs(self, test_settings):
        svc = ContextSourceService(test_settings)
        ctx = svc.get_motor_context()
        rules_pos = ctx.index("Motor Reglas")
        docs_pos = ctx.index("Documentacion Motor")
        assert rules_pos < docs_pos

    def test_missing_rules_file_raises(self, motor_files, test_settings):
        rules, _ = motor_files
        rules.unlink()
        with pytest.raises(FileNotFoundError):
            ContextSourceService(test_settings)

    def test_missing_docs_file_raises(self, motor_files, test_settings):
        _, docs = motor_files
        docs.unlink()
        with pytest.raises(FileNotFoundError):
            ContextSourceService(test_settings)

    def test_reload_picks_up_updated_rules(self, motor_files, test_settings):
        rules, _ = motor_files
        svc = ContextSourceService(test_settings)
        rules.write_text("UPDATED_RULES_CONTENT", encoding="utf-8")
        svc.reload()
        assert "UPDATED_RULES_CONTENT" in svc.get_motor_context()

    def test_reload_picks_up_updated_docs(self, motor_files, test_settings):
        _, docs = motor_files
        svc = ContextSourceService(test_settings)
        docs.write_text("UPDATED_DOCS_CONTENT", encoding="utf-8")
        svc.reload()
        assert "UPDATED_DOCS_CONTENT" in svc.get_motor_context()

    def test_get_motor_context_returns_string(self, test_settings):
        svc = ContextSourceService(test_settings)
        assert isinstance(svc.get_motor_context(), str)

    def test_get_motor_context_non_empty(self, test_settings):
        svc = ContextSourceService(test_settings)
        assert len(svc.get_motor_context()) > 0
