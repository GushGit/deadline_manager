from zoneinfo import ZoneInfo

import pytest

import config


def test_require_token_empty_exits(monkeypatch, capsys):
    monkeypatch.setattr(config, "BOT_TOKEN", "")
    with pytest.raises(SystemExit) as exc:
        config.require_token()
    assert exc.value.code == 1
    assert "BOT_TOKEN" in capsys.readouterr().out


def test_require_token_whitespace_exits(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "   ")
    with pytest.raises(SystemExit) as exc:
        config.require_token()
    assert exc.value.code == 1


def test_require_token_returns_token(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", " 123:abc ")
    assert config.require_token() == "123:abc"


def test_constants_match_spec():
    assert config.CHECK_INTERVAL_SECONDS == 30
    assert config.EXPIRE_INTERVAL_SECONDS == 300
    assert config.MAX_TITLE_LENGTH == 100
    assert config.MAX_ACTIVE_TASKS == 50
    assert config.MAX_DEADLINE_DAYS == 730
    assert config.LATE_REMINDER_MINUTES == 5
    assert config.LIST_PAGE_SIZE == 10
    assert config.SEND_PAUSE_SECONDS == 0.05
    assert config.DEFAULT_TIMEZONE == "Europe/Moscow"


def test_offset_presets():
    assert set(config.OFFSET_PRESETS) == {"d1h1", "d3d1h1", "h1", "d1"}
    assert config.OFFSET_PRESETS["d1h1"][0] == (1440, 60)
    for minutes, label in config.OFFSET_PRESETS.values():
        assert minutes and all(isinstance(m, int) and m > 0 for m in minutes)
        assert label


def test_popular_timezones_are_valid():
    assert len(config.POPULAR_TIMEZONES) == 10
    for label, iana in config.POPULAR_TIMEZONES.items():
        assert label
        assert ZoneInfo(iana).key == iana