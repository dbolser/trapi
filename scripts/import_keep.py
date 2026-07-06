#!/usr/bin/env python3
"""Import a Google Takeout Keep dump into a Trello board.

Usage: python scripts/import_keep.py path/to/Takeout/Keep [--board "Keep import"] [--dry-run]

Mapping:
  note title/first line  -> card name
  text                   -> card description (+ edited-date footer)
  pinned                 -> "Pinned" list, otherwise "Notes"
  archived               -> card is created, then archived
  trashed                -> skipped
  Keep labels            -> Trello labels (created on the board as needed)
  checklist items        -> one Trello checklist, checked state preserved
  image attachments      -> uploaded to the card

Re-runnable: notes whose card name already exists on the board are skipped.
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from trello_cli.api import BASE_URL, TrelloClient, TrelloError  # noqa: E402
from trello_cli.config import SETUP_HELP, load_credentials  # noqa: E402

LABEL_COLORS = ["green", "yellow", "orange", "red", "purple",
                "blue", "sky", "lime", "pink", "black"]
DESC_LIMIT = 16384


def with_retry(fn, *args, **kwargs):
    """Run an API call, waiting out a 429 rate limit once."""
    try:
        return fn(*args, **kwargs)
    except TrelloError as e:
        if e.status == 429:
            time.sleep(10)
            return fn(*args, **kwargs)
        raise


def card_name(note: dict) -> str:
    if note.get("title"):
        return note["title"][:120]
    text = note.get("textContent") or ""
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    if first:
        return first[:120]
    items = note.get("listContent") or []
    if items:
        return items[0]["text"][:120] or "Untitled checklist"
    return "Untitled note"


def note_desc(note: dict) -> str:
    text = note.get("textContent") or ""
    usec = note.get("userEditedTimestampUsec")
    footer = "\n\n---\n*Imported from Google Keep*"
    if usec:
        edited = datetime.fromtimestamp(usec / 1e6, tz=timezone.utc).date()
        footer = f"\n\n---\n*Imported from Google Keep · edited {edited}*"
    if len(text) + len(footer) > DESC_LIMIT:
        text = text[: DESC_LIMIT - len(footer) - 15] + "\n[truncated]"
    return text + footer


def ensure_board(c: TrelloClient, name: str, dry: bool) -> dict:
    boards = c.get("/members/me/boards", filter="open", fields="name,shortUrl")
    for b in boards:
        if b["name"] == name:
            return b
    if dry:
        print(f"[dry-run] would create board '{name}'")
        return {"id": "DRY", "name": name}
    print(f"Creating board '{name}'")
    return c.post("/boards", name=name, defaultLists="false")


def ensure_list(c: TrelloClient, board_id: str, name: str,
                cache: dict, dry: bool) -> str:
    if name in cache:
        return cache[name]
    if dry:
        print(f"[dry-run] would create list '{name}'")
        cache[name] = "DRY"
        return "DRY"
    lst = c.post("/lists", name=name, idBoard=board_id, pos="bottom")
    cache[name] = lst["id"]
    return lst["id"]


def ensure_label(c: TrelloClient, board_id: str, name: str,
                 cache: dict, dry: bool) -> str:
    if name in cache:
        return cache[name]
    color = LABEL_COLORS[len(cache) % len(LABEL_COLORS)]
    if dry:
        print(f"[dry-run] would create label '{name}' ({color})")
        cache[name] = "DRY"
        return "DRY"
    lab = c.post("/labels", name=name, color=color, idBoard=board_id)
    cache[name] = lab["id"]
    return lab["id"]


def upload_attachment(c: TrelloClient, card_id: str, path: Path):
    with open(path, "rb") as fh:
        resp = c._http.post(f"{BASE_URL}/cards/{card_id}/attachments",
                            params=c._auth, files={"file": (path.name, fh)})
    if resp.is_error:
        raise TrelloError(f"attachment upload: HTTP {resp.status_code}",
                          status=resp.status_code)


def import_note(c: TrelloClient, note: dict, ctx: dict, dry: bool) -> str:
    """Import one note; returns 'created', 'skipped', or 'trashed'."""
    if note.get("isTrashed"):
        return "trashed"
    name = card_name(note)
    if name in ctx["existing"]:
        return "skipped"

    list_name = "Pinned" if note.get("isPinned") else "Notes"
    flags = " ".join(f for f, on in [("pinned", note.get("isPinned")),
                                     ("archived", note.get("isArchived"))] if on)
    print(f"  + {name}" + (f"  [{flags}]" if flags else ""))
    if dry:
        ctx["existing"].add(name)
        return "created"

    list_id = ensure_list(c, ctx["board_id"], list_name, ctx["lists"], dry)
    card = with_retry(c.post, "/cards", idList=list_id, name=name,
                      desc=note_desc(note))

    for lab in note.get("labels") or []:
        label_id = ensure_label(c, ctx["board_id"], lab["name"], ctx["labels"], dry)
        with_retry(c.post, f"/cards/{card['id']}/idLabels", value=label_id)

    items = note.get("listContent") or []
    if items:
        checklist = with_retry(c.post, "/checklists", idCard=card["id"], name="Items")
        for item in items:
            with_retry(c.post, f"/checklists/{checklist['id']}/checkItems",
                       name=item["text"][:16384] or "(empty)",
                       checked="true" if item.get("isChecked") else "false")

    for att in note.get("attachments") or []:
        path = ctx["dump_dir"] / att["filePath"]
        if path.exists():
            with_retry(upload_attachment, c, card["id"], path)
        else:
            print(f"    ! attachment missing: {att['filePath']}")

    if note.get("isArchived"):
        with_retry(c.put, f"/cards/{card['id']}", closed="true")

    ctx["existing"].add(name)
    return "created"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dump_dir", type=Path, help="Path to Takeout/Keep directory")
    ap.add_argument("--board", default="Keep import")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    creds = load_credentials()
    if creds is None:
        sys.exit(SETUP_HELP)
    c = TrelloClient(*creds)

    files = sorted(args.dump_dir.glob("*.json"))
    if not files:
        sys.exit(f"No .json note files found in {args.dump_dir}")
    notes = [json.loads(f.read_text()) for f in files]
    notes.sort(key=lambda n: n.get("userEditedTimestampUsec") or 0, reverse=True)
    print(f"{len(notes)} notes in dump")

    board = ensure_board(c, args.board, args.dry_run)
    ctx = {"board_id": board["id"], "dump_dir": args.dump_dir,
           "lists": {}, "labels": {}, "existing": set()}
    if not args.dry_run:
        ctx["lists"] = {l["name"]: l["id"]
                        for l in c.get(f"/boards/{board['id']}/lists", fields="name")}
        ctx["labels"] = {l["name"]: l["id"]
                         for l in c.get(f"/boards/{board['id']}/labels", fields="name")
                         if l["name"]}
        ctx["existing"] = {card["name"] for card in
                           c.get(f"/boards/{board['id']}/cards", filter="all",
                                 fields="name")}

    tally = {"created": 0, "skipped": 0, "trashed": 0}
    for note in notes:
        tally[import_note(c, note, ctx, args.dry_run)] += 1

    print(f"\nDone: {tally['created']} imported, {tally['skipped']} already present, "
          f"{tally['trashed']} trashed notes ignored")
    if not args.dry_run and board.get("shortUrl"):
        print(f"Board: {board['shortUrl']}")


if __name__ == "__main__":
    main()
