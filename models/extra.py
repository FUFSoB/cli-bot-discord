from __future__ import annotations

import functools
from typing import (
    Any,
    Callable,
    Coroutine,
    Mapping,
    Match,
    Optional,
    Pattern,
    TYPE_CHECKING,
    overload,
)
import discord
from discord.utils import sleep_until
from .errors import (
    MissingRequiredStdinError,
    MissingRequiredOptionError,
    MissingRequiredArgumentError,
    CommandPermissionError,
    ConversionError,
    ObjectUnavailableError,
)
from random import randrange, choice
from .utils import (
    get_discord_id,
    try_get_discord_id,
    emoji_list,
    NoneType,
    get_time,
    get_date,
    get_pair,
)
import ujson
import ast
from inspect import iscoroutinefunction, isawaitable, isfunction
import asyncio
import regex
import shlex

if TYPE_CHECKING:
    from models.event import Event
    from parser.wrapper import Result
    from .packages import Command
    from argparse import Namespace
    from models.typings import (
        Other,
        StateType,
        Some,
        SomeCommandCallable,
        SomeCommandCallableEvent,
        RecursiveJson,
        RecursiveList,
        MatchType,
        # RecursiveDict,
        BackJson,
        BackList,
        # BackDict
    )
    from models.bot import Client

__all__ = (
    "types",
    "convert_type",
    "convert_type_fab",
    "get_pair_and_convert",
    "required",
    "has_group",
    "has_object",
    "Segment",
    "Pointer",
    "Setup",
    "Deferred",
    "DynamicDictionary",
    "get_type",
    "Timer",
    "Schedule",
)


def convert_type(command: Command | str, name: str, value: str) -> Any:
    try:
        return types[name](value)
    except Exception:
        raise ConversionError(command, name)


def convert_type_fab(command: Command | str, name: str):
    def convert(value):
        return convert_type(command, name, value)

    return convert


single_regex: Pattern.match = regex.compile(
    r"(?:^([a-z_]+?)(?<!\\)\:)?(.+?)(?<!\\)(?:\:([a-z_]+?))$", regex.MULTILINE
).match
split_double: Pattern.match = regex.compile(
    r"^([a-z_]+?)(?<!\\)::(.*)", regex.DOTALL
).match


def get_pair_and_convert(string: str) -> tuple[str | Any, str | Any]:
    pair = get_pair(string)

    mbtype_name_and_type = single_regex(pair[0])
    if not mbtype_name_and_type:
        return pair

    *name, type_ = mbtype_name_and_type.groups()
    if not name[0]:
        name = name[1].strip()
    else:
        try:
            name = types[name[0]](name[1])
        except Exception:
            raise ValueError(f"cannot convert key into {name[0]}")

    type_ = type_.strip()
    value = pair[1]

    try:
        value = types[type_](value)
    except Exception:
        raise ValueError(f"cannot convert value into {type_}")

    return name, value


def get_array(string: str) -> list[str | Any]:
    type_and_values = split_double(string)
    if not type_and_values:
        return shlex.split(string)

    type_, values = type_and_values.groups()
    type_ = type_.strip()
    try:
        conv = types[type_]
        return [conv(v) for v in shlex.split(values)]
    except Exception:
        raise ValueError(f"cannot convert values into {type_}")


types = {
    "int": int,
    "str": str,
    "float": float,
    "ord": ord,
    "chr": chr,
    "id": get_discord_id,
    "try_id": try_get_discord_id,
    "list": list,
    "json": ujson.loads,
    "ast": ast.literal_eval,
    "time": get_time,
    "date": get_date,
    "null": lambda _: None,
    "embed": lambda x: discord.Embed.from_dict(ast.literal_eval(x)),
    "bytes": lambda x: (
        ast.literal_eval(x) if type(x) is str and x.startswith("b'") else bytes(x)
    ),
    "object": lambda x: discord.Object(x),
    "mapping": lambda x: dict(get_pair_and_convert(i) for i in shlex.split(x)),
    "array": get_array,
    "permissions": lambda x: discord.PermissionOverwrite(**ast.literal_eval(x)),
}


def required(
    *names: str, actual: Optional[str] = None, option: bool = False
):  # TODO typings
    def raise_exception(cls: Command, name: str):
        if name == "stdin":
            raise MissingRequiredStdinError(cls.name)
        else:
            if option:
                raise MissingRequiredOptionError(cls.name, actual or name)
            else:
                raise MissingRequiredArgumentError(cls.name, actual or name)

    def inner(func: SomeCommandCallable):
        @functools.wraps(func)
        async def wrap(
            cls: Command, event: Event, args: Namespace, stdin: Result
        ) -> Some:
            if not any(
                (
                    bool(stdin)
                    if name == "stdin"
                    else getattr(args, name) not in (None, [])
                )
                for name in names
            ):
                raise_exception(cls, names[-1])

            result = await func(cls, event, args, stdin)
            return result

        return wrap

    return inner


def has_group(*groups: str | int):
    def inner(func: SomeCommandCallableEvent):
        if iscoroutinefunction(func):

            @functools.wraps(func)
            async def wrap(cls: Command, event: Event, *args, **kwargs) -> Some:
                for name in groups:
                    if name in event.groups():
                        break
                else:
                    if "root" not in event.groups():
                        raise CommandPermissionError(cls, groups[-1])

                return await func(cls, event, *args, **kwargs)

        else:

            @functools.wraps(func)
            def wrap(cls: Command, event: Event, *args, **kwargs) -> Some:
                for name in groups:
                    if name in event.groups():
                        break
                else:
                    if "root" not in event.groups():
                        raise CommandPermissionError(cls, groups[-1])

                return func(cls, event, *args, **kwargs)

        return wrap

    return inner


def has_object(name: str, kwarg: bool = False):
    def inner(func: SomeCommandCallableEvent):
        if iscoroutinefunction(func):

            @functools.wraps(func)
            async def wrap(cls: Command, event: Event, *args, **kwargs) -> Some:
                if kwargs.get(name) is None if kwarg else not getattr(event, name):
                    raise ObjectUnavailableError(cls, name)

                return await func(cls, event, *args, **kwargs)

        else:

            @functools.wraps(func)
            def wrap(cls: Command, event: Event, *args, **kwargs) -> Some:
                if kwargs.get(name) is None if kwarg else not getattr(event, name):
                    raise ObjectUnavailableError(cls, name)

                return func(cls, event, *args, **kwargs)

        return wrap

    return inner


class Getter:
    def random(self):
        raise NotImplementedError

    def get(self, object):
        raise NotImplementedError

    def place(self, object, value):
        raise NotImplementedError

    def pop(self, object):
        raise NotImplementedError

    def insert(self, final, value):
        raise NotImplementedError


class Segment(Getter):
    start: int | None
    stop: int | None
    step: int | None

    def __init__(self, *args: int | str | None):
        self.start, self.stop, self.step = args
        self.ord = False

        try:
            self.stop = int(self.stop)
        except Exception:
            if self.stop:
                self.stop = ord(self.stop)
                self.ord = True
            else:
                self.stop = None

        if self.start is not None:
            try:
                assert not self.ord
                self.start = int(self.start)
            except (ValueError, AssertionError):
                self.start = ord(self.start)
                self.ord = True

    def __str__(self):
        if self.start is not None:
            return f"{self.start}:{self.stop}:{self.step or 1}"
        else:
            return str(self.stop)

    def __repr__(self):
        return f"Segment{self.start, self.stop, self.step}"

    def __iter__(self):
        if not self.ord:
            yield from range(self.start or 0, self.stop + 1, self.step or 1)
        else:
            for i in range(self.start or 0, self.stop + 1, self.step or 1):
                yield chr(i)

    async def __aiter__(self):
        for i in range(self.start or 0, self.stop + 1, self.step or 1):
            yield chr(i) if self.ord else i

    @property
    def slice(self) -> slice | int:
        if self.start is None:
            return self.stop or 0
        return slice(self.start, self.stop, self.step)

    def random(self) -> int:
        return randrange(self.start or 0, self.stop + 1, self.step or 1)

    @classmethod
    def from_string(cls, string: str) -> "Segment":
        if not string:
            raise ValueError("string cannot be empty")

        parts = string.split(":")
        if len(parts) == 1:
            return cls(None, parts[0], None)

        parts = [x or None for x in parts]

        if parts[0] is None:
            parts[0] = 0

        if len(parts) < 3:
            parts += [None]
        elif len(parts) > 3:
            raise ValueError("improper string passed")
        else:
            parts[2] = int(parts[2])

        return cls(*parts)

    def get(self, final: list[Some]) -> list[Some] | Some:
        return final[self.slice]

    def place(self, final: list[Some], value: Other) -> list[Some | Other]:
        final[self.slice] = value
        return final

    def pop(self, final: list[Some]) -> list[Some] | Some:
        data = final[self.slice]
        del final[self.slice]
        return data

    def insert(self, final: list[Some], value: Other) -> list[Some | Other]:
        final.insert(self.slice, value)
        return final


class Pointer(Getter):
    def __init__(self, *keys: str, reverse: bool = False):
        self.keys = keys
        self.reverse = reverse

    def __str__(self):
        return "\n".join(self.keys)

    def __repr__(self):
        return f"Pointer{self.keys}"

    def __iter__(self):
        yield from self.keys

    async def __aiter__(self):
        for key in self.keys:
            yield key

    def random(self) -> str:
        return choice(self.keys)

    @overload
    def check_reverse(
        self, final: dict[str, Some]
    ) -> dict[str, Some] | dict[Some, str]: ...

    @overload
    def check_reverse(self, final: list[Some]) -> dict[Some, int]: ...

    def check_reverse(self, final: dict[str, Some] | list[Some]):
        if self.reverse:
            if type(final) is list:
                final = {v: n for n, v in enumerate(final)}
            else:
                final = {v: k for k, v in final.items()}
        return final

    @overload
    def get(self, final: RecursiveJson) -> Some | str: ...

    @overload
    def get(self, final: RecursiveList) -> int: ...

    def get(self, final: RecursiveJson | RecursiveList):  # TODO typings
        for key in self.keys:
            final = self.check_reverse(final)
            final = final[key]
        return final

    @overload
    def place(self, final: RecursiveJson) -> RecursiveJson | BackJson: ...

    @overload
    def place(self, final: RecursiveList) -> BackList: ...

    def place(self, final: RecursiveJson | RecursiveList, value: Some):
        for key in self.keys[:-1]:
            final = self.check_reverse(final)
            final = final[key]

        final[self.keys[-1]] = value
        return final

    @overload
    def pop(self, final: RecursiveJson) -> Some | str: ...

    @overload
    def pop(self, final: RecursiveList) -> int: ...

    def pop(self, final: RecursiveJson | RecursiveList):
        for key in self.keys[:-1]:
            final = self.check_reverse(final)
            final = final[key]

        return final.pop(self.keys[-1])

    insert = place


class Matcher(Getter):
    def __init__(
        self,
        *pairs: tuple,
        array: bool = False,
        single: bool = False,
        all: bool = True,
        fallback: Optional[int] = None,
    ):
        if array:
            pairs = tuple((int(key), value) for key, value in pairs)
        self.pairs = pairs
        self.single = single
        self.all = all
        self.fallback = fallback

    def __str__(self):
        return "\n".join(f"{key}={value!r}" for key, value in self.pairs)

    def __repr__(self):
        return f"Matcher{self.pairs}"

    def __iter__(self):
        yield from self.pairs

    async def __aiter__(self):
        for pair in self.pairs:
            yield pair

    def check(self, inner: MatchType) -> bool:
        func = all if self.all else any
        return func(inner[key] == value for key, value in self.pairs)

    def random(self) -> tuple:
        return choice(self.pairs)

    def get(self, final: list[MatchType]) -> list[MatchType] | MatchType:
        total = []
        for inner in final:
            if self.check(inner):
                if self.single:
                    return inner
                total.append(inner)

        if not total and self.fallback is not None:
            fallback = final[self.fallback]
            if self.single:
                return fallback
            return [fallback]

        if self.single:
            return None
        return total

    def place(self, final, value):
        raise NotImplementedError

    def pop(self, final):
        raise NotImplementedError

    insert = place


class SetupMeta(type):
    setup: Callable[[], Coroutine | Any]

    def __init__(cls: "Setup", name: str, bases: tuple[type], clsdict: dict[str, Any]):
        super(SetupMeta, cls).__init__(name, bases, clsdict)
        if len(cls.mro()) > 2:
            setup = cls.setup()
            if isawaitable(setup):
                asyncio.ensure_future(setup)


class Setup(metaclass=SetupMeta):
    @classmethod
    def setup(cls):
        return NotImplemented


def magic(name: str):
    if name.startswith("__r"):
        name = name.replace("__r", "__", 1)
        replace = True
    else:
        replace = False

    def inner(self: type, *args):
        if replace:
            obj = args[0]
            args = None
        else:
            obj = None

        self.actions.append((obj, name, args))

        return self

    return inner


class Deferred(Setup):
    def __init__(self, func: Callable, *args, **kwargs):
        self.function = func
        self.actions = []
        self.args = args
        self.kwargs = kwargs
        self._done = None

    def __call__(self) -> Coroutine:
        return self.done()

    async def done(self) -> Any:
        self._done = self.function(*self.args, **self.kwargs)

        if isawaitable(self._done):
            self._done = await self._done

        for obj, name, args in self.actions:
            if args is None:
                args = (self._done,)
            else:
                if type(args[0]) is Deferred:
                    args = (await args[0](), *args[1:])
                obj = self._done

            try:
                done = getattr(obj, name)(*args)
                assert done is not NotImplemented
                self._done = done
            except (TypeError, AssertionError):
                if obj == self._done:
                    kind = type(args[0])
                    obj = kind(obj)
                else:
                    kind = type(obj)
                    args = (kind(args[0]), *args[1:])

                self._done = getattr(obj, name)(*args)

        return self._done

    def __str__(self):
        return str(self._done)

    def __repr__(self):
        return repr(self._done)

    def __bool__(self):
        return bool(self._done)

    skip = [
        "__getattribute__",
        "__call__",
        "__init__",
        "__new__",
        "__new__",
        "__slots__",
        "__class__",
        "__subclasshook__",
        "__doc__",
        "__setattr__",
        "__str__",
        "__repr__",
        "__bool__",
    ]

    @classmethod
    def setup(cls):
        dirs = [
            name
            for methods in (str, int, float, list, dict, bool)
            for name in dir(methods)
            if name.startswith("__") and name not in cls.skip
        ]

        total = set()
        for name in dirs:
            total.add(name)

        for name in total:
            setattr(cls, name, magic(name))


class DynamicDictionary(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.converters: list[dict[str, Any]] = []
        self.event: Optional[Event] = None

    def __getitem__(self, item: str) -> Any:
        event = self.event

        if event and item in event.ready_variables:
            return event.ready_variables[item]

        elif item in self:
            return super().__getitem__(item)

        elif item == "dir":
            return list(event.ready_variables)

        else:
            for converter in self.converters:
                total_items = converter["items"]
                if isfunction(total_items):
                    total_items = total_items()

                if item in total_items:
                    if converter["event"]:
                        args = (item, self.event)
                    else:
                        args = (item,)

                    return converter["function"](*args)

            return item
            # raise KeyError(item)

    def copy(self) -> "DynamicDictionary":
        obj = DynamicDictionary(self)
        obj.converters = self.converters.copy()
        obj.event = self.event
        return obj

    def __or__(self, other: Mapping) -> "DynamicDictionary":
        obj = super().__or__(other)
        obj = DynamicDictionary(obj)
        obj.converters = self.converters.copy()
        obj.event = self.event
        return obj

    __ior__ = __ror__ = __or__

    def add_converter(self, items: list[str], function: Callable, event: bool = False):
        self.converters.append({"items": items, "function": function, "event": event})

    def prepare_event(self, event: Event) -> "DynamicDictionary":
        obj = self.copy()
        obj.event = event
        return obj


object_words = (
    "author",
    "member",
    "user",
    "emoji",
    "guild",
    "channel",
    "category",
    "voice",
    "object",
    "role",
    "webhook",
    "id",
    "status",
    "activity",
    "activities",
    "permissions",
    "roles",
    "emojis",
    "members",
    "users",
    "owner",
    "client",
    "spotify",
    "customactivity",
    "game",
    "steaming",
    "top_role",
    "message",
    "messages",
    "channels",
    "guilds",
    "text",
    "stream",
    "all",
    "overwrites",
    "overwrite",
    "permissionoverwrite",
    "guild_permissions",
    "rpc",
)

patterns: dict[str, Callable[[Any], Match | bool]] = {
    "null": lambda value: len(value) == 0 or value is None,
    "whitespace": lambda value: not value.strip(),
    "id": regex.compile(r"^\d{17,19}$").match,
    "object": lambda value: value in object_words,
    "int": regex.compile(r"^[-+]?\d+$").match,
    "float": regex.compile(r"^[-+]?(\d*\.\d+)|(\d+\.)$").match,
    "user": regex.compile(r"^<@!?\d{17,19}>$").match,
    "channel": regex.compile(r"^<#\d{17,19}>$").match,
    "role": regex.compile(r"^<&\d{17,19}>$").match,
    "emoji": regex.compile(r"^<a?:\w+:\d{17,19}>$").match,
    "unicode_emoji": lambda value: value in emoji_list,
    "url": regex.compile(r"^<?((?:https?|ftp)://[^\s/$.?#].[^\s]*(?:[^>]))>?$").match,
    "color": regex.compile(r"^(#|0x)(?:[0-9a-fA-F]{3}){1,2}$").match,
}


def get_type(value: Any) -> str:
    type_ = type(value)
    if type_ is not str:
        if type_ is NoneType:
            return "null"
        if type_ is int and len(str(value)) in range(17, 19 + 1):
            return "id"
        return type_.__name__.lower()

    for item, func in patterns.items():
        if func(value):
            return item
    return "string"


class Timer:
    def __init__(self, timeout: float, callback: Callable, *args, **kwargs):
        self._timeout = timeout
        self._callback = callback
        self._task: Optional[asyncio.Future] = None
        self._args = args
        self._kwargs = kwargs

    def start(self) -> None:
        if self._task is not None:
            self.stop()
        self._task = asyncio.ensure_future(self._job())

    async def _job(self) -> None:
        await asyncio.sleep(self._timeout)

        try:
            done = self._callback(*self._args, **self._kwargs)
            if isawaitable(done):
                done = await done
        except Exception:
            pass

        self._task = None

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    async def wait(self) -> Any:
        return await asyncio.wait_for(self._task, None)


class Schedule:
    def __init__(self, **data):
        self.date = data.get("date")
        self.code = data.get("code")
        self.data = data
        self.pid: Optional[int] = None
        self.state: Optional[StateType] = None
        self._future: Optional[asyncio.Future[Result]] = None

    @property
    def short_content(self) -> str:
        if len(self.code) > 50:
            code = self.code[:50] + "..."
        else:
            code = self.code
        return f"schedule {code}"

    def set_pid(self, pid: int) -> None:
        self.pid = pid

    async def _start(self, event: Event) -> Result:
        await sleep_until(self.date)

        from parser import get_processor

        result = await (await get_processor(self.code)).finalize(event, True)

        self._future = None
        await self.cancel()

        return result

    def start(self, event: Event) -> None:
        self._future = asyncio.ensure_future(self._start(event))

    def cached_start(self, client: Client) -> None:
        self.start(client.create_event(self.data))

    async def save(self) -> None:
        from .database import db

        await db.save_schedule(self)

    async def cancel(self) -> None:
        from .database import db

        if self._future:
            self._future.cancel()
            self._future = None
        await db.remove_schedule(self)
        self.state.remove_event(self)
