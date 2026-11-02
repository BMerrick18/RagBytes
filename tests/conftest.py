import pytest

from ragbytes.config import settings


@pytest.fixture(autouse=True)
def _stats_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "stats_path", str(tmp_path / "stats.db"))
