# trapi-cli

A gh-style command line interface for Trello.

> Distribution name `trapi-cli`; the installed command is `trello` and the
> importable package is `trello_cli`.

## Install

As a standalone CLI:

```sh
uv tool install trapi-cli          # from PyPI
uv tool install -e .               # from a local checkout (editable)
```

As a dependency of another project (to reuse the client in code):

```sh
uv add trapi-cli
```

```python
from trello_cli.api import TrelloClient
from trello_cli.config import load_credentials

client = TrelloClient(*load_credentials())
client.get("/members/me")
```

The importable surface (`TrelloClient`, `load_credentials`, `match_ref`) exists
for the CLI's own use — treat it as unstable until a 1.0 release.

## Setup

1. Go to https://trello.com/power-ups/admin and create a (private) Power-Up
2. Copy the **API key**
3. Click the **Token** link next to the key to generate a user token
4. Copy `.env.example` to `.env` (or `~/.config/trello-cli/.env`) and fill both in

Verify with:

```sh
trello auth status
```

## Usage

Boards, lists, and cards can be referenced by id, shortLink, or (partial) name.

```sh
trello board list                     # your boards
trello board view "My Board"          # lists + card counts
trello list list -b "My Board"
trello list add "Doing" -b "My Board"

trello card list "My Board"           # all cards
trello card list "My Board" -l Doing  # one list
trello card view abc123XY --comments
trello card add "Fix the thing" -b "My Board" -l "To Do" -d "details" --due 2026-07-31
trello card edit abc123XY --name "New title" --clear-due
trello card move abc123XY -l Done
trello card archive abc123XY          # --undo to restore
trello card comment abc123XY -m "done in #42"

trello search "invoice"
```

Every command takes a global `--json` flag for scripting:

```sh
trello --json card list "My Board" | jq '.[].name'
```
