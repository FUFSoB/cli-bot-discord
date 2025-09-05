from __future__ import annotations

from models.packages import Command
import asyncio
from models.utils import NoneType, get_time, get_date
from models.extra import Schedule, required
from discord.utils import sleep_until
from datetime import datetime, timedelta, timezone
from parser import get_processor

from typing import Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result


class seconds(Command):
    """
    Get total seconds from multiple statements.
    """

    usage = "%(prog)s <time+>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "time", nargs="+", type=get_time, help="time to calculate"
        )

    @classmethod
    @required("time")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> float:
        return sum(args.time)


class sleep(Command):
    """
    Pause for time.
    """

    usage = "%(prog)s [options*] [time*]"
    epilog = "Date object can be passed to stdin."

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "time", nargs="*", type=get_time, help="time to wait for"
        )
        cls.argparser.add_argument(
            "-d", "--date", type=get_date, help="date to wait for"
        )

    @classmethod
    @required("stdin", "date", "time")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> None:
        if args.date:
            await sleep_until(args.date)

        elif args.time:
            await asyncio.sleep(sum(args.time))

        else:
            try:
                date = list(stdin.filter(datetime))[-1]
                date = date.astimezone(timezone.utc).replace(tzinfo=None)
                await sleep_until(date)
            except Exception:
                pass


class timeout(sleep):
    """
    Set timeout for a command.
    """

    @classmethod
    def generate_argparser(cls):
        super().generate_argparser()
        cls.argparser.add_argument("-c", "--command", help="code to execute")

    @classmethod
    @required("date", "time")
    @required("stdin", "command")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> Result:
        code = args.command or str(stdin)
        processor = await get_processor(code)

        time = (
            args.time
            and sum(args.time)
            or (args.date.astimezone(timezone.utc) - datetime.now()).seconds
        )

        result = Result(name=code)

        try:
            await asyncio.wait_for(processor.finalize(event, result), timeout=time)
        except asyncio.TimeoutError:
            result << "> Timeout!"

        return result


class schedule(timeout):
    """
    Execute command after some time. Lives between state resets.
    """

    @classmethod
    def generate_argparser(cls):
        super().generate_argparser()
        cls.argparser.add_argument(
            "-w", "--wait", action="store_true", help="wait for scheduled action to end"
        )

    @classmethod
    @required("date", "time")
    @required("stdin", "command")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> Result | None:
        code = args.command or str(stdin)

        date = args.date or datetime.now() + timedelta(seconds=sum(args.time))
        date = date.astimezone(timezone.utc).replace(tzinfo=None)

        state = event.state

        temp_vars = {
            key: (
                value
                if type(value)
                in (NoneType, bool, int, float, str, datetime, bytes, list, dict)
                else str(value)
            )
            for key, value in event.temporary_variables.items()
        }

        final = Schedule(
            date=date,
            code=code,
            state_id=state.object.id,
            guild_id=getattr(event.guild, "id", None),
            user_id=getattr(event.user, "id", None),
            channel_id=getattr(event.channel, "id", None),
            temp_vars=temp_vars,
        )

        final.state = state
        state.append_event(final)

        await final.save()
        final.start(event)
        if args.wait:
            return await asyncio.wait_for(final._future, None)
