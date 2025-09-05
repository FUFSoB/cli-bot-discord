from __future__ import annotations

import discord
from ._classes import QueueItem
from models.utils import run_in_executor
import youtube_dl

from typing import Any, Awaitable
from models.event import Event

receivers: dict[str, type["BasicReceiver"]] = {}


class MetaReceiver(type):
    def __init__(
        cls: "BasicReceiver", name: str, bases: tuple[type], clsdict: dict[str, Any]
    ):
        super(MetaReceiver, cls).__init__(name, bases, clsdict)
        if len(cls.mro()) > 2:
            receivers[cls.__name__] = cls
            cls.name = cls.__name__.removesuffix("_receiver")


class BasicReceiver(metaclass=MetaReceiver):
    _title: str | None = None
    _url: str | None = None
    _play_url: str | None = None
    _data: dict[str] | None = None
    _active: bool = False

    def __init__(self, event: Event, query: str):
        self.event = event
        self.query = query
        self.item = None

    async def __aiter__(self):
        yield QueueItem(self.event, self.query, self)

    def set_item(self, item: QueueItem) -> None:
        self.item = item

    @property
    def title(self) -> str | None:
        return self._title

    @property
    def url(self) -> str | None:
        return self._url

    @property
    def play_url(self) -> str | None:
        return self._play_url

    @property
    def data(self) -> dict[str] | None:
        return self._data

    async def get_title(self) -> str: ...
    async def get_url(self) -> str: ...
    async def get_play_url(self) -> str: ...
    async def get_data(self) -> dict[str]: ...

    async def get(self) -> tuple[str, str, str, dict[str]]:
        self._active = True

        title = await self.get_title()
        url = await self.get_url()
        play_url = await self.get_play_url()
        data = await self.get_data()

        return title, url, play_url, data


class static_receiver(BasicReceiver):
    def __init__(self, event: Event, query: str):
        self.event = event
        self._play_url = self._url = self.query = query
        self._title = query.rsplit("/", 1)[1].rsplit("?", 1)[0]
        self._data = {}
        self.item = None

    async def get(self) -> tuple[str, str, str, dict[str]]:
        return self.title, self.url, self.play_url, self.data


ydl = youtube_dl.YoutubeDL(
    dict(
        # forcejson=True,
        # simulate=True,
        # skip_download=True,
        postprocessors=[
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "opus",
                "preferredquality": "320",
            }
        ],
        format="bestaudio/best",
        geo_bypass=True,
        ignoreerrors=True,
        youtube_include_dash_manifest=False,
        cachedir=False,
        quiet=True,
        extract_flat=True,  # skip downloading full playlist
    )
)


class ytdl_receiver(BasicReceiver):
    @staticmethod
    @run_in_executor
    def get_youtube_info(query: str) -> Awaitable[dict[str]]:
        data = ydl.extract_info(query, download=False)
        return data

    async def __aiter__(self):
        query = self.query

        if "search" in self.name:
            query = f"ytsearch:{query}"

        result = await self.get_youtube_info(query)

        if "entries" in result:
            for data in result["entries"]:
                yield QueueItem(
                    self.event,
                    data["id"],
                    ytdl_receiver(self.event, data["id"]),
                    title=data["title"],
                    # url=data["webpage_url"]
                    # url=f"https://youtu.be/{data['id']}"
                    url=f"https://www.youtube.com/watch?v={data['id']}",
                    data=data,
                )
        else:
            self._data = result
            yield QueueItem(
                self.event,
                result["id"],
                self,
                title=result["title"],
                url=result["webpage_url"],
                # url=f"https://youtu.be/{result['id']}",
                data=result,
            )

    @property
    def title(self) -> str | None:
        if self._data is not None:
            return self._data["title"]
        return self._title

    @property
    def url(self) -> str | None:
        if self._data is not None:
            return self._data["webpage_url"]
            # return f"https://youtu.be/{self._data['id']}"
        return self._url

    @property
    def play_url(self) -> str | None:
        if self._data is not None:
            return self._data["url"]
        return self._play_url

    @property
    def data(self) -> dict[str] | None:
        return self._data

    async def get_data(self) -> dict[str]:
        if self._data is None:
            self._data = await self.get_youtube_info(self.query)
        return self._data

    async def get(self) -> tuple[str, str, dict[str]]:
        data = await self.get_data()
        return data["title"], self.url, data["url"], data


class ytdl_search_receiver(ytdl_receiver):
    pass


class attachment_receiver(static_receiver):
    def __init__(self, event: Event, query: str | discord.Attachment):
        self.event = event
        self.query = query
        if type(query) is discord.Attachment:
            self._title = query.filename
            self._url = self._play_url = query.url
            self._data = {}
        self.item = None

    async def __aiter__(self):
        for attachment in self.event.message.attachments:
            yield QueueItem(
                self.event, attachment.url, attachment_receiver(self.event, attachment)
            )
