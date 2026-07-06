from typing import Any

import httpx

BASE_URL = "https://api.trello.com/1"


class TrelloError(Exception):
    """API or lookup error with a user-facing message."""


class TrelloClient:
    def __init__(self, key: str, token: str):
        self._auth = {"key": key, "token": token}
        self._http = httpx.Client(base_url=BASE_URL, timeout=30)

    def request(self, method: str, path: str, **params: Any) -> Any:
        clean = {k: v for k, v in params.items() if v is not None}
        resp = self._http.request(method, path, params={**self._auth, **clean})
        if resp.status_code == 401:
            raise TrelloError(
                f"Unauthorized ({resp.text.strip()}). "
                "Check TRELLO_API_KEY / TRELLO_TOKEN — see 'trello auth status'."
            )
        if resp.is_error:
            raise TrelloError(f"{method} {path}: HTTP {resp.status_code} — {resp.text.strip()}")
        return resp.json()

    def get(self, path: str, **params: Any) -> Any:
        return self.request("GET", path, **params)

    def post(self, path: str, **params: Any) -> Any:
        return self.request("POST", path, **params)

    def put(self, path: str, **params: Any) -> Any:
        return self.request("PUT", path, **params)

    # -- name-or-id resolution -------------------------------------------

    def resolve_board(self, ref: str) -> dict:
        """Accept a board id, shortLink, or (partial) name."""
        boards = self.get("/members/me/boards", filter="all",
                          fields="name,shortLink,closed,url")
        return _match(ref, boards, "board")

    def resolve_list(self, board_id: str, ref: str) -> dict:
        """Accept a list id or (partial) name within a board."""
        lists = self.get(f"/boards/{board_id}/lists", fields="name")
        return _match(ref, lists, "list")


def _match(ref: str, items: list[dict], kind: str) -> dict:
    for item in items:
        if ref in (item["id"], item.get("shortLink")):
            return item
    exact = [i for i in items if i["name"].lower() == ref.lower()]
    if len(exact) == 1:
        return exact[0]
    partial = [i for i in items if ref.lower() in i["name"].lower()]
    if len(partial) == 1:
        return partial[0]
    if not exact and not partial:
        raise TrelloError(f"No {kind} matching '{ref}'.")
    names = ", ".join(f"'{i['name']}'" for i in (exact or partial)[:8])
    raise TrelloError(f"Ambiguous {kind} '{ref}' — matches: {names}")
