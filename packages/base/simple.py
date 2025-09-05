from __future__ import annotations

from operator import attrgetter
import psutil
import distro
import os
import sys
import discord
from models.packages import Command, get_command, get_commands, packages
from models.utils import unescape, convert_bytes
from models.extra import required
from discord.utils import oauth_url
from discord import Permissions

from typing import Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result


class echo(Command):
    """
    Print contents to stdout.
    """

    usage = "%(prog)s [-e] [args*]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("args", nargs="*", help="any string to print")
        cls.argparser.add_argument(
            "-e",
            "--interpretate-escapes",
            action="store_true",
            help="enable interpretation of backslash escapes",
        )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        if args.interpretate_escapes:
            return " ".join(unescape(x) for x in args.args)
        else:
            return " ".join(args.args)


class help(Command):
    """
    Print help message for command.
    Same as `command --help`.

    For list of commands, please execute command `commands`.
    """

    usage = "%(prog)s [command*]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "command", nargs="*", help="any command", default=["help"]
        )
        cls.argparser.add_argument(
            "--all", action="store_true", help="return help for every single command"
        )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        total = []
        for command in get_commands():
            if args.all or command.name in args.command:
                name = " " + command.name + " "
                total.append("\n##" + name.center(18, "=") + "##\n")
                total.append(command.help_message)

        for name, function in event.functions.items():
            if "help_message" not in dir(function):
                continue
            if args.all or name in args.command:
                name = " " + name + " "
                total.append("\n##" + name.center(18, "=") + "##\n")
                total.append(function.help_message)

        return "\n".join(total)


class about(Command):
    """
    Return information about bot.
    """

    proc = psutil.Process(os.getpid())

    @classmethod
    def all_mem(cls):
        return psutil.virtual_memory()

    @classmethod
    def total_used(cls):
        return convert_bytes(cls.all_mem().used)

    @classmethod
    def swap_mem(cls):
        return psutil.swap_memory()

    @classmethod
    def total_swap_used(cls):
        return convert_bytes(cls.swap_mem().used)

    @classmethod
    def mem_proc_used(cls):
        return convert_bytes(cls.proc.memory_info().rss)

    @classmethod
    def cpu_used(cls):
        return psutil.cpu_percent()

    cpu_freq = "2.4GHz"
    cpu_cores = psutil.cpu_count()

    dist = " ".join(distro.linux_distribution())

    v = sys.version_info
    py_version = f"{v.major}.{v.minor}.{v.micro}" + (
        f"{v.releaselevel[0]}{v.serial}" if v.releaselevel != "final" else ""
    )

    dpy_version = discord.__version__

    @classmethod
    def setup(cls):
        cls.total_memory = convert_bytes(cls.all_mem().total)
        cls.total_swap_memory = convert_bytes(cls.swap_mem().total)

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        client = event.client
        app = client.app
        users = str(
            client.intents.members and f"\n    USERS: {len(client.users)}" or ""
        )
        return (
            f"""\
      BOT: {client.user} ({client.user.id})
BOT OWNER: {app.owner} ({app.owner.id})
   GUILDS: {len(client.guilds)}"""
            + users
            + f"""
 CHANNELS: {len(list(client.get_all_channels()))}
   EMOJIS: {len(client.emojis)}
 MESSAGES: {len(client.cached_messages)}
   SYSTEM: {cls.dist}
   PYTHON: {cls.py_version} (discord.py {cls.dpy_version})
MEM USAGE: {cls.mem_proc_used()}
   MEMORY: {cls.total_used()}/{cls.total_memory}
     SWAP: {cls.total_swap_used()}/{cls.total_swap_memory}
      CPU: {cls.cpu_freq} x{cls.cpu_cores} [{cls.cpu_used()}%]"""
        )


class commands(Command):
    """
    Print all available commands.
    """

    @staticmethod
    def prepare_description(desc: Optional[str]) -> str:
        if not desc:
            return ""
        return desc.split("\n", 1)[0]

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        final = ""

        if event.functions:
            final += "Custom commands and functions:\n"

            for object in (event.guild_state, event.user_state, event):
                try:
                    functions = object.exported_functions
                    category = object.kind.capitalize()
                except AttributeError:
                    functions = object.temporary_functions
                    category = "Temporary"
                if not object or not functions:
                    continue

                final += f"  {category}:\n"

                keys = list(sorted(functions.keys()))
                pad = len(max(keys, key=len)) + 1

                for name in keys:
                    function = functions[name]
                    if "source" in dir(function):
                        desc = cls.prepare_description(function.description)
                        final += f"    {name.ljust(pad)} {desc}\n"
                    else:
                        final += f"    {name.ljust(pad)} (function)\n"

                final += "\n"

            final += "\n"

        for package in sorted(packages, key=attrgetter("name")):
            final += f"Package [{package.name}]:\n"

            categories = {
                key: package.categories[key]
                for key in sorted(package.categories.keys())
            }

            for category, commands in categories.items():
                if category:
                    final += f"  Category [{category}]:\n"

                pad = len(max((c.name for c in commands), key=len)) + 1

                for command in sorted(commands, key=attrgetter("name")):
                    desc = cls.prepare_description(command.description)
                    final += f"    {command.name.ljust(pad)} {desc}\n"

                final += "\n"

            final += "\n"

        return final


class whoami(Command):
    """
    Print current user id.
    """

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> int:
        return event.state.object.id


class invite(Command):
    """
    Generate invite link.
    """

    usage = "%(prog)s <permissions>"

    values: dict[str, Permissions] = {
        "none": Permissions.none(),
        "all": Permissions.all(),
        "admin": Permissions(administrator=True),
        "required": Permissions(
            manage_channels=True,
            manage_guild=True,
            add_reactions=True,
            read_messages=True,
            send_messages=True,
            manage_messages=True,
            attach_files=True,
            external_emojis=True,
            view_guild_insights=True,
            change_nickname=True,
            manage_nicknames=True,
            manage_roles=True,
            manage_webhooks=True,
            manage_emojis=True,
            read_message_history=True,
        ),
    }

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "permissions",
            choices=("none", "required", "admin", "all"),
            default="required",
            help="permissions to set",
        )
        cls.argparser.add_argument(
            "-r",
            "--return",
            action="store_true",
            help="just return url instead of sending as separate message",
            dest="return_",
        )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> None | str:
        url = oauth_url(event.client.user.id, permissions=cls.values[args.permissions])
        if args.return_:
            return url

        event.apply_option("send", False)
        await event.send(url)


class whereis(Command):
    """
    Show where source file for command is locating.
    """

    usage = "%(prog)s <command+>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("command", nargs="+", help="commands to show")

    @classmethod
    @required("command")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        return "\n".join(
            [f"{c}: {(await get_command(c, event)).file_source}" for c in args.command]
        )
