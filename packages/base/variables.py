from __future__ import annotations

from models.packages import Command
from models.errors import CommandError
import regex
from structure.filesystem import RegularFile
from structure.data import get_path
from models.extra import required, has_group
from models.utils import get_discord_id, get_pair_not_strict, get_pair
from parser.wrapper import Assignment
from parser import get_processor
import ujson
import shlex
import inspect

from typing import Any, Callable, Coroutine, Literal, Optional, Pattern
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result

if False:
    from models.typings import AllStateType, Some


class export(Command):
    """
    Turn variables or functions into permanent or temporary.
    """

    usage = "%(prog)s [options*] <name[=value]+>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "name",
            nargs="+",
            help="name of variable"
            + (" (or key=value pattern)" if cls.name == "export" else ""),
        )
        cls.argparser.add_argument(
            "-t",
            "--temporary",
            action="store_true",
            help="export variable from permanent to temporary storage",
        )
        cls.argparser.add_argument(
            "-f",
            "--functions",
            action="store_true",
            help="names are actually functions",
        )

    @classmethod
    @required("name")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> None:
        export = not args.temporary
        if args.functions:
            pop_ = event.pop_function
            set_ = event.set_function
        else:
            pop_ = event.pop_variable
            set_ = event.set_variable

        def swap(name):
            return set_(name, pop_(name, not export), export)

        for name in args.name:
            if match := Assignment.pattern.match(name):
                Assignment.function(match, event, export)
            else:
                swap(name)


class unset(export):
    """
    Unset variables or functions.
    """

    @classmethod
    @required("name")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> None:
        export = not args.temporary
        if args.functions:
            pop = event.pop_function
        else:
            pop = event.pop_variable

        for name in args.name:
            pop(name, export)


class storage(Command):
    """
    Sotre or get variables in current state.

    To get variable, only place its name.
    To store variable, also provide stdin.
    """

    usage = "%(prog)s [options*] <name>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("name", help="name of variable")
        cls.argparser.add_argument(
            "-p",
            "--permanent",
            action="store_true",
            help="determine if value is in permanent storage",
        )
        cls.argparser.add_argument(
            "-E",
            "--edit",
            action="store_true",
            help="edit variable instead of rewriting (only w/ stdin)",
        )
        cls.argparser.add_argument(
            "-P",
            "--pop",
            action="store_true",
            help="pop variable instead of just getting (only w/o stdin)",
        )
        cls.argparser.add_argument(
            "-l",
            "--last",
            action="store_const",
            dest="convert",
            const="last",
            help="store last value from stdin",
        )
        cls.argparser.add_argument(
            "-A",
            "--array",
            action="store_const",
            dest="convert",
            const="list",
            help="store list of values from stdin",
        )

    @classmethod
    @required("name")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> Any:
        if not stdin:
            if args.pop:
                return event.pop_variable(args.name, args.permanent)

            return event.get_variable(args.name)

        else:
            if args.convert == "last":
                stdin = stdin.data[-1]
            elif args.convert == "list":
                stdin = stdin.data

            if args.edit:
                if args.convert:

                    def edit(previous_value, value):
                        return previous_value + value

                else:

                    def edit(previous_value, value):
                        return previous_value >> value

            else:
                edit = None

            event.set_variable(args.name, stdin, args.permanent, edit)


class state(Command):
    """
    Select either guild or user state and do something with it
    or set as current.
    """

    usage = "%(prog)s [options*] [guild|user]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "type", choices=("guild", "user"), default="", help="type of state"
        )
        cls.argparser.add_argument(
            "-c",
            "--clear",
            action="store_true",
            help="clear state variables and functions",
        )
        cls.argparser.add_argument(
            "-r",
            "--reset",
            "--reload",
            action="store_true",
            help="delete current state",
            dest="reset",
        )

    @classmethod
    @has_group("admin")
    def get_guild_state(cls, event: Event):
        return event.guild_state

    @classmethod
    def get_user_state(cls, event: Event):
        return event.user_state

    @classmethod
    def get_state(cls, event: Event):
        return event.state

    @classmethod
    def get(cls, type_: str) -> Callable[[Event], AllStateType]:
        return getattr(cls, "get_" + (type_ and type_ + "_") + "state")

    @classmethod
    async def reset(
        cls,
        state: AllStateType,
        get_state: Callable[[Event], AllStateType],
        event: Event,
    ) -> None:
        active = state.reset()
        try:
            new_state = get_state(event)
            await new_state.setup(event)
            for proc in active:
                proc.state = new_state
                new_state.append_event(proc)

        except Exception:
            __import__("traceback").print_exc()

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> None:
        get_state = cls.get(args.type)
        state = get_state(event)
        if args.reset:
            await cls.reset(state, get_state, event)

        elif args.clear:
            state.clear()

        elif state is not event.original_state or not args.type:
            event.state.remove_event(event)
            event.pick_state(args.type or None)
            await event.state.setup(event)
            event.state.append_event(event)


class params(Command):
    """
    Setup special parameters.
    """

    usage = "%(prog)s [options*]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "params", nargs="*", type=get_pair_not_strict, help="any parameters"
        )
        cls.argparser.add_argument(
            "-s", "--show", action="store_true", help="print final options"
        )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str | None:
        for option, value in args.params:
            if value is None:
                value = event[option]
                if type(value) is bool:
                    value = not value

            event.apply_option(option, value)

        if args.show:
            return "\n".join(
                f"{option} is {value}" if type(value) is bool else f"{option}={value!r}"
                for option, value in event.result.total_options.items()
            )


class alias(Command):
    """
    Create alias for command or sequence of instructions.
    """

    usage = "%(prog)s [name=[value]*]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "pair", nargs="*", type=get_pair, help="key-value pair of aliases"
        )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str | None:
        if not args.pair:
            return "\n".join(
                f"{key}={' '.join(str(i) for i in value)!r}"
                for key, value in event.aliases.items()
            )

        for name, value in args.pair:
            if not value:
                event.pop_alias(name)
            processor = await get_processor(value)
            parsed = await processor.process_self()
            event.set_alias(name, parsed)


class config(Command):
    """
    Easy-to-use configuration frontend.

    See ~/.clirc or ~guild/.config.json to edit manually.
    After editing manually execute `state -r` or `state guild -r`
    to apply changes.
    """

    usage = "%(prog)s [name=[value]*]"

    extra_export: Pattern = regex.compile("^export *$", regex.M)

    @staticmethod
    def str_func(value: str, prev: Any, event: Event) -> str:
        return value

    @staticmethod
    def list_func(
        value: str,
        prev: list[Some] | None,
        event: Event,
        convert: Optional[Callable[[str], Some]] = None,
    ) -> list[Some]:
        if convert:
            value = convert(value)

        if prev is None:
            prev = []

        if value in prev:
            prev.remove(value)
        else:
            prev.append(value)

        return prev

    @classmethod
    def list_func_fab(cls, convert: Callable[[str], Some]):
        def inner(value: str, prev: list[Some] | None, event: Event):
            return cls.list_func(value, prev, event, convert)

        return inner

    @classmethod
    def check_fab(
        cls,
        convert: Callable[[str], Some],
        check: Callable[[Some, Event], bool | Coroutine[Any, Any, bool]],
    ):
        async def inner(value: str, prev: Some | None, event: Event):
            value = convert(value)

            checked = check(value, event)
            if inspect.isawaitable(checked):
                checked = await checked

            if not checked:
                raise CommandError(cls, "Inapropriate value")

            return value

        return inner

    @classmethod
    async def check_guild(cls, value: int, event: Event) -> bool:
        return (
            await event.client.fetch_object(value, event, event.guild)
        ).guild == event.guild

    @classmethod
    def setup(cls):
        cls.rc_export = {
            "prefix": cls.str_func,
            "timezone": cls.str_func,
            "date_format": cls.str_func,
            "timedelta_format": cls.str_func,
            "editing_prefix": cls.str_func,
        }
        cls.guild_config = {
            "moderators": cls.list_func_fab(get_discord_id),
            "public_roles": cls.list_func_fab(get_discord_id),
            "mute_role": cls.check_fab(get_discord_id, cls.check_guild),
            "log_channel": cls.check_fab(get_discord_id, cls.check_guild),
        }

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "pair", nargs="*", type=get_pair, help="key-value configuration pair"
        )
        cls.argparser.add_argument(
            "-g", "--guild", action="store_true", help="edit guild settings"
        )

    @classmethod
    async def get_configs(
        cls, event: Event, args: Namespace
    ) -> tuple[RegularFile | None, RegularFile]:
        if args.guild:
            cfg = await get_path(
                "~guild/.config.json", event=event, directory=False, create=True
            )
            if cfg.content is None:
                default = await get_path("/scripts/.guild_config.json", event=event)
                content = await default.read(event=event)
                await cfg.write(content, event=event)
        else:
            cfg = None

        clirc = await get_path(
            f"~{'guild' if args.guild else ''}/.clirc",
            event=event,
            directory=False,
            create=True,
        )
        if clirc.content is None:
            default = await get_path("/scripts/.clirc", event=event)
            content = await default.read(event=event)
            await clirc.write(content, event=event)

        return cfg, clirc

    @classmethod
    def read_content(
        cls, content: str, kind: Literal["rc", "json"]
    ) -> tuple[dict[str], str | None]:
        if kind == "json":
            values = ujson.loads(content)
            text = None

        else:
            lines = content.splitlines()

            values = {}
            for num, line in enumerate(lines):
                if not line.startswith("export "):
                    continue

                content = shlex.split(line)[1:]  # doesn't count \\
                for p_num, part in enumerate(content):
                    try:
                        key, value = get_pair(part)
                    except Exception:
                        continue

                    if key not in cls.rc_export:
                        continue

                    values[key] = value
                    content[p_num] = f"{key}={{{key}!r}}"

                lines[num] = f"export {' '.join(content)}"

            text = "\n".join(lines)

        return values, text

    @classmethod
    def finalize_content(cls, values: dict[str], text: str | None) -> str:
        if text is None:
            return ujson.dumps(values, escape_forward_slashes=False, indent=2)
        else:
            for key, value in values.items():
                prev = text
                if value is None:
                    text = text.replace(f" {key}={{{key}!r}}", "")
                else:
                    text = text.format(**{key: value})
                    if prev == text:
                        if not text.endswith("\n"):
                            text += "\n"
                        text += f"export {key}={value!r}\n"

            text = cls.extra_export.sub("", text)
            return text

    @classmethod
    async def set_value(
        cls,
        key: str,
        file: RegularFile,
        kind: Literal["rc", "json"],
        func: Callable[[str, Any, Event], Any],
        value: str,
        event: Event,
    ) -> None:
        content = await file.read(event=event)

        values, text = cls.read_content(content, kind)

        if not value:
            result = None
        else:
            result = func(value, values.get(key), event)
            if inspect.isawaitable(result):
                result = await result
        values[key] = result

        content = cls.finalize_content(values, text)

        await file.write(content, event=event)

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> None:
        cfg, clirc = await cls.get_configs(event, args)

        for key, value in args.pair:
            if func := cls.rc_export.get(key):
                kind = "rc"
                current = clirc
            elif func := cls.guild_config.get(key):
                kind = "json"
                current = cfg
            else:
                continue

            await cls.set_value(key, current, kind, func, value, event)

        get_state = state.get("guild" if args.guild else "user")
        await state.reset(get_state(event), get_state, event)
