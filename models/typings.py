from __future__ import annotations

from abc import ABCMeta
from typing import Any, Callable, Coroutine, Optional, TypeVar, Union
import discord
from .packages import Command
from .state import UserState, GuildState, DefaultState
from structure.filesystem import (
    Directory,
    Link,
    Generator,
    GeneratedDirectory,
    HomePointer,
    HomeDirectory,
    NetworkDirectory,
    RootDirectory,
    FilterDirectory,
)  # directory types
from structure.filesystem import RegularFile, GeneratedFile, NetworkFile  # file types
from parser.wrapper import (
    Command as CommandWrapper,
    Word,
    List,
    Operator,
    Pipeline,
    Pipe,
    Redirect,
    Assignment,
    Parameter,
    Compound,
    Reservedword,
    If,
    For,
    Loop,
    Function,
    Tilde,
    Substitution,
    Expression,
)  # Wrappers
from models.event import Event
from parser.wrapper import Result
from argparse import Namespace
from models.extra import Segment, Pointer, Matcher

if False:
    FunctionType = Function | Command

    StateObject = discord.User | discord.Guild | discord.Object
    GetStateObject = discord.User | discord.Guild | discord.Member | int
    StateType = UserState | GuildState
    AllStateType = UserState | GuildState | DefaultState

    DirectoryType = (
        Directory
        | Link
        | Generator
        | GeneratedDirectory
        | HomePointer
        | HomeDirectory
        | NetworkDirectory
        | RootDirectory
        | FilterDirectory
    )
    FileType = RegularFile | GeneratedFile | NetworkFile
    GeneratedType = Generator | GeneratedDirectory | GeneratedFile
    NetworkType = NetworkDirectory | NetworkFile
    GeneratedNetworkType = GeneratedType | NetworkType
    BasicFileType = RegularFile | Directory | Link | HomeDirectory
    AllFilesType = DirectoryType | FileType

    GuildChannelType = (
        discord.TextChannel | discord.VoiceChannel | discord.CategoryChannel
    )
    ChannelType = GuildChannelType | discord.DMChannel | discord.GroupChannel
    UserType = discord.Member | discord.User | discord.ClientUser

    RawModels = (
        discord.RawBulkMessageDeleteEvent
        | discord.RawMessageDeleteEvent
        | discord.RawMessageUpdateEvent
        | discord.RawReactionActionEvent
        | discord.RawReactionClearEmojiEvent
        | discord.RawReactionClearEvent
    )

    WrapperType = (
        CommandWrapper
        | Word
        | List
        | Operator
        | Pipeline
        | Pipe
        | Redirect
        | Assignment
        | Parameter
        | Compound
        | Reservedword
        | If
        | For
        | Loop
        | Function
        | Tilde
        | Substitution
        | Expression
    )

    StdoutCallable = Callable[[str | bytes], Coroutine[Any, Any, None]]

    EmojiType = discord.Emoji | discord.PartialEmoji

    FindType = (
        discord.Member
        | discord.User
        | discord.Guild
        | discord.TextChannel
        | discord.VoiceChannel
        | discord.CategoryChannel
        | discord.Emoji
        | discord.Role
    )

    GetType = (
        FindType
        | discord.Message
        | discord.Webhook
        | discord.Object
        | discord.Color
        | discord.PartialEmoji
    )

    DataClassesType = (
        discord.Permissions
        | discord.PermissionOverwrite
        | discord.BaseActivity
        | discord.Spotify
        | discord.Emoji
        | discord.PartialEmoji
        | discord.PublicUserFlags
        | discord.Embed
        | discord.Attachment
    )

    GeneratorDataType = GetType | DataClassesType

    Some = TypeVar("Some")
    Other = TypeVar("Other")
    Key = TypeVar("Key")

    def SomeSyncCallable(*args: Any, **kwargs: Any) -> Some: ...
    async def SomeAsyncCallable(*args: Any, **kwargs: Any) -> Some: ...

    # SomeSyncCallable = Callable[..., Some]
    # SomeAsyncCallable = Callable[..., Coroutine[Any, Any, Some]]
    SomeCallable = Union[SomeSyncCallable, SomeAsyncCallable]

    async def SomeCommandCallable(
        cls: Command, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> Some: ...

    # SomeCommandCallable = Callable[
    #     [Command, Event, Namespace, Result],
    #     Coroutine[Any, Any, Some]
    # ]

    def SomeCommandCallableEventSync(
        cls: Command, event: Event, *args: Any, **kwargs: Any
    ) -> Some: ...

    async def SomeCommandCallableEventAsync(
        cls: Command, event: Event, *args: Any, **kwargs: Any
    ) -> Some: ...

    SomeCommandCallableEvent = Union[
        SomeCommandCallableEventSync, SomeCommandCallableEventAsync
    ]

    GetterType = Segment | Pointer | Matcher

    RecursiveJson = dict[str, Some | "RecursiveJson"]
    RecursiveDict = dict[Key, Some | "RecursiveDict"]
    BackJson = dict[Some | "RecursiveJson", str]
    BackDict = dict[Some | "RecursiveDict", Key]

    RecursiveList = list[Some | "RecursiveList"]
    BackList = dict[Some | "RecursiveList", int]

    MatchType = dict[Key, Some] | list[Some]

    class HasGuild(metaclass=ABCMeta):
        guild: discord.Guild
