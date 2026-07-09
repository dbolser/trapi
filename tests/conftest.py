import httpx
import pytest

from trello_cli.api import BASE_URL, TrelloClient


def make_client(handler) -> TrelloClient:
    """A TrelloClient whose HTTP layer is an httpx.MockTransport."""
    client = TrelloClient("test-key", "test-token")
    client._http = httpx.Client(base_url=BASE_URL,
                                transport=httpx.MockTransport(handler))
    return client


def json_response(data, status=200):
    return httpx.Response(status, json=data)


@pytest.fixture
def recorder():
    """Collects requests and answers them from a path -> data table."""

    class Recorder:
        def __init__(self):
            self.requests = []
            self.routes = {}

        def __call__(self, request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            path = request.url.path.removeprefix("/1")
            if path in self.routes:
                return json_response(self.routes[path])
            return httpx.Response(404, text="not found")

    return Recorder()
