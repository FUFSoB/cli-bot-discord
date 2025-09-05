from __future__ import annotations

from inspect import isawaitable
from structure.data import get_path
from models.extra import Timer, required
import discord
from models.packages import Command
from ._helper_templates import templates
from .variables import state as state_command

from typing import Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result


class template(Command):
    """
    Create event from ready-to-use template.
    """

    usage = "%(prog)s <name>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("name", choices=templates, help="name of template")
        cls.argparser.add_argument(
            "-p", "--path", help="destination to configured template"
        )

    @classmethod
    @required("name")
    async def function(cls, event: Event, args: Namespace, stdin: Optional[Result]):
        # return "WIP"
        await cls.initialize(event, args)
        event.apply_option("send", False)

    def __init__(
        self, event: Event, args: Namespace, template: type, items: dict[str] | None
    ):
        self.state = event.state
        self.template = template
        self.defaults = self.template.defaults
        self.items = items or {k: None for k in self.defaults}
        self.keys = list(self.items)
        self.pid: int = None
        self.current_key: int = 0
        self.message: discord.Message = None
        self.prompt: str = None
        self.path = args.path
        self._timer = Timer(300, self._timer_exit)

    @classmethod
    async def initialize(cls, event: Event, args: Namespace) -> "template":
        template = templates[args.name]
        if args.path:
            file = await get_path(args.path, event=event, directory=False)
            content = await file.read(event=event)
            items = template.match(content.strip())
            if items:
                items = items.named
        else:
            items = None

        self = cls(event, args, template, items)
        self.message = await event.send(self)
        self.state.add_redirect(self)
        self._timer.start()

        return self

    def set_pid(self, pid: int) -> None:
        self.pid = pid

    def prepare_string(self, key: str, value: str) -> str:
        the_key = key.capitalize().replace("_", " ")
        the_value = value or self.defaults[key] or ""

        if key == self.keys[self.current_key]:
            pointer = "!"
        else:
            pointer = ">"

        return f"{the_key}:\n{pointer} {the_value}"

    def __str__(self):
        return (
            "Please, enter following values:\n```"
            + "\n\n".join(
                self.prepare_string(key, value) for key, value in self.items.items()
            )
            + "\n```"
            + (f"\nPrompt: `{self.prompt}`" if self.prompt else "")
        )

    async def edit(self, event: Event) -> discord.Message:
        try:
            assert self.prev_event_message.id != event.message.id
            await self.prev_event_message.delete()
        except Exception:
            pass

        self.prev_event_message = event.message
        await self.message.edit(content=self)

        return self.message

    async def __call__(self, event: Event) -> discord.Message | None:
        if event.name not in ("message", "message_edit"):
            return None

        content = event.message.content
        prefixes = (*event.prefixes, "#")
        if content.startswith(prefixes):
            return None

        content = content.removeprefix("\\").removesuffix("\\")
        prefix = event.get_variable("editing_prefix") or ">"

        try:
            if content.startswith(prefix):
                return await self.command(content.removeprefix(prefix).strip(), event)

            key = self.keys[self.current_key]

            if func := self.template.converters.get(key):
                content = func(content, event)
                if isawaitable(content):
                    content = await content

        except Exception as ex:
            self.prompt = str(ex)
            return await self.edit(event)

        self.items[key] = content
        self.next()
        return await self.edit(event)

    async def command(self, content: str, event: Event) -> discord.Message:
        if content == "exit":
            self.exit()

        elif content == "end":
            await self.end(event)

        elif content == "next":
            self.next()

        elif content == "prev":
            self.prev()

        elif content == "clear":
            self.items[self.keys[self.current_key]] = None
            self.next()

        elif content == "empty":
            self.items[self.keys[self.current_key]] = ""
            self.next()

        return await self.edit(event)

    def exit(self) -> None:
        self.state.pop_redirect(self)
        self._timer.stop()
        self.prompt = "Exited."

    async def cancel(self) -> None:
        self.exit()

    async def _timer_exit(self) -> None:
        self.state.pop_redirect(self)
        self.prompt = "Timeout."
        await self.message.edit(content=self)

    async def end(self, event: Event) -> None:
        # name = self.template.__name__ + "." + self.template.extension
        # fp = f"~/{name}"  # f"~/.autostart/{name}"
        content, fp = self.template.finalize(**self.items)
        fp = self.path or fp

        file = await get_path(fp, event=event, directory=False, create=True)
        await file.write(content, event=event)

        self.exit()
        self.prompt = f"Saved as {fp!r}."

        get_state = state_command.get(self.template.destination)
        await state_command.reset(get_state(event), get_state, event)

    def next(self) -> None:
        if self.current_key == len(self.keys) - 1:
            self.current_key = 0
        else:
            self.current_key += 1

    def prev(self) -> None:
        if self.current_key == 0:
            self.current_key = len(self.keys) - 1
        else:
            self.current_key -= 1
