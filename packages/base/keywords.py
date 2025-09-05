from __future__ import annotations

from models.extra import required
from models.packages import Command
from models.errors import (
    ContinueError,
    BreakError,
    ReturnError,
    # IfPreEndError
)
from parser import get_processor

from typing import NoReturn, Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result


class continue_(Command):
    """
    Continue the loop.
    """

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> NoReturn:
        raise ContinueError()


class break_(Command):
    """
    Break the loop.
    """

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> NoReturn:
        raise BreakError()


class return_(Command):
    """
    Return from function or command.
    """

    usage = "%(prog)s [value...]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("value", nargs="...", help="value to return")

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> NoReturn:
        raise ReturnError(" ".join(args.value) or stdin or None)


class pass_(Command):
    """
    Pass command.
    """

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> None:
        pass


# class except_(Command):
#     """
#     Filter exceptions in command output.
#     """

#     @classmethod
#     def generate_argparser(cls):
#         cls.argparser.add_argument(
#             "default",
#             nargs="*",
#             help="return value if there are only errors"
#         )

#     @classmethod
#     async def function(
#         cls,
#         event: Event,
#         args: Namespace,
#         stdin: Optional[Result]
#     ) -> list | str:
#         return list(
#             stdin.filter(Exception, truth=False, instance=True)
#         ) or args.default and " ".join(args.default)


class try_(Command):
    """
    Try command and return stdin if it fails.
    """

    usage = "%(prog)s <command...>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("command", nargs="...", help="command to execute")

    @classmethod
    @required("command")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> Result | None:
        try:
            result: Result = await (
                await get_processor(" ".join(args.command))
            ).finalize(event, True)
            assert not result.errors
            return result
        except Exception:
            return stdin


# class endif(Command):
#     """
#     Exit from inner if-statement.
#     """

#     @classmethod
#     async def function(
#         cls,
#         event: Event,
#         args: Namespace,
#         stdin: Optional[Result]
#     ) -> NoReturn:
#         raise IfPreEndError()
