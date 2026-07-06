import json
import sys

import typer
from rich.console import Console
from rich.table import Table

from .api import TrelloClient, TrelloError
from .config import SETUP_HELP, load_credentials

app = typer.Typer(help="A gh-style CLI for Trello.", no_args_is_help=True)
auth_app = typer.Typer(help="Check authentication.", no_args_is_help=True)
board_app = typer.Typer(help="Work with boards.", no_args_is_help=True)
list_app = typer.Typer(help="Work with lists.", no_args_is_help=True)
card_app = typer.Typer(help="Work with cards.", no_args_is_help=True)
app.add_typer(auth_app, name="auth")
app.add_typer(board_app, name="board")
app.add_typer(list_app, name="list")
app.add_typer(card_app, name="card")

console = Console()
err_console = Console(stderr=True)
state = {"json": False}


@app.callback()
def main(json_output: bool = typer.Option(False, "--json", help="Output raw JSON.")):
    state["json"] = json_output


def client() -> TrelloClient:
    creds = load_credentials()
    if creds is None:
        err_console.print(SETUP_HELP, style="yellow", highlight=False)
        raise typer.Exit(1)
    return TrelloClient(*creds)


def fail(err: TrelloError):
    err_console.print(f"[red]error:[/red] {err}", highlight=False)
    raise typer.Exit(1)


def emit(data, render):
    """Print raw JSON in --json mode, otherwise call render(data)."""
    if state["json"]:
        print(json.dumps(data, indent=2))
    else:
        render(data)


def guard(fn):
    """Run fn, converting TrelloError into a clean exit."""
    try:
        return fn()
    except TrelloError as e:
        fail(e)


# -- auth ---------------------------------------------------------------

@auth_app.command("status")
def auth_status():
    """Verify credentials by fetching your member profile."""
    me = guard(lambda: client().get("/members/me", fields="fullName,username,url"))

    def render(me):
        console.print(f"[green]✓[/green] Logged in as [bold]{me['fullName']}[/bold] "
                      f"(@{me['username']}) — {me['url']}")

    emit(me, render)


# -- board --------------------------------------------------------------

@board_app.command("list")
def board_list(all: bool = typer.Option(False, "--all", "-a", help="Include closed boards.")):
    """List your boards."""
    filter = "all" if all else "open"
    boards = guard(lambda: client().get("/members/me/boards", filter=filter,
                                        fields="name,shortLink,closed,shortUrl"))

    def render(boards):
        table = Table("ID", "Name", "URL")
        for b in boards:
            name = b["name"] + (" [dim](closed)[/dim]" if b["closed"] else "")
            table.add_row(b["shortLink"], name, b["shortUrl"])
        console.print(table)

    emit(boards, render)


@board_app.command("view")
def board_view(board: str = typer.Argument(help="Board id, shortLink, or name.")):
    """Show a board and its lists with card counts."""
    def go():
        c = client()
        b = c.resolve_board(board)
        lists = c.get(f"/boards/{b['id']}/lists", fields="name")
        cards = c.get(f"/boards/{b['id']}/cards", fields="idList")
        return b, lists, cards

    b, lists, cards = guard(go)
    counts = {}
    for card in cards:
        counts[card["idList"]] = counts.get(card["idList"], 0) + 1
    lists = [{**lst, "cardCount": counts.get(lst["id"], 0)} for lst in lists]

    def render(_):
        console.print(f"[bold]{b['name']}[/bold] — {b['url']}")
        table = Table("List", "Cards")
        for lst in lists:
            table.add_row(lst["name"], str(lst["cardCount"]))
        console.print(table)

    emit({"board": b, "lists": lists}, render)


# -- list ---------------------------------------------------------------

@list_app.command("list")
def list_list(board: str = typer.Option(..., "--board", "-b", help="Board id, shortLink, or name.")):
    """List the lists on a board."""
    def go():
        c = client()
        b = c.resolve_board(board)
        return c.get(f"/boards/{b['id']}/lists", fields="name,closed")

    lists = guard(go)

    def render(lists):
        table = Table("ID", "Name")
        for lst in lists:
            table.add_row(lst["id"], lst["name"])
        console.print(table)

    emit(lists, render)


@list_app.command("add")
def list_add(name: str,
             board: str = typer.Option(..., "--board", "-b", help="Board id, shortLink, or name.")):
    """Create a list on a board."""
    def go():
        c = client()
        b = c.resolve_board(board)
        return c.post("/lists", name=name, idBoard=b["id"], pos="bottom")

    lst = guard(go)
    emit(lst, lambda lst: console.print(f"[green]✓[/green] Created list [bold]{lst['name']}[/bold]"))


# -- card ---------------------------------------------------------------

@card_app.command("list")
def card_list(board: str = typer.Argument(help="Board id, shortLink, or name."),
              list_: str = typer.Option(None, "--list", "-l", help="Only cards in this list.")):
    """List cards on a board (optionally one list)."""
    def go():
        c = client()
        b = c.resolve_board(board)
        lists = {lst["id"]: lst["name"] for lst in c.get(f"/boards/{b['id']}/lists", fields="name")}
        if list_:
            lst = c.resolve_list(b["id"], list_)
            cards = c.get(f"/lists/{lst['id']}/cards",
                          fields="name,shortLink,idList,due,labels")
        else:
            cards = c.get(f"/boards/{b['id']}/cards",
                          fields="name,shortLink,idList,due,labels")
        return lists, cards

    lists, cards = guard(go)

    def render(_):
        table = Table("ID", "Name", "List", "Labels", "Due")
        for card in cards:
            labels = ", ".join(lab["name"] or lab["color"] for lab in card["labels"])
            due = (card["due"] or "")[:10]
            table.add_row(card["shortLink"], card["name"],
                          lists.get(card["idList"], "?"), labels, due)
        console.print(table)

    emit(cards, render)


@card_app.command("view")
def card_view(card: str = typer.Argument(help="Card id or shortLink."),
              comments: bool = typer.Option(False, "--comments", help="Include comments.")):
    """Show a card in full."""
    def go():
        c = client()
        data = c.get(f"/cards/{card}", fields="name,desc,due,closed,shortUrl,labels",
                     members="true", member_fields="fullName",
                     list="true", list_fields="name")
        acts = c.get(f"/cards/{card}/actions", filter="commentCard") if comments else []
        return data, acts

    data, acts = guard(go)

    def render(_):
        console.print(f"[bold]{data['name']}[/bold]"
                      + (" [dim](archived)[/dim]" if data["closed"] else ""))
        console.print(f"[dim]{data['shortUrl']}[/dim]")
        console.print(f"List: {data['list']['name']}")
        if data["due"]:
            console.print(f"Due: {data['due'][:10]}")
        if data["labels"]:
            console.print("Labels: " + ", ".join(lab["name"] or lab["color"] for lab in data["labels"]))
        if data["members"]:
            console.print("Members: " + ", ".join(m["fullName"] for m in data["members"]))
        if data["desc"]:
            console.print(f"\n{data['desc']}")
        for act in reversed(acts):
            who = (act.get("memberCreator") or {}).get("fullName", "unknown")
            when = act["date"][:16].replace("T", " ")
            console.print(f"\n[cyan]{who}[/cyan] [dim]{when}[/dim]\n{act['data']['text']}")

    emit({"card": data, "comments": acts}, render)


@card_app.command("add")
def card_add(name: str,
             board: str = typer.Option(..., "--board", "-b"),
             list_: str = typer.Option(..., "--list", "-l"),
             desc: str = typer.Option(None, "--desc", "-d"),
             due: str = typer.Option(None, "--due", help="Due date, e.g. 2026-07-31.")):
    """Create a card."""
    def go():
        c = client()
        b = c.resolve_board(board)
        lst = c.resolve_list(b["id"], list_)
        return c.post("/cards", idList=lst["id"], name=name, desc=desc, due=due)

    card = guard(go)
    emit(card, lambda card: console.print(
        f"[green]✓[/green] Created [bold]{card['name']}[/bold] ({card['shortUrl']})"))


@card_app.command("edit")
def card_edit(card: str,
              name: str = typer.Option(None, "--name"),
              desc: str = typer.Option(None, "--desc", "-d"),
              due: str = typer.Option(None, "--due"),
              clear_due: bool = typer.Option(False, "--clear-due")):
    """Edit a card's name, description, or due date."""
    if not any([name, desc is not None, due, clear_due]):
        fail(TrelloError("Nothing to change — pass --name, --desc, --due, or --clear-due."))

    def go():
        return client().put(f"/cards/{card}", name=name, desc=desc,
                            due="" if clear_due else due)

    updated = guard(go)
    emit(updated, lambda u: console.print(f"[green]✓[/green] Updated [bold]{u['name']}[/bold]"))


@card_app.command("move")
def card_move(card: str,
              list_: str = typer.Option(..., "--list", "-l", help="Target list."),
              board: str = typer.Option(None, "--board", "-b",
                                        help="Target board (defaults to the card's board).")):
    """Move a card to another list."""
    def go():
        c = client()
        current = c.get(f"/cards/{card}", fields="idBoard,name")
        board_id = c.resolve_board(board)["id"] if board else current["idBoard"]
        lst = c.resolve_list(board_id, list_)
        return c.put(f"/cards/{card}", idList=lst["id"], idBoard=board_id), lst

    updated, lst = guard(go)
    emit(updated, lambda u: console.print(
        f"[green]✓[/green] Moved [bold]{updated['name']}[/bold] to [bold]{lst['name']}[/bold]"))


@card_app.command("archive")
def card_archive(card: str,
                 undo: bool = typer.Option(False, "--undo", help="Unarchive instead.")):
    """Archive (or unarchive) a card."""
    updated = guard(lambda: client().put(f"/cards/{card}", closed="false" if undo else "true"))
    verb = "Unarchived" if undo else "Archived"
    emit(updated, lambda u: console.print(f"[green]✓[/green] {verb} [bold]{u['name']}[/bold]"))


@card_app.command("comment")
def card_comment(card: str,
                 message: str = typer.Option(..., "--message", "-m")):
    """Comment on a card."""
    act = guard(lambda: client().post(f"/cards/{card}/actions/comments", text=message))
    emit(act, lambda a: console.print("[green]✓[/green] Comment added"))


# -- search -------------------------------------------------------------

@app.command("search")
def search(query: str):
    """Search cards and boards."""
    res = guard(lambda: client().get("/search", query=query,
                                     modelTypes="cards,boards",
                                     card_fields="name,shortLink,shortUrl",
                                     board_fields="name,shortLink,shortUrl"))

    def render(res):
        if res.get("boards"):
            table = Table("ID", "Board", "URL")
            for b in res["boards"]:
                table.add_row(b["shortLink"], b["name"], b["shortUrl"])
            console.print(table)
        if res.get("cards"):
            table = Table("ID", "Card", "URL")
            for c in res["cards"]:
                table.add_row(c["shortLink"], c["name"], c["shortUrl"])
            console.print(table)
        if not res.get("boards") and not res.get("cards"):
            console.print("No results.")

    emit(res, render)


if __name__ == "__main__":
    app()
