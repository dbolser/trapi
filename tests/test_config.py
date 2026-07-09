from pathlib import Path

import pytest

from trello_cli.config import load_credentials


@pytest.fixture
def clean_sources(monkeypatch, tmp_path):
    """No TRELLO_* in the environment, cwd and home pointed at tmp dirs."""
    monkeypatch.delenv("TRELLO_API_KEY", raising=False)
    monkeypatch.delenv("TRELLO_TOKEN", raising=False)
    cwd = tmp_path / "cwd"
    home = tmp_path / "home"
    cwd.mkdir()
    home.mkdir()
    monkeypatch.chdir(cwd)
    # Patch Path.home rather than $HOME: Windows resolves the home
    # directory from USERPROFILE, not HOME.
    monkeypatch.setattr(Path, "home", lambda: home)
    return cwd, home


def test_nothing_configured(clean_sources):
    assert load_credentials() is None


def test_environment_wins(clean_sources, monkeypatch):
    cwd, _ = clean_sources
    (cwd / ".env").write_text("TRELLO_API_KEY=filekey\nTRELLO_TOKEN=filetoken\n")
    monkeypatch.setenv("TRELLO_API_KEY", "envkey")
    monkeypatch.setenv("TRELLO_TOKEN", "envtoken")
    assert load_credentials() == ("envkey", "envtoken")


def test_cwd_dotenv(clean_sources):
    cwd, _ = clean_sources
    (cwd / ".env").write_text("TRELLO_API_KEY=k\nTRELLO_TOKEN=t\n")
    assert load_credentials() == ("k", "t")


def test_home_config_dotenv(clean_sources):
    _, home = clean_sources
    conf = home / ".config" / "trello-cli"
    conf.mkdir(parents=True)
    (conf / ".env").write_text("TRELLO_API_KEY=hk\nTRELLO_TOKEN=ht\n")
    assert load_credentials() == ("hk", "ht")


def test_sources_are_never_blended(clean_sources, monkeypatch):
    # Half a pair in the environment must not combine with the other half
    # from a file; the complete file pair should win instead.
    cwd, _ = clean_sources
    monkeypatch.setenv("TRELLO_API_KEY", "envkey")
    (cwd / ".env").write_text("TRELLO_API_KEY=filekey\nTRELLO_TOKEN=filetoken\n")
    assert load_credentials() == ("filekey", "filetoken")


def test_half_pair_alone_is_not_enough(clean_sources, monkeypatch):
    monkeypatch.setenv("TRELLO_TOKEN", "envtoken")
    assert load_credentials() is None
