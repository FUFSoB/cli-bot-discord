from __future__ import annotations

from datetime import datetime, timedelta
from models.database import db
from models.errors import CommandPermissionError
from models.packages import reloading
import discord
import ctypes
import os
import asyncio
import random
from difflib import SequenceMatcher
from youtube_title_parse import get_artist_title

from ._lastfm import auth as lastfm_auth, apply_scrobble, apply_scrobbling_now

from typing import Optional, TYPE_CHECKING
from models.event import Event

# from argparse import Namespace
# from parser.wrapper import Result

if TYPE_CHECKING:
    from ._receivers import BasicReceiver

if not reloading:
    discord.opus.load_opus(ctypes.util.find_library("opus"))
    sessions: dict[int, "VoiceSession"] = {}
    devnull = open(os.devnull, "w+")


class QueueItem:
    def __init__(
        self,
        event: Event,
        query: str,
        receiver: BasicReceiver,
        *,
        title: Optional[str] = None,
        url: Optional[str] = None,
        data: Optional[dict[str]] = None,
    ):
        self.event = event
        self.query = query
        self.receiver = receiver
        receiver.set_item(self)
        self._data: dict[str] = data
        self._title: str = title
        self._url: str = url
        self._play_url: str = None
        self.remove: bool = True
        self.logging: bool = True
        self.start_time: float = 0
        self.stopped: bool = False

    def __getattr__(self, attr: str):
        return self.data.get(attr)

    def __repr__(self):
        return f"<QueueItem query={self.query!r}>"

    def __str__(self):
        return f"{self.full_title} < [{self.event.user}]"

    @property
    def title(self) -> str:
        return self._title or self.receiver.title or self.query or ""

    @property
    def url(self) -> str:
        return self._url or self.receiver.url or self.query or ""

    @property
    def data(self) -> dict[str]:
        return self._data or self.receiver.data or {}

    @property
    def info(self) -> tuple[str, str, str | None, str | None]:
        if (
            not (artist := self.artist)
            or SequenceMatcher(artist, self.uploader).ratio() < 0.75
        ):
            title = self.title or ""
            title_lower = title.lower()
            if any(i in title_lower for i in ("remix", "gachi", "right version", "♂")):
                artist = self.uploader
            elif not artist and (artist_title := get_artist_title(self.title)):
                artist, title = artist_title
                if artist != self.uploader:
                    artist = self.uploader
                    title = self.track or self.title
            else:
                title = self.track or self.title
                artist = self.artist or self.uploader
        else:
            title = self.track or self.title

        return artist, title, self.album, self.duration

    @property
    def full_title(self) -> str:
        artist, title, *_ = self.info
        if not artist:
            return title
        return f"{title} — {artist}"

    def set_start_time(self, second: float) -> None:
        self.start_time = second

    @property
    def playable(self) -> discord.PCMVolumeTransformer:
        return discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(
                self._play_url,
                before_options="-reconnect 1 -reconnect_streamed 1 "
                f"-reconnect_delay_max 5 -ss {self.start_time}",
                # options=f"",
                stderr=devnull,
            )
        )

    def stop(self, session: "VoiceSession") -> None:
        session.stop()
        self.stopped = True
        self.end.set()

    def toggle_remove(self):
        self.remove = not self.remove

    def toggle_logging(self):
        self.logging = not self.logging

    async def play(self, session: "VoiceSession") -> None:
        try:
            self._title, self._url, self._play_url, self._data = (
                await self.receiver.get()
            )
        except Exception:
            # print(__import__("traceback").format_exc())
            await session.log(f"Track skipped: **{self.title}**\n<{self.url}>")
            return

        self.stopped: bool = False
        self.end = end = asyncio.Event()

        session.play(self.playable, after=lambda *a: end.set())
        self.started = datetime.now()

        if not self.logging:
            self.toggle_logging()
        else:
            await session.log(f"Now playing: **{self.title}**\n<{self.url}>")

        asyncio.ensure_future(self.apply_scrobbling_now(session))

        await end.wait()
        self.ended = datetime.now()

        if not self.stopped:
            asyncio.ensure_future(self.apply_scrobbles(session))
        else:  # remove scrobbling now here ?
            pass

    @property
    def time_passed(self) -> timedelta:
        return datetime.now() - self.started

    @property
    def current_position(self) -> float:
        return self.time_passed.total_seconds() + self.start_time

    def seek(self, session: "VoiceSession", seconds: float) -> float:
        seeked = self.current_position + seconds
        if seeked < 0:
            seeked = 0
        self.set_start_time(seeked)

        self.toggle_remove()
        self.toggle_logging()
        self.stop(session)

        return seeked

    async def apply_scrobbling_now(self, session: "VoiceSession") -> None:
        members: list[discord.Member] = session.channel.members
        for member in members:
            data = await db.get_auth_keys(member.id, "lastfm")
            if not data:
                continue

            last = await lastfm_auth(session.client.config["lastfm"], member.id, **data)
            await apply_scrobbling_now(last, self)

    async def apply_scrobbles(self, session: "VoiceSession") -> None:
        members: list[discord.Member] = session.channel.members
        for member in members:
            data = await db.get_auth_keys(member.id, "lastfm")
            if not data:
                continue

            last = await lastfm_auth(session.client.config["lastfm"], member.id, **data)
            await apply_scrobble(last, self)


class Queue:
    def __init__(self, session: "VoiceSession"):
        self.session = session
        self.items: list[QueueItem] = []
        self.history: list[QueueItem] = []
        self._running = None
        self.repeat = False
        self.start_event = asyncio.Event()

    def __repr__(self):
        return f"<Queue for {self.session.id}>"

    def __getitem__(self, item: int) -> QueueItem:
        return self.items[item]

    def __len__(self):
        return len(self.items)

    def __iter__(self):
        yield from self.items

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.items:
            self.start_event.clear()
            try:
                await asyncio.wait_for(self.start_event.wait(), 300)
            except Exception:
                await self.session.disconnect(True)
                raise StopAsyncIteration

        return self.items[0]

    def __del__(self):
        self.stop()

    @property
    def current(self) -> QueueItem | None:
        try:
            return self.items[0]
        except IndexError:
            return None

    @property
    def next_track(self) -> QueueItem | None:
        try:
            return self.items[1]
        except IndexError:
            return None

    def append(self, item: QueueItem, index: Optional[int] = None) -> int:
        if not index or len(self.items) <= index:
            self.items.append(item)
            index = len(self.items) - 1
        else:
            self.items.insert(index, item)

        self.start_event.set()

        return index

    def remove(self, num: int) -> QueueItem:
        if num == 0:
            item = self.items[0]
            item.stop(self.session)
        else:
            item = self.items.pop(num)
        return item

    def next(self, num: Optional[int] = None) -> list[QueueItem]:
        if not self.items:
            return []

        if not num or num <= 1:
            num = 1

        items = self.items[:num]

        item = items[0]
        item.toggle_remove()
        item.set_start_time(0)
        item.stop(self.session)

        del self.items[:num]

        self.history.extend(items)
        return items

    def previous(self, num: Optional[int] = None) -> list[QueueItem]:
        if self.items:  # may be problem with incorrect continue of queue
            item = self.items[0]
            item.toggle_remove()
            item.set_start_time(0)
            item.stop(self.session)

        history_length = len(self.history)
        if history_length == 0:
            return []

        if not num or num <= 1:
            num = history_length - 1
        else:
            num = history_length - num

        prev_items = self.history[num:]
        del self.history[num:]

        self.items[0:0] = prev_items
        self.start_event.set()

        return prev_items

    def reset_current(self) -> None:
        if self.items:
            item = self.items[0]
            item.toggle_remove()
            item.set_start_time(0)
            item.stop(self.session)

    def clear(self) -> None:
        del self.items[1:]

    def empty(self) -> None:
        self.items.clear()

    def toggle_repeat(self, value: bool | str = True) -> bool | str:
        self.repeat = False if self.repeat == value else value
        return self.repeat

    def shuffle(self) -> None:
        lst = self.items[1:]
        del self.items[1:]

        random.shuffle(lst)

        self.items.extend(lst)

    async def run(self) -> None:
        async for item in self:
            await item.play(self.session)

            if not item.remove:
                item.toggle_remove()
                continue

            try:
                item.set_start_time(0)
                if not self.repeat:
                    self.items.remove(item)
                    self.history.append(item)
                elif self.repeat == "all":
                    self.items.remove(item)
                    self.items.append(item)
            except Exception:
                pass

    def start(self) -> "Queue":
        self._running = asyncio.ensure_future(self.run())
        return self

    def stop(self) -> None:
        self._running.cancel()

    def seek(self, seconds: float) -> float | None:
        if self.items:
            return self.items[0].seek(self.session, seconds)


class VoiceSession:
    def __init__(
        self, original: discord.VoiceClient, id: int, text_channel: discord.TextChannel
    ):
        self.original = original
        self.id = id
        self.logs = text_channel
        self.queue = Queue(self).start()
        self.skipping = set()

    def __repr__(self):
        return f"<VoiceSession {self.id}>"

    def __getattr__(self, attr: str):
        return getattr(self.original, attr)

    def __contains__(self, member: discord.Member):
        return member in self.original.channel.members

    def __len__(self):
        return len(self.original.channel.members)

    async def log(self, content: str) -> None:
        try:
            await self.logs.send(content)
        except Exception:
            pass

    async def disconnect(self, from_queue: bool = False) -> None:
        if sessions[self.id] == self:
            del sessions[self.id]
            if not from_queue:
                del self.queue

            return await self.original.disconnect(force=True)

    def append(self, item: QueueItem, index: Optional[int] = None) -> int:
        return self.queue.append(item, index)

    def remove(self, num: int) -> QueueItem:
        return self.queue.remove(num)

    def next(self, num: Optional[int] = None) -> list[QueueItem]:
        return self.queue.next(num)

    def previous(self, num: Optional[int] = None) -> list[QueueItem]:
        return self.queue.previous(num)

    def reset_current(self) -> None:
        return self.queue.reset_current()

    def stop_all(self) -> None:
        self.queue.clear()
        try:
            self.queue.current.stop(self)
        except AttributeError:
            pass

    def repeat(self, value: bool | str = True) -> bool | str:
        return self.queue.toggle_repeat(value)

    def clear(self) -> None:
        self.queue.clear()

    def shuffle(self) -> None:
        self.queue.shuffle()

    def seek(self, seconds: float) -> float | None:
        return self.queue.seek(seconds)


class Mixin:
    @classmethod
    def allowed(cls, event: Event, session: VoiceSession | None) -> bool:
        if (
            not session
            or len(session) <= 2
            or event.user.guild_permissions.administrator
        ):
            return True

        dj = event.guild_state.config.get("dj")
        return bool(dj and dj in event.user.roles)

    @classmethod
    def check(cls, event: Event, session: VoiceSession | None) -> None:
        if not cls.allowed(event, session):
            raise CommandPermissionError(cls, "dj")

    @classmethod
    def get_session(cls, event: Event) -> VoiceSession | None:
        return sessions.get(event.guild.id)

    @classmethod
    def get_and_check(cls, event: Event) -> VoiceSession | None:
        session = cls.get_session(event)
        cls.allowed(event, session)
        return session

    @classmethod
    async def fetch_session(cls, event: Event) -> VoiceSession:
        original = await event.user.voice.channel.connect()
        return cls.set_session(event, original, event.channel)

    @classmethod
    async def fetch_and_check(cls, event: Event) -> VoiceSession:
        session = cls.get_and_check(event)
        if not session:
            session = await cls.fetch_session(event)
        return session

    @classmethod
    def set_session(
        cls,
        event: Event,
        original: discord.VoiceClient,
        text_channel: discord.TextChannel,
    ) -> VoiceSession:
        id = event.guild.id
        session = sessions[id] = VoiceSession(original, id, text_channel)
        return session
