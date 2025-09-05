from __future__ import annotations

from models.packages import Command
from models.extra import (
    Pointer,
    get_pair_and_convert,
    required,
    types,
    convert_type,
    Matcher,
)
import ujson
import pprint

from typing import Any, Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result

if False:
    from models.typings import GetterType


class pointer(Command):
    """
    Create special pointer object (for dictionaries).
    """

    usage = "%(prog)s [key*]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("key", nargs="*", help="dictionary key")
        cls.argparser.add_argument(
            "-r", "--reverse", action="store_true", help="get by value instead of key"
        )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> Pointer:
        return Pointer(*args.key, reverse=args.reverse)


class matcher(Command):
    """
    Create special getter object to match both values and keys.
    """

    usage = "%(prog)s [<[key_type:]key:type|key>=[value]*]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "pair", nargs="*", type=get_pair_and_convert, help="key-value pair"
        )
        cls.argparser.add_argument(
            "-a", "--array", action="store_true", help="treat keys as array indexes"
        )
        cls.argparser.add_argument(
            "-s", "--single", action="store_true", help="return only first match"
        )
        cls.argparser.add_argument(
            "-A", "--any", action="store_true", help="use 'or' logic"
        )
        cls.argparser.add_argument(
            "-f",
            "--fallback",
            type=int,
            help="element to get if none meeting requirements",
        )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> Matcher:
        return Matcher(
            *args.pair,
            array=args.array,
            single=args.single,
            all=not args.any,
            fallback=args.fallback,
        )


class mapping(Command):
    """
    Create dictionary object.
    """

    usage = "%(prog)s [<[key_type:]key:type|key>=[value]*]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "pair", nargs="*", type=get_pair_and_convert, help="key-value pair"
        )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> dict:
        return dict(args.pair)


class json(Command):
    """
    Work with json and dictionaries.
    """

    usage = "%(prog)s [options*]"
    epilog = "There must be either dictionary or json-string in stdin."

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "-p",
            "--pretty",
            action="store",
            nargs="?",
            const=2,
            type=int,
            metavar="indent",
            help="return pretty-formatted object",
        )
        cls.argparser.add_argument(
            "-j",
            "--json",
            action="store_true",
            help="return json-string (by default returns dictionary)",
        )

    @classmethod
    def convert(
        cls, value: dict | str, is_json: bool
    ) -> dict | list | str | float | bool | None:
        value_type = type(value)
        if value_type is str and not is_json:
            return ujson.loads(value)
        elif is_json:
            return ujson.dumps(value, ensure_ascii=False, escape_forward_slashes=False)
        else:
            return value

    @classmethod
    def pretty(cls, value: dict | str, is_json: bool, indent: int | None) -> str:
        data = cls.convert(value, False)

        if is_json:
            return ujson.dumps(
                data, ensure_ascii=False, indent=indent, escape_forward_slashes=False
            )
        else:
            return pprint.pformat(data, indent=indent, sort_dicts=False)

    @classmethod
    @required("stdin")
    async def function(
        cls, event: Event, args: Namespace, stdin: Result
    ) -> str | dict | list | float | bool | None:
        values = list(stdin.filter(dict, str))

        if args.pretty:
            return cls.pretty(values[-1], args.json, args.pretty)
        else:
            return cls.convert(values[-1], args.json)


class pop(Command):
    """
    Pop value from an object.
    """

    usage = "%(prog)s [options*]"
    epilog = "There must be dict/list and getter in stdin."

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "-g",
            "--get-value",
            action="store_true",
            help="get value instead of resulting object",
        )

    @staticmethod
    def get_objects(stdin: Result) -> tuple[Any | dict | list, Any, GetterType]:
        final = stdin.not_getters
        if len(final) == 1:
            final = final[0]

        first = final
        getters = stdin.getters
        finalizer = getters.pop(-1)

        for getter in getters:
            final = getter.get(final)  # TODO typings

        return first, final, finalizer

    @classmethod
    @required("stdin")
    async def function(
        cls, event: Event, args: Namespace, stdin: Result
    ) -> list | dict | Any:
        first, final, popper = cls.get_objects(stdin)

        popped = popper.pop(final)

        if args.get_value:
            return popped
        return first


class place(pop):
    """
    Place value to an object.

    Types available: {cls.types}
    """

    usage = "%(prog)s [options*] [value]"

    types = ", ".join(types)

    @classmethod
    def generate_argparser(cls):
        super().generate_argparser()
        cls.argparser.add_argument(
            "value", help="value to place (uses current by default)"
        )
        cls.argparser.add_argument("-t", "--type", help="format value as type")

    @classmethod
    @required("stdin")
    async def function(
        cls, event: Event, args: Namespace, stdin: Result
    ) -> list | dict | Any:
        first, final, placer = cls.get_objects(stdin)

        value = args.value or placer.get(final)
        if args.type:
            value = convert_type(cls, args.type, value)

        placer.place(final, value)

        if args.get_value:
            return value
        return first


class insert(place):
    """
    Insert value to an object.
    """

    usage = "%(prog)s [options*] <value>"

    types = ", ".join(types)

    @classmethod
    def generate_argparser(cls):
        super().generate_argparser()
        cls.argparser.add_argument(
            "-p",
            "--pop-if-exists",
            action="store_true",
            help="pop value if it exists (array-only)",
        )

    @classmethod
    @required("stdin")
    @required("value")
    async def function(
        cls, event: Event, args: Namespace, stdin: Result
    ) -> list | dict | Any:
        first, final, placer = cls.get_objects(stdin)

        value = args.value
        if args.type:
            value = convert_type(cls, args.type, value)

        if type(final) is list and value in final:
            final.remove(value)
        else:
            placer.insert(final, value)

        if args.get_value:
            return value
        return first
