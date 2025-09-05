from __future__ import annotations

import os
import importlib
import argparse
import inspect
from typing import Any, Callable, Coroutine, Iterator, Optional, TYPE_CHECKING

# from discord.utils import get
from structure.data import get_path
from .errors import (
    CommandPermissionError,
    ReturnError,
    KeywordError,
    BaseError,
    InternalError,
    ArgparseError,
)
from .utils import classproperty

if TYPE_CHECKING:
    from .event import Event
    from parser.wrapper import Result
    from .typings import FunctionType, FileType
    from argparse import Namespace

__all__ = (
    "packages",
    "events",
    "file_commands",
    "get_commands",
    "get_command",
    "Package",
    "Command",
)

packages: list["Package"] = []
events: dict[str, list[Callable[[Event], Coroutine]]] = {}
file_commands: list["Command"] = []
reloading: bool = False


class PackageMeta(type):
    def __init__(
        cls: "Package", name: str, bases: tuple[type], clsdict: dict[str, Any]
    ):
        super(PackageMeta, cls).__init__(name, bases, clsdict)
        if len(cls.mro()) > 2:
            packages.append(cls)

            cls.name = cls.__name__

            for attr in dir(cls):
                if not attr.startswith("on_"):
                    continue

                value: Callable[[Event], Coroutine] = getattr(cls, attr)
                if attr in events:
                    events[attr].append(value)
                else:
                    events[attr] = [value]

            if cls.skip_files:
                cls.categories = {"": cls.commands}
                return

            file_dir = cls.__module__.replace(".", "/")
            modules = [
                i.rsplit(".", 1)[0]
                for i in os.listdir(file_dir)
                if not i.startswith("__")
            ]
            cls.categories = {m: [] for m in modules if not m.startswith("_")}

            for module in modules:
                imported = importlib.import_module(cls.__module__ + "." + module)
                if reloading:
                    importlib.reload(imported)

    def __repr__(cls: "Package"):
        return f"<Package {cls.name!r} commands={cls.commands}>"


class Package(metaclass=PackageMeta):
    """
    ParentClass for packages.
    """

    name: str = None
    skip_files: bool = False
    version: str = "0.0"
    categories: dict[str, list["Command"]]
    commands: list["Command"] = []
    _commands_dict: dict[str, "Command"] = None

    @classproperty
    def commands_dict(cls) -> dict[str, "Command"]:
        if not cls._commands_dict:
            cls._commands_dict = {c.name: c for c in cls.commands}
        return cls._commands_dict


class CommandMeta(type):
    def __init__(
        cls: "Command", name: str, bases: tuple[type], clsdict: dict[str, Any]
    ):
        super(CommandMeta, cls).__init__(name, bases, clsdict)
        if len(cls.mro()) > 2:
            if cls.__name__.startswith("_"):
                return

            cls.setup()

            if not cls.apply_to_package:
                return

            package = packages[-1]
            package.commands.append(cls)
            cls.package = package
            cls.category = cls.__module__.rsplit(".", 1)[-1]
            package.categories[cls.category].append(cls)

            cls.source = inspect.getsource(cls).rstrip()
            cls.name = cls.__name__.removesuffix("_")
            cls.description = cls.__doc__ and cls.__doc__.strip().replace(
                "\n" + " " * 4, "\n"
            ).format(cls=cls)
            cls.epilog = cls.epilog and cls.epilog.strip().replace(
                "\n" + " " * 4, "\n"
            ).format(cls=cls)
            cls.file_source = f"/bin/{cls.name}"

            cls.argparser_create()
            cls.generate_argparser()
            cls.argparser_add_help()

    def __repr__(cls: "Command"):
        return f"<Command {cls.name!r}>"

    def __eq__(cls: "Command", other: str | "Command"):
        if type(other) is Command:
            return cls.name == other.name
        else:
            return cls.name == other or other in cls.aliases


class Command(metaclass=CommandMeta):
    """
    ParentClass for commands.
    """

    name: str = None
    source: str = None
    description: str = None
    epilog: Optional[str] = None
    usage: str = "%(prog)s"
    examples: list = []
    argparser: "ArgParser" = None
    help_message: str = None
    group: str = "any"
    apply_to_package: bool = True
    package: Package = None
    file_source: str = None
    aliases: list[str] = []

    @classmethod
    async def unsafe_execute(
        cls, event: Event, parsed: list[str], stdin: Optional[Result] = None
    ) -> Any:
        argparser = cls.argparser

        if cls.group not in event.groups() and "root" not in event.groups():
            raise CommandPermissionError(cls)

        if argparser:
            try:
                parsed = argparser.parse_args(parsed)
            except argparse.ArgumentError as ex:
                raise ArgparseError(cls, ex)

            if getattr(parsed, "help", False):
                return cls.help_message

        return await cls.function(event, parsed, stdin)

    @classmethod
    async def execute(
        cls, event: Event, parsed: list[str], stdin: Optional[Result] = None
    ) -> Any:
        try:
            return await cls.unsafe_execute(event, parsed, stdin)
        except KeywordError:
            raise
        except Exception as ex:
            if event["return_on_error"]:
                if not isinstance(ex, BaseError):
                    ex = InternalError(ex)
                raise ReturnError(ex)
            raise

    @classmethod
    def setup(cls):
        return NotImplemented

    @classmethod
    def argparser_create(cls) -> None:
        cls.argparser = ArgParser(
            prog=cls.name,
            description=cls.description,
            epilog=cls.epilog,
            usage=cls.usage,
        )

    @classmethod
    def generate_argparser(cls):
        return NotImplemented

    @classmethod
    def argparser_add_help(cls) -> None:
        cls.argparser.add_argument("-h", "--help", action="store_true")
        cls.help_message = cls.argparser.format_help().strip()

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result] = None
    ):
        return NotImplemented


# default_packages = [
#     "base",
#     "discord",
#     "files",
#     "music",
#     "root",
#     "tools"
# ]


# def get_commands(
#     active_packages: list[str] = default_packages
# ) -> Iterator[Command]:
#     if active_packages == ["*"]:
#         pkgs = packages
#     else:
#         pkgs = (get(packages, name=name) for name in active_packages)

#     for package in pkgs:
#         yield from package.commands


def get_commands() -> Iterator[Command]:
    for package in packages:
        yield from package.commands


# def get_commands_dict() -> dict[str, Command]:
#     dct = {}
#     for package in packages:
#         dct |= package.commands_dict
#     return dct


async def get_command(name: str, event: Event) -> FunctionType | FileType | list | None:
    if "/" in name:
        return await get_path(name, event=event, directory=False)
    elif func := event.get_function(name):
        return func
    elif alias := event.get_alias(name):
        return alias
    else:
        for command in get_commands():
            if command == name:
                return command
        # return get_commands_dict().get(name)
        # return get(get_commands(), name=name)


def get_events(name: str) -> Iterator[Callable[[Event], Coroutine]]:
    yield from events.get("on_any", ())
    yield from events.get(name, ())


class ClientBotHelpFormatter(argparse.RawDescriptionHelpFormatter):
    def __init__(self, prog, indent_increment=2, max_help_position=7, width=80):  # 40
        super().__init__(prog, indent_increment, max_help_position, width)

    def _format_action_invocation(self, action):
        if not action.option_strings:
            default = self._get_default_metavar_for_positional(action)
            (metavar,) = self._metavar_formatter(action, default)(1)
            return metavar

        else:
            parts = []

            # if the Optional doesn't take a value, format is:
            #    -s, --long
            if action.nargs == 0:
                parts.extend(action.option_strings)

            # if the Optional takes a value, format is:
            #    -s, -S, --long1, --long2 ARGS
            else:
                default = self._get_default_metavar_for_optional(action)
                args_string = self._format_args(action, default)

                parts.extend(action.option_strings[:-1])
                # parts.append('%s %s' % (action.option_strings[-1],
                #                         args_string))
                parts.append(
                    "%s %s"
                    % (
                        action.option_strings[-1],
                        (
                            "<" + args_string.lower() + ">"
                            if not args_string.startswith(("[", "{"))
                            else args_string.lower()
                        ),
                    )
                )

            return ", ".join(parts)

    def _format_action(self, action):
        # determine the required width and the entry label
        help_position = min(self._action_max_length + 2, self._max_help_position)
        help_width = max(self._width - help_position, 11)
        # action_width = help_position - self._current_indent - 2
        action_header = self._format_action_invocation(action)

        tup = self._current_indent, "", action_header
        action_header = "%*s%s\n" % tup

        # collect the pieces of the action help
        parts = [action_header]

        # if there was help for the action, add lines of help text
        if action.help:
            indent_first = help_position
            help_text = self._expand_help(action)
            help_lines = self._split_lines(help_text, help_width)
            full_spaces = " " * self._current_indent
            liner = (
                "  ╘═ "
                if action_header.startswith(full_spaces + "--")
                else " ╘══ " if action_header.startswith(full_spaces + "-") else "╘═══ "
            )

            parts.append("%*s%s%s\n" % (indent_first - 5, "", liner, help_lines[0]))
            for line in help_lines[1:]:
                parts.append("%*s%s\n" % (help_position, "", line))

        # or add a newline if the description doesn't end with one
        elif not action_header.endswith("\n"):
            parts.append("\n")

        # if there are any sub-actions, add their help as well
        for subaction in self._iter_indented_subactions(action):
            parts.append(self._format_action(subaction))

        # return a single string
        return self._join_parts(parts)


class ArgParser(argparse.ArgumentParser):  # add_argument, parse_known_args
    REMAINDER = argparse.REMAINDER
    PARSER = argparse.PARSER
    RawDescriptionHelpFormatter = argparse.RawDescriptionHelpFormatter
    RawTextHelpFormatter = argparse.RawTextHelpFormatter
    ArgumentDefaultsHelpFormatter = argparse.ArgumentDefaultsHelpFormatter
    MetavarTypeHelpFormatter = argparse.MetavarTypeHelpFormatter
    ClientBotHelpFormatter = ClientBotHelpFormatter

    def __init__(self, **kwargs):
        super().__init__(
            add_help=False,
            exit_on_error=False,
            formatter_class=ArgParser.ClientBotHelpFormatter,
            **kwargs,
        )

    def exit(self, status=0, message=None):
        return

    def print_usage(self, file=None):
        return

    def print_help(self, file=None):
        return
