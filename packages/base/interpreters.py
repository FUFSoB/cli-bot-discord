from __future__ import annotations

import io
import pydoc
import traceback
import discord  # NOQA
from models.packages import Command, ArgParser
from models.utils import run_in_executor, aexec
from models.errors import ShellError
from models.extra import required, types, convert_type_fab
from structure.data import get_path
from parser import get_processor
import shlex

from typing import Awaitable, Generator, Literal, Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result
from parser.processing import Processor


class Help(pydoc.help.__class__):
    _GoInteractive = object()

    def call(self, request=_GoInteractive):
        if request is not self._GoInteractive:
            return self.help(request)
        else:
            return self.help(self.help)


@run_in_executor
def noaexec(code: str, glob: dict[str], loc: dict[str]) -> Awaitable[None]:
    return exec(code, glob, loc)


class cli(Command):
    """
    Execute input as command sequence.
    """

    usage = "%(prog)s [options*] [file]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("file", help="file to execute")
        cls.argparser.add_argument("-c", "--command", help="code to execute")

    @classmethod
    @required("stdin", "command", "file")
    async def get_code(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> tuple[str, str]:
        if args.command:
            code = args.command
            source = "command-line argument"
        elif args.file:
            file = await get_path(args.file, event=event, directory=False)
            code = await file.read(event=event)
            source = str(file.path)
        else:
            code = str(stdin)
            source = "stdin"

        return code, source

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> Result:
        code, _ = await cls.get_code(event, args, stdin)

        return await (await get_processor(code)).finalize(event, True)


class interp(cli):
    """
    Interpretate python code in bot's scope.
    """

    group = "root"

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str | ShellError:
        code, _ = await cls.get_code(event, args, stdin)

        passed = {**locals(), **globals()}

        is_async = any(i in code for i in ("await ", "async with", "async for"))
        with io.StringIO() as where_to_write:

            def new_print(*args, **kwargs):
                kwargs.update(file=where_to_write)
                print(*args, **kwargs)

            def new_help(request):
                func = Help(output=where_to_write)
                return func(request)

            passed.update({"print": new_print, "help": new_help})

            try:
                if is_async:
                    await aexec(**passed)
                else:
                    await noaexec(code, globals(), passed)
            except Exception:
                output = ShellError(traceback.format_exc())
            else:
                output = where_to_write.getvalue()

        return output


class brainfuck(cli):
    """
    Brainfuck code interpreter.
    """

    symbols = (".", ",", "[", "]", "<", ">", "+", "-")

    # https://github.com/pocmo/Python-Brainfuck

    @classmethod
    @run_in_executor
    def evaluate(cls, code: str) -> Awaitable[Generator[str, None, None]]:
        code = [i for i in code if i in cls.symbols]
        bracemap = cls.buildbracemap(code)

        cells, codeptr, cellptr = [0], 0, 0

        while codeptr < len(code):
            command = code[codeptr]

            if command == ">":
                cellptr += 1
                if cellptr == len(cells):
                    cells.append(0)

            elif command == "<":
                cellptr = 0 if cellptr <= 0 else cellptr - 1

            elif command == "+":
                cells[cellptr] = cells[cellptr] + 1 if cells[cellptr] < 255 else 0

            elif command == "-":
                cells[cellptr] = cells[cellptr] - 1 if cells[cellptr] > 0 else 255

            elif command == "[" and cells[cellptr] == 0:
                codeptr = bracemap[codeptr]
            elif command == "]" and cells[cellptr] != 0:
                codeptr = bracemap[codeptr]
            elif command == ".":
                yield chr(cells[cellptr])
            # if command == ",":
            #     cells[cellptr] = ord("")

            codeptr += 1

    @staticmethod
    def buildbracemap(code: str) -> dict[int, int]:
        temp_bracestack: list[int] = []
        bracemap: dict[int, int] = {}

        for position, command in enumerate(code):
            if command == "[":
                temp_bracestack.append(position)
            if command == "]":
                start = temp_bracestack.pop()
                bracemap[start] = position
                bracemap[position] = start

        return bracemap

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        code, _ = await cls.get_code(event, args, stdin)

        return "".join(await cls.evaluate(code))


class argparse(cli):
    """
    Interpretate command sequence with argument parser.
    """

    epilog = """
    File model:
    ######### test.sh #########
    #!/bin/{cls.name}

    ! name
    @ description
    % usage
    $ epilog
    ; arg | action & | nargs & | const & | default & | type & | choices & & &
          | help & | metavar & | dest &
    ; -o --opt | required

    |||

    echo $arg $opt
    ###########################

    And then:
    ./test.sh "Print me as argument" -o "And me as option!"
    ###########################

    Types available: {cls.types}
    """

    types = ", ".join(types)

    reserved: dict[str, str] = {
        "!": "prog",
        "@": "description",
        "%": "usage",
        "$": "epilog",
        ";": "arg",
        "|": "kwarg",
        "&": None,
    }

    @classmethod
    def generate_argparser(cls):
        super().generate_argparser()
        cls.argparser.add_argument(
            "-s",
            "--store",
            action="store_true",
            help="store as executable instead of executing",
        )
        cls.argparser.add_argument(
            "-m",
            "--merge",
            action="store_true",
            help="merge multiple values into one string",
        )

    @staticmethod
    def parse(content: str) -> tuple[list[str], str]:
        if content.startswith("#!"):
            content = content.split("\n", 1)[-1]
        to_parse, content = content.split("\n|||", 1)

        to_parse = "\n".join(line.split("#", 1)[0] for line in to_parse.split("\n"))

        return shlex.split(to_parse), content

    @classmethod
    def complete(cls, content: str) -> tuple[ArgParser, str]:
        argparser = None
        reserved = cls.reserved
        parsed, content = cls.parse(content)

        next = None
        args = []
        kwarg_name = None
        kwargs = {}

        for element in parsed:
            if element in reserved:
                next = reserved[element]
                if next == "arg":
                    if not args:
                        argparser = ArgParser(**kwargs)
                    else:
                        argparser.add_argument(*args, **kwargs)

                    args.clear()
                    kwargs.clear()

                continue

            if next in ("prog", "description", "usage", "epilog"):
                if next in kwargs:
                    kwargs[next] += " " + element
                else:
                    kwargs[next] = element

            elif next == "arg":
                args.append(element)

            elif next == "kwarg":
                kwarg_name = element
                next = "value"

            elif next == "value":
                if kwarg_name == "type":
                    kwargs[kwarg_name] = convert_type_fab(argparser.prog, element)

                elif kwarg_name == "nargs":
                    try:
                        element = int(element)
                    except ValueError:
                        pass
                    kwargs[kwarg_name] = element

                elif kwarg_name == "required":
                    kwargs[kwarg_name] = True

                elif kwarg_name == "choices":
                    if not kwargs.get(kwarg_name):
                        kwargs[kwarg_name] = []

                    kwargs[kwarg_name].append(element)

                elif kwargs.get(kwarg_name):
                    kwargs[kwarg_name] += " " + element

                else:
                    kwargs[kwarg_name] = element

        else:
            if args:
                argparser.add_argument(*args, **kwargs)
            elif not argparser:
                argparser = ArgParser(**kwargs)

            argparser.add_argument("-h", "--help", action="store_true")

        return argparser, content

    @staticmethod
    def store_args(event: Event, inside: Namespace, args: Namespace) -> None:
        for name, value in args._get_kwargs():
            if name == "help":
                continue
            if inside.merge and type(value) is list:
                value = " ".join(str(v) for v in value)
            event.set_variable(name, value)

    @classmethod
    async def store_command(
        cls,
        evnt: Event,
        inside: Namespace,
        argparser: ArgParser,
        code: str,
        to_parse: str,
        source: str,
    ) -> None:
        processor: Processor = await get_processor(to_parse)

        class custom(Command):
            apply_to_package = False
            file_source = source

            @classmethod
            def setup(cls):
                cls.name = argparser.prog
                cls.description = argparser.description
                cls.usage = argparser.usage
                cls.epilog = argparser.epilog
                cls.argparser = argparser
                cls.source = code
                cls.help_message = argparser.format_help().strip()
                return cls

            @staticmethod
            async def function(
                event: Event, args: Namespace, stdin: Optional[Result]
            ) -> Result:
                cls.store_args(event, inside, args)
                return await processor.finalize(event, True)

        evnt.set_function(custom.name, custom, export=True)

    @classmethod
    async def execute_command(
        cls, event: Event, inside: Namespace, argparser: ArgParser, to_parse: str
    ) -> Result:
        args = argparser.parse_args(event.state.command_args[1:])

        if getattr(args, "help", False):
            return argparser.format_help().strip()

        cls.store_args(event, inside, args)

        return await (await get_processor(to_parse)).finalize(event)

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> Result | None:
        code, source = await cls.get_code(event, args, stdin)
        argparser, content = cls.complete(code)

        if args.store:
            await cls.store_command(event, args, argparser, code, content, source)
        else:
            return await cls.execute_command(event, args, argparser, content)


class event_(cli):
    """
    Interpretate command sequence for event.
    """

    usage = "%(prog)s [options*] [file] <-n name+>"
    epilog = "Events available: {cls.events}"

    events = ", ".join(
        (
            "any",
            "typing",
            "message",
            "message_edit",
            "message_delete",
            "raw_message_edit",
            "raw_message_delete",
            "reaction_add",
            "reaction_remove",
            "raw_reaction_add",
            "raw_reaction_remove",
            "member_join",
            "member_remove",
            "member_ban",
            "member_unban",
        )
    )

    @classmethod
    def generate_argparser(cls):
        super().generate_argparser()
        cls.argparser.add_argument("-n", "--name", action="append", help="event name")
        cls.argparser.add_argument(
            "-s", "--store", action="store_true", help="use event multiple times"
        )
        cls.argparser.add_argument(
            "-a", "--apply", action="store_true", help="apply result to command output"
        )
        cls.argparser.add_argument(
            "-p",
            "--prefixed",
            action="store_true",
            help="do not skip prefixed messages",
        )
        cls.argparser.add_argument(
            "-b", "--bots", action="store_true", help="do not ignore bot users"
        )

    @classmethod
    @required("name", option=True)
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        await cls.initialize(event, args, stdin)
        return f"Listening to {', '.join(args.name)}"

    def __init__(self, event: Event, args: Namespace, processor: Processor):
        self.state = event.state
        self.names: list[str] = args.name
        self.short_content = "{" + ", ".join(self.names) + "}"
        self.store: bool = args.store
        self.apply: bool = args.apply
        self.bots: bool = args.bots
        self.prefixed: bool = args.prefixed
        self.processor = processor
        self.pid: int = None

    def set_pid(self, pid: int) -> None:
        self.pid = pid

    @classmethod
    async def initialize(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> "event_":
        content, _ = await cls.get_code(event, args, stdin)
        processor: Processor = await get_processor(content)
        await processor.process_self()

        self = cls(event, args, processor)
        self.state.add_redirect(self)
        return self

    async def __call__(self, event: Event) -> Literal[True] | None:
        if event.name not in self.names:
            return None

        if getattr(event.user, "bot", None) and not self.bots:
            return None

        if (
            not self.prefixed
            and event.name in ("message", "message_edit", "raw_message_edit")
            and event.prefixed
        ):
            return None

        _, returned, raised = await event.finalize_specific(
            self.processor, (None if self.apply else True), True
        )

        if not self.store:
            self.state.pop_redirect(self)

        if not self.apply and (returned or raised):
            return True

        return None

    async def cancel(self) -> None:
        self.state.pop_redirect(self)
