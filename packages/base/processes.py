from __future__ import annotations

from models.extra import required
from models.packages import Command

from typing import Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result


class ps(Command):
    """
    Return list of active processes.
    """

    usage = "%(prog)s"

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        return "\n".join(
            f"{e.pid}: {e.short_content}" for e in event.state.sorted_processes
        )


class kill(Command):
    """
    Kill active process.
    """

    usage = "%(prog)s <pid>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("pid", type=int, help="process id")

    @classmethod
    @required("pid")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        process = event.state.get_process(args.pid)
        await process.cancel()
        return f"Process killed: [{process.pid}] {process.short_content}"
