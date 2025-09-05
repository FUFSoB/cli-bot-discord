from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Iterator, Literal, Optional, TYPE_CHECKING
import traceback
import discord
from discord.utils import get
from .utils import try_coro, timeit
from .state import UserState, GuildState, DefaultState, get_state
from parser import get_processor
from parser.wrapper import Result
from .response import Response
from .errors import BaseError, InternalError, NoPrefixError
from .packages import get_events
from inspect import isfunction

if TYPE_CHECKING:
    from .bot import Client
    from parser.processing import Processor
    from .typings import (
        ChannelType,
        GuildChannelType,
        UserType,
        FunctionType,
        StateType,
        AllStateType,
        RawModels,
    )

__all__ = ("Event",)

loop = asyncio.get_event_loop()


class Event:
    """
    Class for standardizing all discord.py events.
    """

    launched: Optional[bool] = None
    object: Optional[
        UserType | discord.Guild | discord.Message | ChannelType | discord.Role
    ] = None
    message: Optional[discord.Message] = None
    prev_message: Optional[discord.Message] = None
    guild: Optional[discord.Guild] = None
    prev_guild: Optional[discord.Guild] = None
    channel: Optional[ChannelType] = None
    prev_channel: Optional[GuildChannelType] = None
    user: Optional[UserType] = None
    prev_user: Optional[UserType] = None
    role: Optional[discord.Role] = None
    prev_role: Optional[discord.Role] = None
    emojis: Optional[list[discord.Emoji]] = None
    prev_emojis: Optional[list[discord.Emoji]] = None
    messages: Optional[list[discord.Message]] = None
    voice: Optional[discord.VoiceState] = None
    prev_voice: Optional[discord.VoiceState] = None
    invite: Optional[discord.Invite] = None
    relationship: Optional[discord.Relationship] = None
    prev_relationship: Optional[discord.Relationship] = None
    reaction: Optional[discord.Reaction] = None
    reactions: Optional[list[discord.Reaction]] = None
    when: Optional[datetime] = None

    @property
    def objects(self) -> dict[str, Any]:
        return {
            key: value
            for key in self.__annotations__.keys()
            if (value := getattr(self, key, None))
        }

    def __init__(self, client: Client, name: str):
        self.client = client
        self.name = name
        self.guild_only: bool = False
        self._state: Optional[Literal["user", "guild", "default"]] = None
        self._task: Optional[asyncio.Future] = None
        self.result = Result()
        self.used_aliases: list[str] = []
        self.temporary_variables: dict[str, Any] = {}
        self.temporary_functions: dict[str, FunctionType] = {}
        self.pid: Optional[int] = None
        self._objects_cli: Optional[dict[str, Any]] = None

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self.result, item)
        except AttributeError:
            raise KeyError(item)

    def __bool__(self):
        return any(self.objects.values())

    def __repr__(self):
        return f"<Event {self.name} pid={self.pid} object={self.object}>"

    @property
    def objects_cli(self) -> dict[str, list[int | str] | int | str]:
        if not self._objects_cli:
            self._objects_cli = {
                "_"
                + key: (
                    [v.id if "id" in dir(v) else str(v) for v in value]
                    if type(value) is list
                    else value.id if "id" in dir(value) else str(value)
                )
                for key, value in self.objects.items()
                if value is not None
            }

        return self._objects_cli

    def apply_option(self, option: str, value: Any) -> None:
        self.result.apply_option(option, value)

    def set_pid(self, pid: int) -> None:
        self.pid = pid

    @property
    def short_content(self) -> str:
        return self.result.short_content or self.name

    @property
    def user_state(self) -> UserState:
        if not self.user or self.guild_only or self._state == "guild":
            return None
        return get_state(self.client, self.user)

    @property
    def guild_state(self) -> GuildState:
        if not self.guild:
            return None
        return get_state(self.client, self.guild)

    def pick_state(self, pick: Optional[str] = None) -> None:
        if pick not in ("user", "guild", "default", None):
            raise ValueError("pick must be either user or guild")
        self._state = pick

    @property
    def default_state(self) -> DefaultState:
        return get_state(None, discord.Object(1))

    @property
    def original_state(self) -> StateType:
        return self.user_state or self.guild_state

    @property
    def state(self) -> AllStateType:
        if self._state:
            return getattr(self, self._state + "_state")
        return self.original_state

    @property
    def variables(self) -> dict[str, Any]:
        return (self.guild and self.guild_state.variables(self) or {}) | (
            self.user_state and self.user_state.variables(self) or {}
        )

    @property
    def ready_variables(self) -> dict[str, Any]:
        return {
            name: value(self) if isfunction(value) else value
            for name, value in self.variables.items()
        }

    def set_variable(self, *args, **kwargs) -> Any:
        return self.state.set_variable(self, *args, **kwargs)

    def get_variable(self, name: str) -> Any:
        return self.state.get_variable(self, name, self.variables)

    def pop_variable(self, *args, **kwargs) -> Any:
        return self.state.pop_variable(self, *args, **kwargs)

    @property
    def functions(self) -> dict[str, FunctionType]:
        return (self.guild and self.guild_state.functions(self) or {}) | (
            self.user_state and self.user_state.functions(self) or {}
        )

    def set_function(self, *args, **kwargs) -> FunctionType:
        return self.state.set_function(self, *args, **kwargs)

    def get_function(self, name) -> Optional[FunctionType]:
        return self.state.get_function(self, name, self.functions)

    def pop_function(self, *args, **kwargs) -> Optional[FunctionType]:
        return self.state.pop_function(self, *args, **kwargs)

    @property
    def aliases(self) -> dict[str, list]:
        return (self.guild and self.guild_state.aliases or {}) | (
            self.user_state and self.user_state.aliases or {}
        )

    def set_alias(self, *args, **kwargs) -> None:
        return self.state.set_alias(*args, **kwargs)

    def get_alias(self, name) -> Optional[list]:
        return self.state.get_alias(self, name, self.aliases)

    def pop_alias(self, *args, **kwargs) -> Optional[list]:
        return self.state.pop_alias(*args, **kwargs)

    def groups(self) -> Iterator[str | int]:
        """
        Yield every group available for this event.
        """
        yield "any"

        guild, user = self.guild, self.user

        if guild:
            if not user:
                yield guild.id
                yield "guild"
                yield "moderator"
                yield "admin"
            is_guild_member = type(user) is discord.Member
        else:
            is_guild_member = False

        if not user:
            return

        if user.id in self.client.config.root:
            yield "root"

        if user.bot:
            yield "bot"

        yield "user"

        if is_guild_member:
            yield "member"

            user_roles = (user, *user.roles)

            for object in user_roles:
                yield object.id

            if user.guild_permissions.administrator:
                yield guild.id
                yield "admin"

            if guild.owner == user:
                yield "owner"

            moderators = self.guild_state.config.get("moderators")

            if (
                moderators
                and any(role.id in moderators for role in user_roles)
                or user.guild_permissions.administrator
            ):
                yield "moderator"

            for g in self.client.guilds:
                if g == guild:
                    continue
                member = g.get_member(user.id)
                if member and member.guild_permissions.administrator:
                    yield g.id

        else:
            yield user.id

    @classmethod
    async def generate(cls, client: Client, name: str, *args):
        """
        Guess type and create object.
        """
        object = cls(client, name)

        if "raw" in name and isinstance(args[0], discord.raw_models._RawReprMixin):
            await object.from_raw(name, args[0])

        elif "message" in name:
            if "bulk" in name:
                object.from_bulk_messages(args[-1])
            else:
                if len(args) > 1:
                    args = args[::-1]
                object.from_message(*args)

        elif "reaction" in name:
            if name == "reaction_clear":
                object.from_reaction_clear(*args)
            else:
                object.from_reaction(*args)

        elif name == "ready":
            object.pick_state("default")
            object.launched = True

        elif name == "typing":
            object.from_typing(*args)

        elif "ban" in name:
            object.from_ban(*args)

        elif name == "webhooks_update":
            object.from_hook(*args)

        elif "member" in name or "user" in name:
            if len(args) > 1:
                args = args[::-1]
            object.from_user(*args)

        elif "_channel_" in name:
            channel = args[-1] if "pin" not in name else args[0]
            prev_channel = args[0] if "channel_update" in name else None
            pin = args[0] if "pin" in name else None
            if "guild" in name:
                object.from_guild_channel(channel, prev_channel, pin)
            else:
                object.from_private_channel(channel, prev_channel, pin)

        elif "guild_role" in name:
            if len(args) > 1:
                args = args[::-1]
            object.from_guild_role(*args)

        elif "guild_emojis" in name:
            object.from_guild_emojis(*args)

        elif "guild" in name:
            if len(args) > 1:
                args = args[::-1]
            object.from_guild(*args)

        elif name == "voice_state_update":
            object.from_voice(*args)

        elif "invite" in name:
            object.from_invite(*args)

        elif "group" in name:
            object.from_group(*args)

        elif "relationship" in name:
            if len(args) > 1:
                args = args[::-1]
            object.from_relationship(*args)

        return object

    def from_data(self, **kwargs):
        """
        Generate object from data.
        """
        channel_id = int(kwargs.get("channel_id", 0))
        channel = self.client.get_channel(channel_id)

        guild_id = int(kwargs.get("guild_id", 0))
        guild = self.client.get_guild(guild_id)

        user_id = int(kwargs.get("user_id", 0))
        user = user_id and (
            guild and guild.get_member(user_id) or self.client.get_user(user_id)
        )

        self.temporary_variables = kwargs.get("temp_vars", {})

        self.object = user or guild
        self.user = user
        self.guild = guild
        self.channel = channel

    def from_single(self, object: discord.User | discord.Guild):
        """
        Generate object from single object.
        """
        self.object = object
        setattr(self, type(object).__name__.lower(), object)
        self.channel = (
            object
            if type(object) is discord.User
            else get(object.channels, type="text")
        )

    def from_message(
        self, message: discord.Message, prev_message: Optional[discord.Message] = None
    ):
        """
        Generate object from message event.
        """
        self.object = message
        self.message = message
        self.prev_message = prev_message
        self.guild = message.guild
        self.channel = message.channel
        self.user = message.author

    def from_reaction(
        self, reaction: discord.Reaction, user: Optional[UserType] = None
    ):
        """
        Generate object from reaction event.
        """
        self.object = reaction.message
        self.message = reaction.message
        self.guild = reaction.message.guild
        self.channel = reaction.message.channel
        self.reaction = reaction.emoji
        self.user = user

    def from_reaction_clear(
        self, message: discord.Message, reactions: list[discord.Reaction]
    ):
        """
        Generate object from reaction clear event.
        """
        self.object = message
        self.message = message
        self.guild = message.guild
        self.channel = message.channel
        self.reactions = reactions

    def from_bulk_messages(self, messages: list[discord.Message]):
        """
        Generate object from message event.
        """
        message = messages[0]
        self.object = message.channel
        self.guild = message.guild
        self.channel = message.channel
        self.messages = messages

    async def from_raw(self, name, raw: RawModels):
        """
        Generate object from raw events.
        """
        client = self.client
        raw_attributes = dir(raw)

        if raw.channel_id:
            channel = client.get_channel(raw.channel_id)
            if type(channel) is not discord.DMChannel:
                guild = channel.guild
            else:
                guild = None
        else:
            channel = None
            guild = None

        prev_message = None
        reaction = raw.emoji if "emoji" in raw_attributes else None

        if "message_id" in raw_attributes:
            if (
                name != "raw_message_edit"
                and "cached_message" in raw_attributes
                and raw.cached_message
            ):
                message = raw.cached_message
            else:
                message = None

                if "data" in raw_attributes:
                    try:
                        message = discord.Message(
                            channel=channel, data=raw.data, state=client._connection
                        )
                    except Exception:
                        message = None
                    prev_message = (
                        "cached_message" in raw_attributes
                        and raw.cached_message
                        or None
                    )

                if not message and "delete" not in name and channel:
                    message = get(
                        self.client.cached_messages, id=raw.message_id
                    ) or await try_coro(channel.fetch_message(raw.message_id))

            if "reaction" not in name and message:
                user = message.author
            elif "clear" in name:
                user = None
            elif "user_id" in raw_attributes:
                if guild:
                    user = guild.get_member(raw.user_id) or await try_coro(
                        guild.fetch_member(raw.user_id)
                    )
                else:
                    user = client.get_user(raw.user_id) or await try_coro(
                        client.fetch_user(raw.user_id)
                    )
            else:
                user = None

            messages = None

        elif "cached_messages" in raw_attributes:
            messages = raw.cached_messages
            message = None
            user = None
        else:
            messages = None
            message = None
            user = None

        self.object = (message or channel,)
        self.message = message
        self.prev_message = prev_message
        self.guild = guild
        self.channel = channel
        self.reaction = reaction
        self.user = user
        self.messages = messages

    def from_hook(self, channel: discord.TextChannel):
        """
        Generate object from webhook.
        """
        self.object = channel
        self.channel = channel
        self.guild = channel.guild

    def from_typing(
        self,
        channel: discord.TextChannel | discord.DMChannel,
        user: discord.Member | discord.User,
        when: datetime,
    ):
        """
        Generate object from typing.
        """
        self.object = channel
        self.channel = channel
        self.guild = channel.guild if type(channel) is not discord.DMChannel else None
        self.user = user
        self.when = when

    def from_private_channel(
        self,
        channel: discord.DMChannel | discord.GroupChannel,
        prev_channel: Optional[discord.GroupChannel] = None,
        pin: Optional[discord.Message] = None,
    ):
        """
        Generate object from private channel event.
        """
        self.object = channel
        self.channel = channel
        self.prev_channel = prev_channel
        self.message = pin

    def from_guild_channel(
        self,
        channel: GuildChannelType,
        prev_channel: Optional[GuildChannelType] = None,
        pin: Optional[discord.Message] = None,
    ):
        """
        Generate object from guild channel event.
        """
        self.object = channel
        self.channel = channel
        self.prev_channel = prev_channel
        self.guild = channel.guild
        self.message = pin

    def from_guild_role(
        self, role: discord.Role, perv_role: Optional[discord.Role] = None
    ):
        """
        Generate object from role event.
        """
        self.object = role
        self.role = role
        self.prev_role = perv_role
        self.guild = role.guild

    def from_guild_emojis(
        self,
        guild: discord.Guild,
        prev_emojis: list[discord.Emoji],
        emojis: list[discord.Emoji],
    ):
        """
        Generate object from emojis event.
        """
        self.object = guild
        self.guild = guild
        self.emojis = emojis
        self.prev_emojis = prev_emojis

    def from_user(self, user: UserType, prev_user: Optional[UserType] = None):
        """
        Generate object from member event.
        """
        self.object = user
        self.user = user
        self.prev_user = prev_user
        self.guild = user.guild if type(user) is discord.Member else None

    def from_guild(
        self, guild: discord.Guild, prev_guild: Optional[discord.Guild] = None
    ):
        """
        Generate object from guild event.
        """
        self.object = guild
        self.guild = guild
        self.prev_guild = prev_guild

    def from_ban(self, guild: discord.Guild, user: discord.User):
        """
        Generate object from ban.
        """
        self.object = guild
        self.guild = guild
        self.user = user

    def from_voice(
        self,
        member: discord.Member,
        prev_voice: discord.VoiceState,
        voice: discord.VoiceState,
    ):
        """
        Generate object from voice state.
        """
        self.object = member
        self.user = member
        self.guild = member.guild
        self.voice = voice
        self.prev_voice = prev_voice

    def from_invite(self, invite: discord.Invite):
        """
        Generate object from invite.
        """
        self.object = invite.guild
        self.guild = invite.guild
        self.channel = invite.channel
        self.invite = invite

    def from_group(self, channel: discord.GroupChannel, user: discord.User):
        """
        Generate object from group.
        """
        self.object = channel
        self.channel = channel
        self.user = user

    def from_relationship(
        self,
        relationship: discord.Relationship,
        prev_relationship: Optional[discord.Relationship] = None,
    ):
        """
        Generate object from relationship.
        """
        self.object = relationship.user
        self.user = relationship.user
        self.relationship = relationship
        self.prev_relationship = prev_relationship

    @classmethod
    async def execute(cls, client: Client, event: str, *args, **kwargs) -> Any:
        """
        Implement dispatching in different class
        """
        if not client.real:
            return

        method = "on_" + event

        object = await cls.generate(client, event, *args)

        for e in ("any", event):
            listeners = client._listeners.get(e)
            if not listeners:
                continue

            removed = []
            for i, (future, condition) in enumerate(listeners):
                if future.cancelled():
                    removed.append(i)
                    continue

                try:
                    if object:
                        result = condition(object)
                    else:
                        result = condition(*args)
                except Exception as exc:
                    future.set_exception(exc)
                    removed.append(i)
                else:
                    if result:
                        if object:
                            future.set_result(object)
                        elif len(args) == 0:
                            future.set_result(None)
                        elif len(args) == 1:
                            future.set_result(args[0])
                        else:
                            future.set_result(args)
                        removed.append(i)

            if len(removed) == len(listeners):
                client._listeners.pop(e)
            else:
                for idx in reversed(removed):
                    del listeners[idx]

        if event != "ready":
            await client.fully_ready.wait()
            redirects = (
                getattr(object.guild_state, "redirects", [])
                + ["not_guild"]
                + getattr(object.user_state, "redirects", [])
            )

            if len(redirects) > 1:
                object.guild_only = True
                for func in redirects:
                    if func == "not_guild":
                        object.guild_only = False
                        continue

                    result = await func(object)
                    if result is not None:
                        return result

        for coro in get_events(method):
            name = coro.__self__.name

            client._schedule_event(coro, method + f" from pkg {name!r}", object)

        try:
            coro = getattr(client, "on_any")
        except Exception:
            pass
        else:
            client._schedule_event(coro, f"on_any ({event})", object)

        try:
            coro = getattr(client, method)
        except AttributeError:
            pass
        else:
            client._schedule_event(coro, method, object)

    async def send(self, *args, **kwargs) -> discord.Message:
        """
        Send function to check if event really has object where to send.
        """
        if not self.channel:
            raise NotImplementedError
        return await self.channel.send(*args, **kwargs)

    async def response(self, result: Result) -> None:
        return await (await Response.get(self).append(result)).launch()

    async def safely_finalize(
        self, content: Optional[str] = None, result: Optional[Result] = None
    ) -> None:
        """
        Finalize and send message.
        """
        try:
            if result is None:
                result = await self.finalize(content)
                if result is None:
                    return
            else:
                result = Result(
                    name=content or self.message.system_content, data=[result]
                )
            await self.response(result)

        except NoPrefixError:
            return

        except BaseError as ex:
            print(traceback.format_exc())
            await self.safely_finalize(result=ex)

        except Exception as ex:
            print(traceback.format_exc())
            await self.safely_finalize(result=InternalError(ex))

    async def background_finalize(
        self, *args, processor: Optional[Processor] = None, **kwargs
    ) -> Optional[Result]:
        """
        Launch finalize in controllable task.
        """
        self._task = asyncio.ensure_future(
            self.finalize_specific(processor, *args, **kwargs)
            if processor
            else self.safely_finalize(*args, **kwargs)
        )
        self.state.append_event(self)
        try:
            return await asyncio.wait_for(self._task, None)
        except Exception as ex:
            return Result() << ex
        finally:
            self.state.remove_event(self)

    @property
    def prefixes(self) -> tuple[str, str]:
        prefix = self.get_variable("prefix") or "$"
        mention = self.client.user.mention
        return prefix, mention

    @property
    def prefixed(self) -> bool:
        return self.message.system_content.startswith(self.prefixes)

    def parse_prefix(self, content: str) -> Optional[str]:
        for p in self.prefixes:
            if content.startswith(p):
                return content.removeprefix(p).lstrip()

    @timeit
    async def finalize(self, content: Optional[str] = None) -> Result:
        """
        Process everything including parsing and commands execution.
        """
        if self.user_state:
            await self.user_state.setup(self)

        content = content or self.message.system_content
        if content is None:
            return
        content = content.replace("<@!", "<@")
        content = self.parse_prefix(content)
        if content is None:
            raise NoPrefixError()

        processor = await get_processor(content)
        self.result.set_name(processor.string)
        await processor.finalize(self)

        return self.result

    @timeit
    async def finalize_specific(self, processor: Processor, *args, **kwargs) -> Result:
        self._task = asyncio.ensure_future(processor.finalize(self, *args, **kwargs))
        self.state.append_event(self)
        try:
            return await asyncio.wait_for(self._task, None)
        except Exception as ex:
            return Result() << ex
        finally:
            self.state.remove_event(self)

    async def cancel(self) -> None:
        if self._task:
            self._task.cancel()
        if self.result:
            await self.response(self.result << f"> [{self.pid}] Cancelled!")
