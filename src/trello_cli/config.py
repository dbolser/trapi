import os
from pathlib import Path

from dotenv import load_dotenv

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


def load_credentials() -> tuple[str, str] | None:
    """Return (key, token), or None if not configured.

    Precedence: real environment > ./.env > ~/.config/trello-cli/.env
    """
    load_dotenv(Path.cwd() / ".env")
    try:
        load_dotenv(Path.home() / ".config" / "trello-cli" / ".env")
    except RuntimeError:  # home directory unresolvable (e.g. no $HOME)
        pass
    key = os.environ.get("TRELLO_API_KEY")
    token = os.environ.get("TRELLO_TOKEN")
    if key and token:
        return key, token
    return None
