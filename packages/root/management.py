from __future__ import annotations

from models.packages import Command
import sys
import os
import models.packages as mpkg
import packages
from models.bot import clients

from typing import Literal, Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result


class reboot(Command):
    """
    Reboot bot.
    """

    group = "root"

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> None:
        if not event.client.real:
            return

        for client in clients:
            await client.logout()

        print("\n\n")
        os.execv(sys.executable, [sys.executable] + sys.argv)


class reload(Command):
    """
    Reload bot commands.
    """

    group = "root"

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> Literal["Reloaded!"] | None:
        if not event.client.real:
            return

        mpkg.packages.clear()
        mpkg.events.clear()
        mpkg.reloading = True
        packages.reload_modules()

        return "Reloaded!"


class poweroff(Command):
    """
    Exit bot.
    """

    group = "root"

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> None:
        if not event.client.real:
            return

        for client in clients:
            await client.logout()
        os._exit(0)


class debug(Command):
    """
    Print value into terminal.
    """

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("value", nargs="...", help="value to print")

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> None:
        print(f"{args.value=}")
        print(f"{stdin=}")
