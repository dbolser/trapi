import re
from typing import Any

import httpx

BASE_URL = "https://api.trello.com/1"


class TrelloError(Exception):
    """API or lookup error with a user-facing message."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class TrelloClient:
    def __init__(self, key: str, token: str):
        self._auth = {"key": key, "token": token}
        self._http = httpx.Client(base_url=BASE_URL, timeout=30)

    def request(self, method: str, path: str, **params: Any) -> Any:
        clean = {k: v for k, v in params.items() if v is not None}
        # Write payloads go in the body: long values (card descriptions,
        # comments) would exceed URL length limits as query params.
        if method in ("POST", "PUT"):
            kwargs: dict[str, Any] = {"params": self._auth, "data": clean}
        else:
            kwargs = {"params": {**self._auth, **clean}}
        try:
            resp = self._http.request(method, path, **kwargs)
        except httpx.RequestError as e:
            raise TrelloError(f"{method} {path}: {e}") from e
        if resp.status_code == 401:
            raise TrelloError(
                f"Unauthorized ({resp.text.strip()}). "
                "Check TRELLO_API_KEY / TRELLO_TOKEN — see 'trello auth status'.",
                status=401,
            )
        if resp.is_error:
            raise TrelloError(f"{method} {path}: HTTP {resp.status_code} — {resp.text.strip()}",
                              status=resp.status_code)
        return resp.json()

    def get(self, path: str, **params: Any) -> Any:
        return self.request("GET", path, **params)

    def post(self, path: str, **params: Any) -> Any:
        return self.request("POST", path, **params)

    def put(self, path: str, **params: Any) -> Any:
        return self.request("PUT", path, **params)

    # -- name-or-id resolution -------------------------------------------

    def resolve_board(self, ref: str) -> dict:
        """Accept a board id, shortLink, or (partial) name.

        Ids and shortLinks resolve directly (works for archived boards too);
        names match against open boards only.
        """
        if re.fullmatch(r"[0-9a-fA-F]{24}|[A-Za-z0-9]{8}", ref):
            board = self._try_get(f"/boards/{ref}", "name,shortLink,closed,url")
            if board:
                return board
        boards = self.get("/members/me/boards", filter="open",
                          fields="name,shortLink,closed,url")
        return match_ref(ref, boards, "board")

    def resolve_list(self, board_id: str, ref: str) -> dict:
        """Accept a list id or (partial) name within a board.

        Ids resolve directly (works for archived lists too); names match
        against the board's open lists.
        """
        if re.fullmatch(r"[0-9a-fA-F]{24}", ref):
            lst = self._try_get(f"/lists/{ref}", "name")
            if lst:
                return lst
        lists = self.get(f"/boards/{board_id}/lists", fields="name")
        return match_ref(ref, lists, "list")

    def _try_get(self, path: str, fields: str) -> dict | None:
        try:
            return self.get(path, fields=fields)
        except TrelloError as e:
            # Only "not a real id" outcomes fall back to name matching;
            # auth and transport failures should surface immediately.
            if e.status in (400, 404):
                return None
            raise


def match_ref(ref: str, items: list[dict], kind: str) -> dict:
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
