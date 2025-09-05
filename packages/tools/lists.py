from __future__ import annotations

from models.packages import Command
from models.extra import Segment, required, types, convert_type
from models.errors import LimitExceededError
from collections import Counter
import regex
import random

from typing import Any, Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result


class segment(Command):
    """
    Create special segment object (for lists).
    """

    usage = "%(prog)s [[start]:][stop[:step]*]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "string",
            nargs="*",
            type=Segment.from_string,
            help="python-like slice syntax",
        )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> Segment:
        return args.string


class array(Command):
    """
    Create list object.

    Types available: {cls.types}
    """

    usage = "%(prog)s [options*] [type::][item*]"

    types = ", ".join(types)

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("item", nargs="*", help="items of list")
        cls.argparser.add_argument("-t", "--type", help="converts items to type")

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> list[str] | list:
        return (
            [convert_type(cls, args.type, item) for item in args.item]
            if args.type
            else args.item
        )


class sequence(Command):
    """
    Create sequence of objects.
    """

    usage = "%(prog)s"
    epilog = "There must be segment in stdin."

    @classmethod
    @required("stdin")
    async def function(
        cls, event: Event, args: Namespace, stdin: Result
    ) -> list[int] | list[str]:
        segments = list(stdin.filter(Segment))

        if any(
            seg.stop is None or (seg.stop - (seg.start or 0)) / (seg.step or 1) > 10000
            for seg in segments
        ):
            raise LimitExceededError(10000, "maximum number of symbols")

        return [obj for segment in segments async for obj in segment]


class get(Command):
    """
    Slice items.
    """

    usage = "%(prog)s"
    epilog = "There must be getter and other output in stdin."

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "-f",
            "--fallback",
            nargs="?",
            action="store",
            const="",
            help="fallback to getter or value",
            metavar="value",
        )

    @classmethod
    @required("stdin")
    async def function(cls, event: Event, args: Namespace, stdin: Result) -> Any:
        total = stdin.not_getters
        if len(total) == 1:
            total = total[0]

        for getter in stdin.are_getters():
            try:
                total = getter.get(total)
            except Exception:
                if args.fallback is not None:
                    return args.fallback or str(getter)
                raise

        return total


class split(Command):
    """
    Split string.
    """

    usage = "%(prog)s [options*] [delimeter]"
    epilog = "There must be string in stdin."

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "delimeter", default="\n", help="any delimeter [Default: \\n]"
        )
        cls.argparser.add_argument(
            "-e", "--regex", action="store_true", help="split using regex"
        )
        cls.argparser.add_argument(
            "-t", "--times", default=0, type=int, help="times to split"
        )

    @classmethod
    @required("stdin")
    async def function(
        cls, event: Event, args: Namespace, stdin: Result
    ) -> list[str] | None:
        content = str(stdin)
        if not content:
            return

        if args.regex:
            return regex.split(args.delimeter, content, args.times)
        else:
            if args.delimeter == "":
                return list(content)
            else:
                return content.split(args.delimeter, args.times or -1)


class pick(Command):
    """
    Pick from items.
    """

    usage = "%(prog)s [options*] [item*]"
    epilog = "There must be list or segment in stdin."
    aliases = ["choose"]

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("item", nargs="*", help="possible item to choose")
        cls.argparser.add_argument(
            "-t", "--times", type=int, default=1, help="repeat times"
        )
        cls.argparser.add_argument(
            "-r", "--raw", action="store_true", help="return raw list of results"
        )

    @classmethod
    @required("stdin", "item")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> list | str:
        if stdin and (_getters := stdin.getters):
            pick = _getters[-1].random

        else:
            pick_from = args.item or stdin

            def pick() -> str | Any:
                return random.choice(pick_from)

        total = [pick() for _ in range(args.times)]

        if len(total) < 2 or args.raw:
            return total
        else:
            return "\n".join(
                f"{key}: {value}" for key, value in Counter(total).most_common()
            )


class join(Command):
    """
    Join strings.
    """

    usage = "%(prog)s [delimeter]"
    epilog = "There must be list in stdin."

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "delimeter", default="\n", help="any delimeter [Default: \\n]"
        )

    @classmethod
    @required("stdin")
    async def function(cls, event: Event, args: Namespace, stdin: Result) -> str:
        return args.delimeter.join(str(i) for i in stdin)
