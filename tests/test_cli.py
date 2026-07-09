import json

import pytest
from typer.testing import CliRunner

from trello_cli import __version__, main

from .conftest import make_client

runner = CliRunner()

BOARD_ID = "64a3ec34adca60eb1113f51e"
CARD_ID = "64a7c0e15889348bed680859"


@pytest.fixture
def fake_client(monkeypatch, recorder):
    """Point the CLI at a mock-transport client and return the recorder."""
    monkeypatch.setattr(main, "client", lambda: make_client(recorder))
    return recorder


def test_version():
    result = runner.invoke(main.app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_missing_credentials_exits_with_setup_help(monkeypatch):
    monkeypatch.setattr(main, "load_credentials", lambda: None)
    result = runner.invoke(main.app, ["board", "list"])
    assert result.exit_code == 1
    assert "Missing Trello credentials" in result.output


def test_card_edit_requires_a_change():
    result = runner.invoke(main.app, ["card", "edit", "abc123XY"])
    assert result.exit_code == 1
    assert "Nothing to change" in result.output


def test_card_edit_due_flags_conflict():
    result = runner.invoke(main.app, ["card", "edit", "abc123XY",
                                      "--due", "2026-08-01", "--clear-due"])
    assert result.exit_code == 1
    assert "mutually exclusive" in result.output


def test_card_label_requires_a_change():
    result = runner.invoke(main.app, ["card", "label", "abc123XY"])
    assert result.exit_code == 1
    assert "Nothing to change" in result.output


def test_label_list_renders_table(fake_client):
    fake_client.routes[f"/boards/{BOARD_ID}"] = {"id": BOARD_ID, "name": "B"}
    fake_client.routes[f"/boards/{BOARD_ID}/labels"] = [
        {"id": "a" * 24, "name": "Urgent", "color": "red"},
        {"id": "b" * 24, "name": "", "color": None},
    ]
    result = runner.invoke(main.app, ["label", "list", "-b", BOARD_ID])
    assert result.exit_code == 0
    assert "Urgent" in result.output
    assert "red" in result.output


def test_json_flag_emits_raw_json(fake_client):
    fake_client.routes["/members/me/boards"] = [
        {"name": "B", "shortLink": "IVCMk9Bo", "closed": False,
         "shortUrl": "https://trello.com/b/IVCMk9Bo"}]
    result = runner.invoke(main.app, ["--json", "board", "list"])
    assert result.exit_code == 0
    assert json.loads(result.output)[0]["shortLink"] == "IVCMk9Bo"


def test_card_label_add_and_remove_skips_noops(fake_client):
    urgent, bug = "a" * 24, "b" * 24
    fake_client.routes[f"/cards/{CARD_ID}"] = {
        "id": CARD_ID, "idBoard": BOARD_ID, "name": "My card",
        "idLabels": [urgent]}
    fake_client.routes[f"/boards/{BOARD_ID}/labels"] = [
        {"id": urgent, "name": "Urgent", "color": "red"},
        {"id": bug, "name": "Bug", "color": "green"},
    ]
    fake_client.routes[f"/cards/{CARD_ID}/idLabels"] = {}
    fake_client.routes[f"/cards/{CARD_ID}/idLabels/{urgent}"] = {}

    result = runner.invoke(main.app, ["card", "label", CARD_ID,
                                      "-a", "Bug", "-a", "Urgent", "-r", "Urgent"])
    assert result.exit_code == 0
    assert "added Bug" in result.output
    assert "removed Urgent" in result.output

    writes = [(r.method, r.url.path) for r in fake_client.requests
              if r.method in ("POST", "DELETE")]
    # 'Urgent' was already on the card, so only one POST (for Bug).
    assert writes == [("POST", f"/1/cards/{CARD_ID}/idLabels"),
                      ("DELETE", f"/1/cards/{CARD_ID}/idLabels/{urgent}")]


def test_card_label_bad_ref_fails_before_any_write(fake_client):
    fake_client.routes[f"/cards/{CARD_ID}"] = {
        "id": CARD_ID, "idBoard": BOARD_ID, "name": "My card", "idLabels": []}
    fake_client.routes[f"/boards/{BOARD_ID}/labels"] = [
        {"id": "a" * 24, "name": "Urgent", "color": "red"}]

    result = runner.invoke(main.app, ["card", "label", CARD_ID,
                                      "-a", "Urgent", "-a", "nope"])
    assert result.exit_code == 1
    assert "No label matching 'nope'" in result.output
    assert not [r for r in fake_client.requests if r.method != "GET"]
