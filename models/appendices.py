from __future__ import annotations

import collections.abc
from typing import Iterator, Literal, Optional, TYPE_CHECKING
import discord
from discord.utils import get
from inspect import iscoroutinefunction
from .utils import try_coro, as_patial_emoji_list

if TYPE_CHECKING:
    from .typings import FindType, GetType
    from .event import Event


__all__ = ("Finder",)


class Finder:
    guilds: list[discord.Guild]
    intents: discord.Intents
    cached_messages: collections.abc.Sequence

    def get_all_roles(self) -> Iterator[discord.Role]:
        for guild in self.guilds:
            for role in guild.roles:
                yield role

    def get_role(self, id: int) -> Optional[discord.Role]:
        for guild in self.guilds:
            role = guild.get_role(id)
            if role:
                return role

    async def shared_guilds(
        self, member: discord.User | discord.Member
    ) -> Iterator[discord.Guild]:
        id = member.id
        if self.intents.members:

            async def check(guild: discord.Guild):
                return guild.get_member(id)

        else:

            def check(guild: discord.Guild):
                return try_coro(guild.fetch_member(id))

        for guild in self.guilds:
            if await check(guild):
                yield guild

    def get_message(self, id: int) -> Optional[discord.Message]:
        return get(self.cached_messages, id=id)

    async def fetch_object(
        self,
        id: int | str,
        event: Optional[Event] = None,
        guild: discord.Guild | Literal[False] | None = False,
    ) -> GetType:
        """
        Try to get or fetch any object that is visible to bot.
        """
        object = None

        if guild:
            guild_scope = True
        else:
            guild = getattr(event, "guild", None)
            guild_scope = False

        try:
            assert len(str(id)) >= 17
            id = int(id)
        except Exception:

            async def find_single_object(name):
                gen = self.find_object(name, event, equals=True)
                return await gen.__anext__()

            def get_color(color: str):
                if color.startswith("#"):
                    color = color.removeprefix("#")
                if color.startswith("0x"):
                    color = color.removeprefix("0x")
                else:
                    return None
                return discord.Color(int(color, base=16))

            functions = (
                lambda name: get(as_patial_emoji_list, name=name),
                get_color,
                find_single_object,
            )

        else:
            functions = (
                (
                    (guild.get_member if self.intents.members else guild.fetch_member)
                    if guild
                    else lambda id: None
                ),
                self.get_user,
                self.get_guild,
                self.get_channel,
                self.get_emoji,
                self.get_message,
                self.get_role,
                self.fetch_user,
                self.fetch_webhook,
            )

        for func in functions:
            if iscoroutinefunction(func):
                object = await try_coro(func(id))

            else:
                object = func(id)

            if object:
                if guild_scope and object.guild != guild:
                    break
                return object

        if type(id) is str:
            id = 0
        return discord.Object(id)

    async def find_object(
        self,
        query: str,
        event: Optional[Event] = None,
        guild: discord.Guild | Literal[False] | None = False,
        equals: bool = False,
    ) -> Iterator[FindType]:
        found = []

        if guild:
            guild_scope = True
        else:
            guild = getattr(event, "guild", None)
            guild_scope = False

        if guild_scope:
            functions = (
                (
                    guild.members
                    if self.intents.members
                    else guild.fetch_members(limit=None)
                ),
                guild.emojis,
                guild.channels,
                guild.roles,
            )

        else:
            functions = (
                (
                    guild.members
                    if self.intents.members
                    else guild.fetch_members(limit=None) if guild else []
                ),
                self.users,
                self.guilds,
                self.emojis,
                self.get_all_channels(),
                self.get_all_roles(),
            )

        if equals:

            def inner_check(object, name):
                return query == name or (
                    type(object) is discord.Member and query == object.display_name
                )

        else:
            query = query.lower()

            def inner_check(object, name):
                return query in name.lower() or (
                    type(object) is discord.Member
                    and query in object.display_name.lower()
                )

        def check(object):
            if object.id in found:
                return False

            name = object.name if type(object) is discord.Emoji else str(object)

            if inner_check(object, name):
                return True

            return False

        for generator in functions:
            if isinstance(generator, discord.iterators._AsyncIterator):
                async for object in generator:
                    checked = check(object)
                    if checked:
                        found.append(object.id)
                        yield object
            else:
                for object in generator:
                    checked = check(object)
                    if checked:
                        found.append(object.id)
                        yield object
