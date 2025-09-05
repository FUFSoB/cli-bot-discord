from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import functools
import inspect
import math
import random
import concurrent.futures
from typing import Any, Awaitable, Optional, Pattern, TYPE_CHECKING
import regex
from models.errors import NotAMentionError, NotAMessageUrlError
import discord
import emojis
import traceback
from dateutil.parser import parse as parse_date
from discord.utils import snowflake_time
import googletrans

if TYPE_CHECKING:
    from .typings import EmojiType, Some, SomeSyncCallable, SomeCallable

__all__ = (
    "classproperty",
    "try_coro",
    "timeit",
    "unescape",
    "print_return",
    "always_true",
    "convert_bytes",
    "get_discord_id",
    "try_get_discord_id",
    "try_get_discord_obj_or_date",
    "NoneType",
    "get_message_url",
    "try_get_message_url",
    "run_in_executor",
    "aexec",
    "random_bool",
    "get_discord_repr",
    "get_discord_str",
    "get_dir_str",
    "get_discord_image",
    "tryit",
    "emoji_list",
    "get_name",
    "get_pair",
    "get_pair_not_strict",
    "get_time",
    "get_date",
    "translator",
)

emoji_list: list[str] = list(emojis.emojis.EMOJI_TO_ALIAS)
as_patial_emoji_list = [discord.PartialEmoji(name=e) for e in emoji_list]

NoneType = type(None)

loop = asyncio.get_event_loop()

translator = googletrans.Translator()


class classproperty:
    def __init__(self, func):
        self.fget = func

    def __get__(self, instance, owner):
        return self.fget(owner)


async def try_coro(coro: Awaitable[Some], default: Optional[Any] = None) -> Some:
    """
    Function to easily use client.fetch_* functions in "or" expressions.
    """
    try:
        return await coro
    except Exception:
        return default


def timeit(func: SomeCallable):
    """
    Wrap a function to calculate timings.
    """
    func_name = func.__module__ + "." + func.__qualname__

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def inner(*args, **kwargs) -> Some:
            start = datetime.now()
            result = await func(*args, **kwargs)
            end = datetime.now()
            difference = end - start
            print(
                "coro:\033[94m"
                f"{func_name}\033[0m "
                f"took: \033[94m{difference}"
                "\033[0m"
            )
            # setattr(result, "__timeit", difference)
            return result

    else:

        @functools.wraps(func)
        def inner(*args, **kwargs) -> Some:
            start = datetime.now()
            result = func(*args, **kwargs)
            end = datetime.now()
            difference = end - start
            print(
                "func:\033[94m"
                f"{func_name}\033[0m "
                f"took: \033[94m{difference}"
                "\033[0m"
            )
            # setattr(result, "__timeit", difference)
            return result

    return inner


def print_return(func: SomeCallable):
    """
    Wrap a function to print return value.
    """
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def wrap(*args, **kwargs) -> Some:
            result = await func(*args, **kwargs)
            print(repr(result))
            return result

    else:

        @functools.wraps(func)
        def wrap(*args, **kwargs) -> Some:
            result = func(*args, **kwargs)
            print(repr(result))
            return result

    return wrap


def tryit(func: SomeCallable):
    """
    Wrap a function to try full function.
    """
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def wrap(*args, **kwargs) -> Some | Exception:
            try:
                result = await func(*args, **kwargs)
            except Exception as ex:
                print(traceback.format_exc())
                result = ex
            return result

    else:

        @functools.wraps(func)
        def wrap(*args, **kwargs) -> Some | Exception:
            try:
                result = func(*args, **kwargs)
            except Exception as ex:
                print(traceback.format_exc())
                result = ex
            return result

    return wrap


def unescape(text: str) -> str:
    """
    Expand some special symbols
    """
    return text.replace("\\n", "\n")  # .replace("\\t", "\t")


class AlwaysTrue:
    def __bool__(self):
        return True

    def __contains__(self, other):
        return True


always_true = AlwaysTrue()


def convert_bytes(units: int) -> str:
    """
    Tool to convert bytes integer into human-readable string
    """
    value, size_name = 1024, ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")

    if units == 0:
        return f"0.0{size_name[0]}"

    i = int(math.floor(math.log(units, value)))
    p = math.pow(value, i)
    s = round(units / p, 2)

    return "%s%s" % (s, size_name[i])


discord_id_regex: Pattern = regex.compile(r"(\d{17,19})>?$")


def get_discord_id(value: str) -> int:
    """
    Get Discord ID from either mention or text
    """
    try:
        return int(discord_id_regex.search(value)[1])
    except Exception:
        raise NotAMentionError(value)


def try_get_discord_id(value: str) -> int | str:
    """
    Get Discord ID, but return input value if failed
    """
    try:
        return get_discord_id(value)
    except Exception:
        return value


def try_get_discord_obj_or_date(value: str) -> discord.Object | datetime:
    """
    Get either discord or datetime object from value.
    """
    try:
        new = get_discord_id(value)
    except Exception:
        new = parse_date(value).astimezone(timezone.utc).replace(tzinfo=None)
    else:
        new = discord.Object(new)
    return new


def get_date(value: str) -> datetime:
    """
    Get datetime object from discord-like or date-like string.
    """
    try:
        return snowflake_time(get_discord_id(value))
    except Exception:
        return parse_date(value)


message_url_regex: Pattern = regex.compile(r"(?:(\d{17,19})/)?(\d{17,19})$")


def get_message_url(value: str) -> tuple[int, ...]:
    """
    Get channel and message ID from url or `channel/message` string
    """
    try:
        channel, message = message_url_regex.search(value).groups()
    except Exception:
        raise NotAMessageUrlError(value)
    else:
        return channel and int(channel), int(message)


def try_get_message_url(value: str) -> tuple[int, ...] | tuple[None, str]:
    """
    Get channel and message ID, but return input value if failed
    """
    try:
        return get_message_url(value)
    except Exception:
        return (None, value)


executor = concurrent.futures.ThreadPoolExecutor()


def run_in_executor(func: SomeSyncCallable):
    """
    Decorator to make blocking functions non-blocking
    """

    @functools.wraps(func)
    def inner(*args, **kwargs) -> Awaitable[Some]:
        return loop.run_in_executor(executor, lambda: func(*args, **kwargs))

    return inner


async def aexec(code: str, **kwargs) -> Any:
    """
    Hack to implement async exec function
    """
    exec(
        "async def __ex(): " + "".join(f"\n {i}" for i in code.split("\n")),
        kwargs,
        locals(),
    )

    return await locals()["__ex"]()


def random_bool(rate: float = 50) -> bool:
    return random.random() < (rate / 100)


def get_discord_repr(object: Any) -> str | None:
    type_ = type(object)

    if type_ in (discord.Message, discord.PartialMessage):
        return object.jump_url
    elif type_ is discord.Guild:
        return object.default_role.mention
    elif type_ in (discord.Emoji, discord.PartialEmoji):
        return str(object)
    elif "mention" in dir(object):
        return object.mention
    else:
        return None


def get_discord_str(object: Any) -> str:
    type_ = type(object)

    if type_ is discord.Spotify:
        return f"{object.title} — {object.artist}"
    elif isinstance(object, discord.BaseActivity) or type_ in (
        discord.Emoji,
        discord.PartialEmoji,
    ):
        return object.name
    elif type_ in (discord.Message, discord.PartialMessage, discord.Object):
        return type_.__name__
    elif type_ is discord.Webhook:
        return object.name + "#0000"
    else:
        return str(object)


def get_dir_str(object: Any) -> str:
    type_ = type(object)

    if type_ is discord.Spotify or isinstance(object, discord.BaseActivity):
        return type_.__name__.lower()
    elif type_ in (discord.Emoji, discord.PartialEmoji):
        return object.name
    elif type_ is discord.Reaction:
        return object.emoji if type(object.emoji) is str else object.emoji.name
    elif type_ is discord.Embed:
        return "embed"
    elif type_ is discord.Attachment:
        return "attachment"
    else:
        return str(object)


def resolve_partial_emoji_image(object: EmojiType, name: bool = False) -> str:
    name = name and object or object.name

    if name in emoji_list:
        title = "".join(f"{ord(y):x}" for y in name)
        return f"http://files.fufsob.ru/emojis/{title}.png"
    else:
        return str(object.url)


def get_discord_image(object: Any) -> str | None:
    type_ = type(object)

    if type_ is discord.Guild:
        return str(object.icon_url_as(static_format="png"))

    elif isinstance(object, (discord.abc.User, discord.Webhook)):
        return str(object.avatar_url_as(static_format="png"))

    elif type_ is discord.Emoji:
        return str(object.url)

    elif type_ is discord.PartialEmoji:
        return resolve_partial_emoji_image(object)

    elif type_ is discord.Reaction:
        emoji = object.emoji
        if type(emoji) in (str, discord.PartialEmoji):
            return resolve_partial_emoji_image(emoji, type(emoji) is str)

        return str(emoji.url)

    elif type_ is discord.Spotify:
        return object.album_cover_url

    elif type_ is discord.Activity:
        return object.large_image_url

    elif type_ is discord.Color:
        return f"http://www.singlecolorimage.com/get/{object.value:x}/100x100"

    elif type_ is discord.Streaming and object.twitch_name:
        return (
            "https://static-cdn.jtvnw.net/"
            f"previews-ttv/live_user_{object.twitch_name}-1600x900.jpg"
        )

    else:
        return None


def get_name(name: str, names: list[str]) -> str:
    number = 1
    prev_name = name

    while name in names:
        name = f"{prev_name} ({number})"
        number += 1

    return name


# pair_regex: Pattern = regex.compile(r"(.+?)=(.*)", regex.DOTALL)


def get_pair(string: str) -> tuple[str, str]:
    # match = pair_regex.match(string)
    # if not match:
    #     raise ValueError("must be a key-pair value")
    # return match.groups()
    result = string.split("=", 1)
    if len(result) < 2:
        raise ValueError("must be a key-pair value")

    return tuple(result)


def get_pair_not_strict(string: str) -> tuple[str, str | None]:
    result = string.split("=", 1)
    if len(result) == 1:
        result += [None]

    return tuple(result)


time_regex: Pattern = regex.compile(r"(\d+(?:\.?\d*)|(?:\.\d+))([smhdwMy])?")
time_suffixes: dict[str, float] = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 60 * 60 * 24,
    "w": 60 * 60 * 24 * 7,
    "M": 60 * 60 * 24 * 30,
    "y": 60 * 60 * 24 * 365.25,
}


def get_time(value: str) -> float:
    found: list[tuple[str, str | None]] = time_regex.findall(value)
    return sum(float(m[0]) * time_suffixes[m[1] or "s"] for m in found)
