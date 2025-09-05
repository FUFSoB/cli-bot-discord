from __future__ import annotations

from models.packages import Command
from models.extra import Timer, required
from models.utils import get_pair_not_strict
import ujson
import idna
import aiohttp
from parser import get_processor

from typing import Literal, Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result


class net(Command):
    """
    Internet browser.
    """

    usage = "%(prog)s [options*] <url>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("url", help="any http(s) url")
        cls.argparser.add_argument(
            "-m",
            "--method",
            choices=("GET", "POST", "PUT", "DELETE", "PATCH"),
            type=lambda x: x.upper(),
            default="GET",
            help="request method to use",
        )
        cls.argparser.add_argument(
            "-D", "--data", type=lambda x: x.encode(), help="any data"
        )
        cls.argparser.add_argument(
            "-j",
            "--json-keys",
            nargs="*",
            action="extend",
            type=get_pair_not_strict,
            help="key-value pairs",
        )
        cls.argparser.add_argument("-J", "--json", type=ujson.loads, help="any json")
        cls.argparser.add_argument(
            "-p",
            "--params",
            nargs="*",
            action="extend",
            type=get_pair_not_strict,
            help="key-value pairs",
        )

    @staticmethod
    def make_up_the_url(url: str) -> str:
        if not url.startswith("http"):
            url = "http://" + url

        url = url.removesuffix("/")

        domain = url.split("//", 1)[1].split("/")[0]
        idna_domain = idna.encode(domain).decode()
        url = url.replace(domain, idna_domain)

        return url

    @classmethod
    async def request(cls, args: Namespace, url: str, **kwargs) -> str | bytes:
        async with aiohttp.ClientSession(json_serialize=ujson.dumps) as session:
            async with session.request(args.method, url, **kwargs) as resp:
                try:
                    return await resp.text()
                except Exception:
                    return await resp.read()

    @classmethod
    @required("url")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str | bytes:
        url = cls.make_up_the_url(args.url)

        data = (
            args.data or args.json or (dict(args.json_keys) if args.json_keys else None)
        )

        return await cls.request(args, url, data=data, params=args.params)


class enter(Command):
    """
    Enter into single command mode.
    """

    usage = "%(prog)s <command...>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "-s", "--stdin", action="store_true", help="apply input to stdin"
        )
        cls.argparser.add_argument("command", nargs="...", help="any command")

    @classmethod
    @required("command")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        self = await cls.initialize(event, args, stdin)
        return (
            f"Entered {self.string!r} command.\n"
            "To exit from enter-mode, execute `exit` command."
        )

    def __init__(self, event: Event, string: str, is_stdin: bool):
        self.state = event.state
        self.short_content = event.short_content
        self.string = string
        self.is_stdin = is_stdin
        self._timer = Timer(300, self.exit)
        self.pid = None

    def set_pid(self, pid: int) -> None:
        self.pid = pid

    @classmethod
    async def initialize(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> "enter":
        self = cls(event, " ".join(args.command), args.stdin)
        self.state.add_redirect(self)
        self._timer.start()
        return self

    async def __call__(self, event: Event) -> Literal[True] | None:
        if event.name not in ("message", "message_edit"):
            return None

        content = event.message.content
        prefixes = (*event.prefixes, "#")
        if content.startswith(prefixes):
            if "exit" in content:
                await event.message.add_reaction("👌")
                return self.exit()
            return None

        content = content.removeprefix("\\")

        if self.is_stdin:
            string = self.string + " << CALL_EOF\n" + content + "\nCALL_EOF"
        else:
            string = self.string + " " + content

        processor = await get_processor(string)
        result = await processor.finalize(event)
        result.set_name(processor.string)
        await event.response(result)

        self._timer.start()
        return True

    def exit(self) -> Literal[True]:
        self.state.pop_redirect(self)
        self._timer.stop()
        return True

    async def cancel(self) -> None:
        self.exit()
