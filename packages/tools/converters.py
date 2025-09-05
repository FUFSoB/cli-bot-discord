from __future__ import annotations

from models.packages import Command
from models.errors import CommandError
from models.utils import get_discord_id, get_time
from models.extra import required
from structure.data import get_path
import base64 as b64
from datetime import datetime, timedelta, timezone
from dateutil.parser import parse as parse_date
from discord.utils import snowflake_time
from string import Template as FormatTemplate
import emojis

from typing import Optional, Union
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result


class base64(Command):
    """
    Encode or decode base64.
    """

    usage = "%(prog)s [-d] [file]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "file", nargs="?", help="file to encode or decode from"
        )
        cls.argparser.add_argument(
            "-d", "--decode", action="store_true", help="decode data"
        )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        if args.file:
            file = await get_path(args.file, event=event, directory=False)
            data = await file.read(event=event)
        else:
            data = stdin.as_data()

        if type(data) is str:
            data = data.encode()

        try:
            if args.decode:
                final = b64.b64decode(data).decode("utf-8")
            else:
                final = b64.b64encode(data).decode("ascii")
        except Exception:
            raise CommandError(cls, "Not a base64-suitable input")

        return final


class date(Command):
    """
    Manipulate with date-representing objects
    """

    usage = "%(prog)s [options*] [format]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("format", nargs="*", help="any format string")
        cls.argparser.add_argument("-d", "--date", help="date string")
        cls.argparser.add_argument(
            "-f",
            "--from-id",
            type=get_discord_id,
            help="get date from ID",
            metavar="ID",
        )
        cls.argparser.add_argument(
            "-t", "--tz-offset", help="explicitely set timezone offset"
        )
        cls.argparser.add_argument(
            "-R",
            "--raw",
            action="store_true",
            help="return date object instead of formatted string",
        )

    @staticmethod
    def stdin_to_datetime(object: list[datetime | str]) -> datetime | None:
        if not object:
            return None

        # if type(object) is list:
        object = object[-1]

        if type(object) is datetime:
            return object

        try:
            return snowflake_time(get_discord_id(object))
        except Exception:
            return parse_date(object)

    @staticmethod
    def format_string(event: Event, args: Namespace) -> str:
        return (
            args.format
            and " ".join(args.format)
            or event.get_variable("date_format")
            or "%d %h %Y, %H:%M:%S %Z"
        )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str | datetime:
        tz = timezone(
            timedelta(
                hours=float(args.tz_offset or event.get_variable("timezone") or 0)
            )
        )

        date = (
            args.date
            and parse_date(args.date)
            or args.from_id
            and snowflake_time(args.from_id)
            or stdin
            and cls.stdin_to_datetime(list(stdin.filter(datetime, str)))
            or datetime.now()
        ).astimezone(tz)

        if args.raw:
            return date

        return date.strftime(cls.format_string(event, args))


class timedelta_(Command):
    """
    Manipulate with date-representing objects
    """

    usage = "%(prog)s [options*] <time+>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "time", nargs="+", type=get_time, help="time to setup object from"
        )
        cls.argparser.add_argument(
            "-f",
            "--format",
            nargs="?",
            default=None,
            help="format object into specified string",
        )

    @classmethod
    def setup(cls):
        class DeltaTemplate(FormatTemplate):
            delimiter = "%"

        @staticmethod
        def format(tdelta: timedelta, fmt: str) -> str:
            d: dict[str, str | float] = {"D": tdelta.days}
            d["days"] = tdelta.days == 1 and "day" or "days"

            yd = divmod(tdelta.days, 365.25)
            d["y"], d["d"] = int(yd[0]), int(yd[1])
            d["years"] = d["y"] == 1 and "year" or "years"

            d["h"], rem = divmod(tdelta.seconds, 3600)
            d["H"] = f"{d['h']:02}"
            d["hours"] = d["h"] == 1 and "hour" or "hours"

            d["m"], d["s"] = divmod(rem, 60)
            d["M"] = f"{d['m']:02}"
            d["S"] = f"{d['s']:02}"

            d["minutes"] = d["m"] == 1 and "minute" or "minutes"
            d["seconds"] = d["s"] == 1 and "second" or "seconds"

            d["T"] = tdelta.seconds
            d["f"] = tdelta.microseconds

            t = DeltaTemplate(fmt)
            return t.substitute(**d)

        cls.format = format

    @staticmethod
    def format_delta_string(final: timedelta, event: Event, args: Namespace) -> str:
        return (
            args.format
            and " ".join(args.format)
            or event.get_variable("timedelta_format")
            or final.days > 365
            and "%y %years, %d days, %h:%M:%S"
            or "%D %days, %h:%M:%S"
        )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str | timedelta:
        seconds = sum(args.time)
        final = timedelta(seconds=seconds)
        if args.format:
            return cls.format(final, cls.format_delta_string(final, event, args))

        return final


class datedelta(date, timedelta_):
    """
    Calculate delta of two date objects.
    """

    usage = "%(prog)s [format]"
    epilog = (
        "There must be date-representing objects in stdin "
        "(e.g. from command date --raw)."
    )

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("format", nargs="*", help="any format string")
        cls.argparser.add_argument(
            "-s",
            "--sum",
            action="store_true",
            help="summarize values instead of calculating difference",
        )
        cls.argparser.add_argument(
            "-r", "--reverse", action="store_true", help="reverse order of date objects"
        )
        cls.argparser.add_argument(
            "-R",
            "--raw",
            action="store_true",
            help="return date/datedelta object instead of formatted string",
        )

    @classmethod
    @required("stdin")
    async def function(
        cls, event: Event, args: Namespace, stdin: Result
    ) -> str | datetime | timedelta | None:
        DT = Union[datetime, timedelta]
        if args.sum:

            def func(first: DT, second: DT) -> DT:
                return first + second

        else:

            def func(first: DT, second: DT) -> DT:
                return first - second

        dates = list(stdin.filter(datetime, timedelta))
        if len(dates) == 1:
            dates: list[datetime | timedelta] = [datetime.now()] + dates
        if args.reverse:
            dates: list[datetime | timedelta] = dates[::-1]

        final = None
        for date in dates:
            if final is None:
                final = date
                continue
            final = func(final, date)

        if args.raw:
            return final

        if type(final) is datetime:
            return final.strftime(cls.format_string(event, args))

        return cls.format(final, cls.format_delta_string(final, event, args))


class unicode(Command):
    """
    Manipulate with unicode characters.
    """

    usage = "%(prog)s [options*] <action> <string+>"

    extra_defaults = {"hex": "-", "code": " ", "encode": "ascii", "decode": "ascii"}

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "action",
            choices=("hex", "code", "demojize", "encode", "decode"),
            help="action to take on strings",
        )
        cls.argparser.add_argument("string", nargs="+", help="any string")
        cls.argparser.add_argument(
            "-e",
            "--extra",
            help="extra argument depending on action (delimeter, encoding)",
        )

    @staticmethod
    def abs_func(string: str, extra: str) -> str: ...

    @staticmethod
    def hex(string: str, sep: str) -> str:
        return sep.join(f"{ord(y):x}" for y in string)

    @staticmethod
    def code(string: str, sep: str) -> str:
        return sep.join(str(ord(y)) for y in string)

    @staticmethod
    def demojize(string: str, _) -> str:
        return emojis.decode(string)

    @staticmethod
    def encode(string: str, encoding: str) -> str:
        return string.encode(encoding, "backslashreplace").decode(encoding)

    @staticmethod
    def decode(string: str, encoding: str) -> str:
        return bytes(string, encoding).decode("utf-8")

    @classmethod
    @required("action")
    @required("string")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> list[str]:

        action: cls.abs_func = getattr(cls, args.action)
        extra = args.extra or cls.extra_defaults.get(args.action)

        return [action(s, extra) for s in args.string]
