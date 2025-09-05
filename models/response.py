from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Iterator, Optional, TYPE_CHECKING, TypedDict
import discord
from .utils import run_in_executor

if TYPE_CHECKING:
    from parser.wrapper import Result
    from .event import Event

__all__ = (
    "Response",
    "generate_pages_dictionary",
)

length = 1800
responses: dict[int, "Response"] = {}


def paginate(string: str) -> Iterator[str]:
    """
    Split string by limit and line-breaks.
    """
    while len(string) > length:
        sliced = string[:length]

        if "\n" in sliced:
            splitted = sliced.rsplit("\n", 1)[0] + "\n"
        else:
            splitted = sliced

        yield splitted

        string = string.removeprefix(splitted)
        # string = string.split(splitted, 1)[-1]

    else:
        yield string


def embed_paginate(embed: discord.Embed) -> Iterator[discord.Embed]:
    """
    Split embed description by limit and line-breaks.
    """
    string = embed.description

    if len(string) <= length:
        yield embed
        return

    for sub in paginate(string):
        new: discord.Embed = embed.copy()
        new.description = sub
        yield new


class PagesDict(TypedDict):
    name: str | None
    content: list[str]
    short_content: str | None
    embeds: list[discord.Embed]
    embeds_parsed: bool
    files: list[discord.File]
    pages: int
    prefix: str
    post_prefix: str
    suffix: str
    syntax: str
    raw: Result


@run_in_executor
def generate_pages_dictionary(result: Result) -> Awaitable[PagesDict]:
    content = list(paginate(str(result)))

    embeds = result.embeds
    if len(embeds) == 1:
        embeds = list(embed_paginate(embeds[0]))
        embeds_parsed = True
    else:
        embeds = embeds[:10]
        embeds_parsed = False

    files = result.files

    pages = len(embeds) if len(embeds) > 1 else len(content)

    return PagesDict(
        name=result.name,
        content=content,
        short_content=result.short_content,
        embeds=embeds,
        embeds_parsed=embeds_parsed,
        files=files[:10],
        pages=pages,
        prefix=result.prefix or "```",
        post_prefix=result.post_prefix or "\n",
        suffix=result.suffix or "```",
        syntax=result.syntax,
        raw=result,
    )


class Response:
    def __init__(self):
        self.event: Optional[Event] = None
        self.message: Optional[discord.Message] = None
        self.data: list[dict[str, Any]] = []
        self.current: dict[str, int] = {"command": 0, "page": 0}
        self.collapsed: bool = False
        self.session: Optional[asyncio.Future] = None

    @classmethod
    def get(cls, event: Event) -> "Response":
        msg = event.message
        instance = msg and responses.get(msg.id)

        if not instance:
            instance = cls()
            if msg:
                responses.update({msg.id: instance})

        return instance.set_event(event)

    def set_event(self, event: Event) -> "Response":
        self.event = event
        return self

    def __getitem__(self, item: str) -> Any:
        return self.data[self.current["command"]][item]

    def __len__(self):
        return len(self.data)

    def __str__(self):
        page = f"{self.current['page'] + 1}/{self['pages']}"
        command = f"{self.current['command'] + 1}/{len(self)}" if len(self) > 1 else ""

        if self.collapsed:
            return (
                self["prefix"]
                + self["post_prefix"]
                + f"== `{self['short_content']}` {{{self.event.user}}} "
                + (
                    f"[p.{page}" + (command and f", c.{command}] " or "] ")
                    if self.is_paged()
                    else ""
                )
                + "=="
                + self["suffix"]
            )

        content = self.page("content")

        if not content:
            if self.embed is None and not self["files"]:
                content = "== NO OUTPUT =="
            elif self["content"]:
                pass
            else:
                return ""

        return (
            (
                self["prefix"]
                + self["syntax"]
                + self["post_prefix"]
                + content
                + self["suffix"]
                if content
                else ""
            )
            + (f"\nCommand: `{self['short_content']}` — *{self.event.user}*")
            + (
                f"\nPage: {page}" + (command and f" _(Response: {command})_")
                if self.is_paged()
                else ""
            )
        )

    def is_paged(self) -> bool:
        return len(self) > 1 or len(self["content"]) > 1 or len(self["embeds"]) > 1

    def is_long(self) -> bool:
        return len(str(self.result)) > 600 or (
            self.embed and len(self.embed.description) > 600
        )

    def page(self, item: str) -> Optional[str | discord.Embed]:
        data = self[item]
        page = self.current["page"]

        if data and page < len(data):
            return data[page]
        else:
            return None

    @property
    def embed(self) -> Optional[discord.Embed]:
        if self.collapsed:
            return None
        return self.page("embeds")

    @property
    def result(self) -> Result:
        return self["raw"]

    async def append(self, result: Result) -> "Response":
        self.data.append(await generate_pages_dictionary(result))

        return self

    async def send(self) -> bool:
        if not self.result.send:
            self.message = False
            return False

        self.message = await self.event.send(
            content=str(self),
            # embeds=self["embeds"][:10],
            embed=self.embed,
            files=self["files"],
        )
        return True

    async def edit(self) -> None:
        await self.message.edit(content=str(self), embed=self.embed)

    reactions = ("↕️", "⬅️", "➡️", "❌")

    async def setup_reactions(self) -> tuple:
        """
        Setup required reactions.
        """
        if self.is_paged():
            reactions = self.reactions[:3]
        elif self.is_long():
            reactions = self.reactions[:1]
        else:
            reactions = tuple()

        for reaction in reactions:
            if reaction not in self.message.reactions:
                await self.message.add_reaction(reaction)

        return reactions

    def check_reaction(self, event: Event) -> bool:
        """
        Check if event is correct.
        """
        user = event.user

        if not user:
            return False
        if event.message.id != self.message.id:
            return False
        if str(event.reaction) not in self.reactions:
            return False
        if "admin" in event.groups() and not user.bot:
            return True
        if user.id != self.event.user.id:
            return False

        return True

    async def waiter(self) -> None:
        """
        Check reactions and change pages.
        """
        async for event in self.event.client.fetch_events(
            ("raw_reaction_remove", self.check_reaction),
            ("raw_reaction_add", self.check_reaction),
            timeout=300,
        ):
            if event:
                result = str(event.reaction)
            else:
                result = None

            command, page = self.current.values()

            if result == "⬅️":
                if page == 0:
                    if command != 0:
                        self.current["command"] -= 1
                        self.current["page"] = self["pages"] - 1
                else:
                    self.current["page"] -= 1

            elif result in ("❌", None):
                try:
                    await self.message.clear_reactions()
                except Exception:
                    pass
                return

            elif result == "➡️":
                if page + 1 != self["pages"]:
                    self.current["page"] += 1
                elif command + 1 != len(self):
                    self.current["command"] += 1
                    self.current["page"] = 0

            elif result == "↕️":
                self.collapsed = not self.collapsed

            await self.edit()

    async def launch(self) -> None:
        if self.message is None:
            if await self.send() is False:
                return

        elif self.message is False:
            self.current["command"] = len(self) - 1
            self.current["page"] = 0
            if await self.send() is False:
                return

        else:
            self.current["command"] = len(self) - 1
            self.current["page"] = 0
            await self.edit()

        reactions = await self.setup_reactions()

        if reactions:
            if not self.session or self.session.done():
                self.session = asyncio.ensure_future(self.waiter())

    def cancel(self) -> bool:
        asyncio.ensure_future(self.message.clear_reactions())
        return self.session.cancel()

    async def delete(self) -> None:
        self.session.cancel()
        responses.pop(self.event.message.id)
        await self.message.delete()
