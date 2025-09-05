from typing import Any


class Config:
    def __init__(self):
        self.data: dict[str, Any] = {
            "root": None,
            "cliapi": None,
            "mongo": None,
            "lastfm": None,
        }

    def __setitem__(self, item: str, value: Any) -> None:
        self.data[item] = value

    def __getitem__(self, item: str) -> Any:
        return self.data[item]

    def __getattr__(self, attr: str) -> Any:
        try:
            return self.data[attr]
        except IndexError:
            raise AttributeError(f"attribute {attr} is not available")
