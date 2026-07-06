import os
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

SETUP_HELP = """\
Missing Trello credentials. To set them up:

  1. Go to https://trello.com/power-ups/admin and create a (private) Power-Up
  2. Copy the API key it gives you
  3. Click the "Token" link next to the key to generate a user token
  4. Put both in a .env file (here, or in ~/.config/trello-cli/.env):

       TRELLO_API_KEY=...
       TRELLO_TOKEN=...

They are also read from the environment directly.\
"""


def _pair(vals: Mapping[str, str | None]) -> tuple[str, str] | None:
    key, token = vals.get("TRELLO_API_KEY"), vals.get("TRELLO_TOKEN")
    if key and token:
        return key, token
    return None


def load_credentials() -> tuple[str, str] | None:
    """Return (key, token), or None if not configured.

    The first source with a complete pair wins — environment, then ./.env,
    then ~/.config/trello-cli/.env. Sources are never blended: a stray
    half-credential in one must not pair with the other half from another.
    """
    creds = _pair(os.environ)
    if creds:
        return creds
    paths = [Path.cwd() / ".env"]
    try:
        paths.append(Path.home() / ".config" / "trello-cli" / ".env")
    except RuntimeError:  # home directory unresolvable (e.g. no $HOME)
        pass
    for path in paths:
        creds = _pair(dotenv_values(path))
        if creds:
            return creds
    return None
