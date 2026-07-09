import httpx
import pytest

from trello_cli.api import TrelloError

from .conftest import json_response, make_client

BOARD_ID = "64a3ec34adca60eb1113f51e"


# -- request plumbing -----------------------------------------------------

def test_get_sends_auth_and_params_in_query(recorder):
    recorder.routes["/members/me"] = {"ok": True}
    make_client(recorder).get("/members/me", fields="name", skip=None)
    params = dict(recorder.requests[0].url.params)
    assert params == {"key": "test-key", "token": "test-token", "fields": "name"}


def test_post_sends_payload_in_body_and_auth_in_query(recorder):
    recorder.routes["/cards"] = {"ok": True}
    make_client(recorder).post("/cards", name="hi there", desc=None)
    req = recorder.requests[0]
    assert dict(req.url.params) == {"key": "test-key", "token": "test-token"}
    assert req.content == b"name=hi+there"


def test_401_maps_to_credentials_hint():
    client = make_client(lambda req: httpx.Response(401, text="invalid token"))
    with pytest.raises(TrelloError, match="invalid token.*TRELLO_API_KEY"):
        client.get("/members/me")


def test_http_error_includes_status_and_body():
    client = make_client(lambda req: httpx.Response(429, text="rate limited"))
    with pytest.raises(TrelloError, match="HTTP 429 — rate limited") as exc:
        client.get("/members/me")
    assert exc.value.status == 429


def test_transport_error_maps_to_trello_error():
    def boom(request):
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(TrelloError, match="GET /members/me: connection refused"):
        make_client(boom).get("/members/me")


# -- resolve_board / resolve_list ----------------------------------------

def test_resolve_board_by_id_hits_board_directly(recorder):
    recorder.routes[f"/boards/{BOARD_ID}"] = {"id": BOARD_ID, "name": "Mine"}
    board = make_client(recorder).resolve_board(BOARD_ID)
    assert board["name"] == "Mine"
    assert len(recorder.requests) == 1


def test_resolve_board_falls_back_to_name_listing(recorder):
    # Looks like a shortLink, but the direct fetch 404s -> match by name.
    recorder.routes["/members/me/boards"] = [
        {"id": BOARD_ID, "shortLink": "IVCMk9Bo", "name": "Projects"}]
    board = make_client(recorder).resolve_board("Projects")
    assert board["id"] == BOARD_ID


def test_resolve_board_direct_fetch_500_is_not_swallowed():
    client = make_client(lambda req: httpx.Response(500, text="oops"))
    with pytest.raises(TrelloError, match="HTTP 500"):
        client.resolve_board(BOARD_ID)


def test_resolve_list_by_name(recorder):
    recorder.routes[f"/boards/{BOARD_ID}/lists"] = [
        {"id": "a" * 24, "name": "To Do"}, {"id": "b" * 24, "name": "Done"}]
    lst = make_client(recorder).resolve_list(BOARD_ID, "done")
    assert lst["id"] == "b" * 24


# -- resolve_label --------------------------------------------------------

LABELS = [
    {"id": "a" * 24, "name": "Urgent", "color": "red"},
    {"id": "b" * 24, "name": "", "color": "green"},
    {"id": "c" * 24, "name": "", "color": "red"},
]


def label_client(recorder):
    recorder.routes[f"/boards/{BOARD_ID}/labels"] = LABELS
    return make_client(recorder)


def test_resolve_label_by_name(recorder):
    assert label_client(recorder).resolve_label(BOARD_ID, "urgent")["id"] == "a" * 24


def test_resolve_label_by_unique_color(recorder):
    assert label_client(recorder).resolve_label(BOARD_ID, "green")["id"] == "b" * 24


def test_resolve_label_ambiguous_color(recorder):
    with pytest.raises(TrelloError, match="Ambiguous label 'red' — matches by color"):
        label_client(recorder).resolve_label(BOARD_ID, "red")


def test_resolve_label_name_beats_color(recorder):
    # 'urgent' names the red label; color matching never enters into it.
    recorder.routes[f"/boards/{BOARD_ID}/labels"] = LABELS
    label = make_client(recorder).resolve_label(BOARD_ID, "Urgent")
    assert label["color"] == "red"


def test_resolve_label_no_match(recorder):
    with pytest.raises(TrelloError, match="No label matching 'blue'"):
        label_client(recorder).resolve_label(BOARD_ID, "blue")
