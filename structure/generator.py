from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from inspect import ismethod, iscoroutinefunction, getfullargspec, iscoroutine
from discord.abc import Snowflake, GuildChannel
from discord import (
    Permissions,
    PermissionOverwrite,
    Reaction,
    iterators as discord_iterators,
    BaseActivity,
    Spotify,
    Emoji,
    PartialEmoji,
    Guild,
    Member,
    Status,
    ChannelType,
    PublicUserFlags,
    Embed,
    Attachment,
)
from .permissions import Mode
from models.utils import (
    get_discord_repr,
    get_discord_str,
    get_dir_str,
    get_discord_image,
    get_name as _get_name,
)
import os
from datetime import datetime

if TYPE_CHECKING:
    from .filesystem import Generator, Directory
    from models.event import Event
    from models.bot import Client
    from models.typings import GeneratorDataType, DataClassesType

__all__ = (
    "generate_binaries",
    "generate_clients",
    "generate_object_by_id",
    "generate_object_by_name",
    "generate_object_by_type",
    "read_local_files",
)


data_classes = (
    Permissions,
    PermissionOverwrite,
    BaseActivity,
    Spotify,
    Emoji,
    PartialEmoji,
    PublicUserFlags,
    Embed,
    Attachment,
)


def get_name(name: str, names: list[str]) -> str:
    name = _get_name(name, names)
    names.append(name)
    return name


async def generate_binaries(
    generator: Generator, event: Event, name: Optional[str] = None
):
    from models.packages import get_commands

    for command in get_commands():
        yield await generator.create("file", command.name, content=command, event=True)


async def read_local_files(directory: Directory, event: Event):
    for name in os.listdir("scripts"):
        with open(f"scripts/{name}", "r") as fp:
            file = await directory.create("file", name, content=fp.read(), event=True)
        yield file

        if name.endswith(".command"):
            await file.parse_as_command(event=event)


async def generate_clients(
    generator: Generator, event: Event, name: Optional[str] = None
):
    from models.bot import clients

    for client in clients:
        yield await generator.create(
            "generator",
            client.name,
            function=generate_client_object,
            extra=(client,),
            event=True,
        )


async def generate_client_object(
    generator: Generator,
    event: Event,
    name: Optional[str] = None,
    client: Optional[Client] = None,
):
    if not client:
        return

    for name in ("users", "guilds", "emojis", "cached_messages"):
        yield await generator.create(
            "generator",
            name,
            function=generate_objects_from_list,
            extra=(getattr(client, name),),
            event=True,
        )

    yield await generator.create(
        "generator", "get", function=generate_object_by_id, extra=(client,), event=True
    )
    yield await generator.create(
        "generator",
        "find",
        function=generate_object_by_name,
        extra=(client,),
        event=True,
    )


async def generate_object_by_id(
    generator: Generator,
    event: Event,
    name: Optional[str] = None,
    guild: Optional[Guild] = None,
):
    if not name:
        return

    yield await generator.create(
        "generator", name, function=generate_object, extra=(guild, True), event=True
    )


async def generate_object_by_name(
    generator: Generator,
    event: Event,
    name: Optional[str] = None,
    guild: Optional[Guild] = None,
):
    if not name:
        return

    yield await generator.create(
        "generator", name, function=find_object, extra=(guild,), event=True
    )


async def generate_object_by_type(directory: Directory):
    for name in ("user", "guild", "channel", "message"):
        yield await directory.create("generator", name, function=get_object, event=True)


other_types = {"colour": "color"}


async def generate_object(
    generator: Generator,
    event: Event,
    name: Optional[str] = None,
    object: Optional[GeneratorDataType | Client] = None,
    scope: bool = False,
):
    if not object:
        object = await event.client.fetch_object(generator.name, event)
    elif type(object).__name__ == "Client":
        object = await object.fetch_object(generator.name, event)
    elif scope:
        object = await event.client.fetch_object(generator.name, event, guild=object)

    attrs = dir(object)

    if "id" in attrs:
        owner = object.id or "any" if type(object) is not Reaction else "admin"

        mode = Mode(
            0o755,
            owner,
            ("guild" in attrs and object.guild and object.guild.id or owner),
        )
    else:
        mode = None

    for attr in attrs:
        if attr.startswith("_"):
            continue

        try:
            value = getattr(object, attr)
        except AttributeError:
            continue

        if value is None:
            continue

        if ismethod(value):
            if iscoroutinefunction(value) or isinstance(
                value, discord_iterators._AsyncIterator
            ):
                continue

            from_func = True
        else:
            from_func = False

        type_ = type(value)

        if type_ in (tuple, list, set) and attr not in ("features",):
            file = await generator.create(
                "generator",
                attr,
                function=generate_objects_from_list,
                extra=(value,),
                event=True,
            )

        elif isinstance(value, Snowflake) or type_ in (Reaction,):
            file = await generator.create(
                "generator",
                attr,
                mode=mode,
                function=generate_object,
                extra=(value,),
                event=True,
            )

        elif issubclass(type_, data_classes):
            if type_ in (Permissions, PermissionOverwrite):
                attr = "permissions"

            file = await generator.create(
                "generator",
                attr,
                mode=mode,
                function=generate_data_class,
                extra=(value,),
                event=True,
            )

        else:
            if from_func:
                if len(getfullargspec(value).args) <= 1:
                    try:
                        value = value()
                    except Exception:
                        continue

                    if iscoroutine(value):
                        value.close()
                        continue

                    elif isinstance(
                        value, discord_iterators._AsyncIterator
                    ) or "__enter__" in dir(value):
                        continue

                    type_ = type(value)

                else:
                    continue

            else:
                if type_ not in (datetime, bool, list):
                    value = str(value)

            file = await generator.create(
                "file", attr, mode=mode, content=value, event=True
            )

        yield file

    if type(object) is Guild:
        yield await generator.create(
            "generator",
            "get",
            function=generate_object_by_id,
            extra=(object,),
            event=True,
        )
        yield await generator.create(
            "generator",
            "find",
            function=generate_object_by_name,
            extra=(object,),
            event=True,
        )

    type_name = type(object).__name__.lower()
    yield await generator.create(
        "file",
        ".type",
        mode=mode,
        content=other_types.get(type_name, type_name),
        event=True,
    )
    yield await generator.create("file", ".object", content=object, event=True)

    if discord_repr := get_discord_repr(object):
        yield await generator.create(
            "file", ".discord", mode=mode, content=discord_repr, event=True
        )

    yield await generator.create(
        "file", ".str", mode=mode, content=get_discord_str(object), event=True
    )

    if asset := get_discord_image(object):
        yield await generator.create(
            "file", ".image_url", mode=mode, content=asset, event=True
        )

        filename = asset.rsplit("/", 1)[-1]
        ext = filename.rsplit(".", 1)[-1].split("?", 1)[0]
        if ext == filename:
            ext = "png"

        yield await generator.create(
            "network_file", f".image.{ext}", mode=mode, content=asset, event=True
        )

        if ext == "gif":
            yield await generator.create(
                "network_file",
                ".image.png",
                mode=mode,
                content=asset.replace(".gif", ".png", 1),
                event=True,
            )


async def find_object(
    generator: Generator,
    event: Event,
    name: Optional[str] = None,
    object: Optional[Guild | Client] = None,
):
    names = []
    if type(object).__name__ == "Client":
        iterator = object.find_object(generator.name, event, guild=False)
    else:
        iterator = event.client.find_object(generator.name, event, guild=object)

    async for object in iterator:
        yield await generator.create(
            "generator",
            get_name(get_dir_str(object), names),
            function=generate_object,
            extra=(object,),
            event=True,
        )

    yield await generator.create("file", ".type", content="list", event=True)
    yield await generator.create("file", ".object", content=names, event=True)
    yield await generator.create("file", ".count", content=len(names), event=True)


def get_object(generator: Generator, event: Event, name: Optional[str] = None):
    object = getattr(event, generator.name)

    return generate_object(generator, event, None, object)


async def generate_objects_from_list(
    generator: Generator,
    event: Event,
    name: Optional[str] = None,
    lst: list[GeneratorDataType] = [],
):
    names = []

    for object in lst:
        if "id" in dir(object):
            owner = object.id or "any" if type(object) is not Reaction else "admin"
            mode = Mode(
                0o755,
                owner,
                ("guild" in dir(object) and object.guild and object.guild.id or owner),
            )
        else:
            mode = None

        yield await generator.create(
            "generator",
            get_name(get_dir_str(object), names),
            mode=mode,
            function=(
                generate_object
                if not type(object) in data_classes
                else generate_data_class
            ),
            extra=(object,),
            event=True,
        )

    yield await generator.create("file", ".type", content="list", event=True)
    yield await generator.create("file", ".object", content=lst, event=True)

    total_number = len(names)
    yield await generator.create("file", ".count", content=total_number, event=True)

    if not lst:
        return

    if isinstance(lst[0], Member):

        def bots():
            return len([m for m in lst if m.bot])

        def online():
            return len([m for m in lst if m.status != Status.offline])

        yield await generator.create(
            "file", ".online_count", content=online, event=True
        )
        yield await generator.create(
            "file",
            ".offline_count",
            content=lambda: total_number - online(),
            event=True,
        )
        yield await generator.create("file", ".bot_count", content=bots, event=True)
        yield await generator.create(
            "file", ".user_count", content=lambda: total_number - bots(), event=True
        )

    elif isinstance(lst[0], GuildChannel):
        yield await generator.create(
            "generator",
            ".voice",
            function=generate_objects_from_list,
            extra=([c for c in lst if c.type == ChannelType.voice],),
            event=True,
        )
        yield await generator.create(
            "generator",
            ".text",
            function=generate_objects_from_list,
            extra=([c for c in lst if c.type == ChannelType.text],),
            event=True,
        )
        yield await generator.create(
            "generator",
            ".category",
            function=generate_objects_from_list,
            extra=([c for c in lst if c.type == ChannelType.category],),
            event=True,
        )


bools = {True: "true", False: "false", None: "null"}


async def generate_data_class(
    generator: Generator,
    event: Event,
    name: Optional[str] = None,
    object: Optional[DataClassesType] = None,
):
    type_ = type(object)

    if type_ in (Permissions, PermissionOverwrite, PublicUserFlags):
        for name, value in object:
            yield await generator.create(
                "file", name, content=bools[value].lower(), event=True
            )

    elif type_ is Embed:
        yield await generator.create(
            "file", "to_dict", content=object.to_dict, event=True
        )

    elif type_ is Attachment:
        for attr in (
            "filename",
            "id",
            "size",
            "url",
            "proxy_url",
            "width",
            "height",
            "is_spoiler",
        ):
            value = getattr(object, attr)
            if attr == "is_spoiler":
                value = value()
            yield await generator.create("file", attr, content=value, event=True)
        yield await generator.create(
            "network_file",
            ".content" + object.filename.rsplit(".", 1)[-1],
            content=object.url,
            event=True,
        )
        yield await generator.create(
            "network_file",
            ".file." + object.filename.rsplit(".", 1)[-1],
            content=object.url,
            event=True,
        )

    else:
        async for file in generate_object(generator, event, name, object):
            yield file

    yield await generator.create(
        "file", ".type", content=type_.__name__.lower(), event=True
    )
    yield await generator.create("file", ".object", content=object, event=True)
