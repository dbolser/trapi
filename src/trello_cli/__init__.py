from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("trello-cli")
except PackageNotFoundError:
    __version__ = "0+unknown"
