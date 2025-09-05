from __future__ import annotations

from pylast import LastFMNetwork
from models.utils import run_in_executor

# from difflib import SequenceMatcher
# from youtube_title_parse import get_artist_title

from typing import Awaitable, TYPE_CHECKING

if TYPE_CHECKING:
    from ._classes import QueueItem

clients: dict[int, LastFMNetwork] = {}


@run_in_executor
def auth_with_token(config: dict[str, str], token: str) -> Awaitable[LastFMNetwork]:
    """
    Auth with lastfm temporary token.
    """
    client = LastFMNetwork(config["key"], config["secret"], token=token)
    return client


@run_in_executor
def auth(config: dict[str, str], id: int, session_key: str) -> Awaitable[LastFMNetwork]:
    client = clients.get(id)

    if not client:
        clients[id] = client = LastFMNetwork(
            config["key"], config["secret"], session_key=session_key
        )

    return client


# def get_info(item: QueueItem) -> tuple[str, str, str | None, str | None]:
#     if (
#         not (artist := item.artist)
#         or SequenceMatcher(artist, item.uploader).ratio() < 0.75
#     ):
#         if "remix" in (title := item.title or "").lower():
#             artist = item.uploader
#         elif not artist:
#             artist, title = get_artist_title(item.title)
#             if artist != item.uploader:
#                 artist = item.uploader
#                 title = item.track or item.title
#         else:
#             title = item.track or item.title
#     else:
#         title = item.track or item.title

#     return artist, title, item.album, item.duration


@run_in_executor
def apply_scrobble(client: LastFMNetwork, item: QueueItem) -> Awaitable[None]:
    artist, title, album, duration = item.info

    timestamp = item.ended.timestamp()

    client.scrobble(artist, title, timestamp, album, duration=duration)


@run_in_executor
def apply_scrobbling_now(client: LastFMNetwork, item: QueueItem) -> Awaitable[None]:
    artist, title, album, duration = item.info

    client.update_now_playing(artist, title, album, duration=duration)
