import pytest

from trello_cli.api import TrelloError, match_ref

ITEMS = [
    {"id": "64a3ec34adca60eb1113f51e", "shortLink": "IVCMk9Bo", "name": "Alpha"},
    {"id": "64a3ec34adca60eb1113f51f", "shortLink": "YySs8goi", "name": "Alpha Two"},
    {"id": "64a3ec34adca60eb1113f520", "shortLink": "OADXTcpZ", "name": "Beta"},
]


def test_matches_by_id():
    assert match_ref("64a3ec34adca60eb1113f520", ITEMS, "board")["name"] == "Beta"


def test_matches_by_shortlink():
    assert match_ref("YySs8goi", ITEMS, "board")["name"] == "Alpha Two"


def test_exact_name_beats_partial_matches():
    # "Alpha" is exact for one item and partial for another.
    assert match_ref("alpha", ITEMS, "board")["name"] == "Alpha"


def test_unique_partial_name():
    assert match_ref("bet", ITEMS, "board")["name"] == "Beta"


def test_ambiguous_partial_name():
    with pytest.raises(TrelloError, match="Ambiguous board 'alph'"):
        match_ref("alph", ITEMS, "board")


def test_no_match():
    with pytest.raises(TrelloError, match="No list matching 'gamma'"):
        match_ref("gamma", ITEMS, "list")


def test_empty_ref_rejected():
    with pytest.raises(TrelloError, match="Empty label reference"):
        match_ref("", [{"id": "x", "name": ""}], "label")


def test_tolerates_null_and_empty_names():
    items = [{"id": "a" * 24, "name": None}, {"id": "b" * 24, "name": ""},
             {"id": "c" * 24, "name": "Real"}]
    assert match_ref("real", items, "label")["id"] == "c" * 24
