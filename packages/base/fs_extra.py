from __future__ import annotations

import discord
from models.packages import Command
from models.extra import required, Timer
from structure.data import get_path
import regex

from typing import Generator, Optional, Pattern
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result

if False:
    from models.typings import FileType


class ed(Command):
    """
    Edit file via discord chat system.

    To append text, simpy write it without any prefixes.
    To ignore text, start text with "#".
    Write bot commands as usual (with your prefix).

    Prefix: `>` (`>>` in case when your actual prefix is `>`)
    Commands: exit, save, clear, joinline, newline, clearline,
    splitline, backline, back [num], append, insert,
    pos <line> <sym>, line <n>, sym <n>
    """

    usage = "%(prog)s <file>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("file", help="any file")

    @classmethod
    @required("file")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> None:
        await cls.initialize(event, args, stdin)
        event.apply_option("send", False)

    cc_sym = "▄"
    cc_sym_rev = "▀"

    def __init__(self, event: Event, file: FileType, lines: list[str]):
        self.state = event.state
        self.short_content = event.short_content
        self.file = file
        self.ext = file.extension
        self.lines = lines
        self.current = {"line": 0, "symbol": 0}
        self.mode = "append"
        self.prompt: Optional[str] = None
        self.message: discord.Message = None
        self.prev_event_message = None
        self._timer = Timer(300, self._timer_exit)
        self.pid: int = None

    def set_pid(self, pid: int) -> None:
        self.pid = pid

    @classmethod
    async def initialize(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> "ed":
        file = await get_path(args.file, event=event, directory=False, create=True)

        content = await file.read(event=event) or "\n"
        lines = content.splitlines()

        self = cls(event, file, lines)
        self.message = await event.send(self)
        self.state.add_redirect(self)
        self._timer.start()

        return self

    async def edit(self, event: Event) -> discord.Message:
        try:
            assert self.prev_event_message.id != event.message.id
            await self.prev_event_message.delete()
        except Exception:
            pass

        self.prev_event_message = event.message
        await self.message.edit(content=self)

        return self.message

    @property
    def content(self) -> str:
        return "\n".join(self.lines)

    @property
    def current_line(self) -> str:
        return self.lines[self.current["line"]]

    def __str__(self):
        lines = self.lines.copy()

        current_line = self.current_line
        line_num = self.current["line"]
        symbol = self.current["symbol"]
        max_lines = len(lines)
        max_line_num_width = len(str(max_lines))

        lines[line_num] = current_line[:symbol] + self.cc_sym + current_line[symbol:]

        first = line_num - 6
        if first < 0:
            first = 0
        last = line_num + 7
        if last > max_lines:
            last = max_lines

        max_line_len = len(max(lines[first:last], key=len))
        col_counter = (
            ("".join(str(i) for i in range(10)) * (max_line_len // 10))[1:]
            + "".join(str(i) for i in range(max_line_len % 10 + 1))
        ).replace("0", " ")
        col_counter = (
            ("_" * (max_line_num_width) + "| ")
            + col_counter[:symbol]
            + self.cc_sym_rev
            + col_counter[symbol + 1 :]
        )

        content = (
            f"`{self.file.name}` — *{self.state.object}*\n"
            f"```{self.ext}\n{col_counter}\n"
            + "\n".join(
                f"""{
                    str(num + 1 + first).rjust(max_line_num_width, ' ')
                    if num + first != line_num else ">" * max_line_num_width
                }| {line}"""
                for num, line in enumerate(lines[first:last])
            )
        )

        if len(content) >= 1800:
            content = content[:1800] + "<..>"

        return content + "\n```\n" + self.footer

    @property
    def footer(self) -> str:
        return (
            f"**({self.current['line'] + 1}; "
            f"{self.current['symbol'] + 1})**"
            f" - *[{len(self.lines)} lines; "
            f"{len(self.current_line)} symbols]*"
            f" - Mode: `{self.mode}`"
            + (f"\n\nPrompt: `{self.prompt}`" if self.prompt else "")
        )

    def back(self, num: int) -> None:
        current_line_num = self.current["line"]
        current_line = self.lines[current_line_num]
        first_symbol = self.current["symbol"]

        symbol = first_symbol - num
        if symbol < 0:
            symbol = 0

        new_string = current_line[:symbol] + current_line[first_symbol:]

        self.lines[current_line_num] = new_string

        self.current["symbol"] = symbol

    def backline(self) -> None:
        current_line_num = self.current["line"]
        del self.lines[current_line_num]

        if current_line_num > len(self.lines) - 1:
            self.current["line"] -= 1

        self.current["symbol"] = 0

    def joinline(self) -> None:
        current_line_num = self.current["line"]
        if current_line_num == 0:
            return

        current_line = self.lines[current_line_num]
        prev_line = self.lines[current_line_num - 1]
        self.lines[current_line_num - 1] += current_line
        del self.lines[current_line_num]

        self.current["line"] -= 1
        self.current["symbol"] = len(prev_line)

    def splitline(self) -> None:
        current_line_num = self.current["line"]
        current_line = self.lines[current_line_num]
        symbol = self.current["symbol"]
        before, after = current_line[:symbol], current_line[symbol:]
        self.lines.insert(current_line_num + 1, after)
        self.lines[current_line_num] = before

    def newline(self) -> None:
        current_line_num = self.current["line"]
        self.lines.insert(current_line_num + 1, "")
        self.current["line"] += 1
        self.current["symbol"] = 0

    def clearline(self) -> None:
        current_line_num = self.current["line"]
        self.lines[current_line_num] = ""
        self.current["symbol"] = 0

    def clear(self) -> None:
        self.lines.clear()
        self.lines.append("")
        self.current["line"] = 0
        self.current["symbol"] = 0

    async def command(self, content: str, event: Event) -> discord.Message:
        line, symbol = None, None

        if content == "exit":
            self.exit()

        elif content == "save":
            await self.save(event)

        elif content == "clear":
            self.clear()

        elif content == "joinline":
            self.joinline()

        elif content == "splitline":
            self.splitline()

        elif content == "newline":
            self.newline()

        elif content == "clearline":
            self.clearline()

        elif content == "backline":
            self.backline()

        elif content in ("append", "insert"):
            self.mode = content

        elif content.startswith("back"):
            string = content.removeprefix("back").strip()
            num = int(string) if string else 1
            self.back(num)

        elif content.startswith("pos"):
            values = (int(i) for i in content.removeprefix("pos").strip().split())
            line = next(values) - 1
            symbol = next(values) - 1

        elif content.startswith("line"):
            line = int(content.removeprefix("line")) - 1

        elif content.startswith("sym"):
            symbol = int(content.removeprefix("sym")) - 1

        if line is not None:
            if line < 0 or line > (len(self.lines) - 1):
                self.prompt = "out of bounds: line"
                line = None
            else:
                self.current["line"] = line
        else:
            line = True

        if line is not None and symbol is not None:
            if symbol < 0 or symbol > len(self.current_line):
                self.prompt = "out of bounds: symbol"
                if line is not True:
                    self.prompt += ", set to 1"
                    self.current["symbol"] = 0
            else:
                self.current["symbol"] = symbol

        return await self.edit(event)

    async def __call__(self, event: Event) -> discord.Message | None:
        if event.name not in ("message", "message_edit"):
            return None

        content = event.message.content
        prefixes = (*event.prefixes, "#")
        if content.startswith(prefixes):
            return None

        content = content.removeprefix("\\").removesuffix("\\")
        self.prompt = ""
        prefix = event.get_variable("editing_prefix") or ">"

        if content.startswith(prefix):
            return await self.command(content.removeprefix(prefix).strip(), event)

        new_lines = content.split("\n")
        last_num = len(new_lines) - 1
        mode = self.mode

        for num, line in enumerate(new_lines):
            current_line_num = self.current["line"]
            symbol = self.current["symbol"]  # 5

            current_line = self.lines[current_line_num]
            before = current_line[:symbol]
            after = current_line[symbol:]

            if mode == "append":
                before_new = before + line

                self.lines[current_line_num] = before_new
                if num != last_num:
                    self.lines.insert(current_line_num + 1, after)
                    self.current["line"] += 1
                    self.current["symbol"] = 0
                else:
                    self.current["symbol"] = len(before_new)
                    self.lines[current_line_num] += after

            elif mode == "insert":  # TODO
                if len(line) >= len(after):
                    new = line
                else:
                    new = line + after[len(line) :]
                self.lines[current_line_num] = before + new
                if num != last_num:
                    self.current["line"] += 1
                    self.current["symbol"] = 0
                else:
                    self.current["symbol"] += len(line)

        self._timer.start()
        return await self.edit(event)

    async def save(self, event: Event) -> None:
        await self.file.write(self.content, event=event)
        self.prompt = "Saved."

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


class grep(Command):
    """
    Search for pattern in each file.
    """

    usage = "%(prog)s [options*] <pattern> [file*]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("pattern", default="", help="pattern to search with")
        cls.argparser.add_argument("file", nargs="*", default=(), help="any file")
        cls.argparser.add_argument(
            "-e", "--regex", action="store_true", help="use regex to search"
        )
        cls.argparser.add_argument(
            "-n",
            "--line-number",
            action="store_true",
            help="print line number with output lines",
        )
        cls.argparser.add_argument(
            "-o", "--only-matching", action="store_true", help="print only matched"
        )
        cls.argparser.add_argument(
            "-v",
            "--invert-match",
            action="store_true",
            help="select non-matching lines",
        )
        cls.argparser.add_argument(
            "-i", "--ignore-case", action="store_true", help="ignore case distinctions"
        )
        cls.argparser.add_argument(
            "-U", "--unique", action="store_true", help="only unique matches"
        )

    @classmethod
    def match_lines(
        cls, query: Pattern, content: str, args: Namespace
    ) -> Generator[tuple[str, str], None, None]:
        invert = args.invert_match
        for num, line in enumerate(content.splitlines()):
            found: list[str] = query.findall(line)
            if found and invert or not found and not invert:
                continue
            if args.only_matching:
                for match in found:
                    yield num + 1, match
            else:
                yield num + 1, line

    @classmethod
    def find_all(cls, contents: dict[str, str], args: Namespace) -> str:
        flag = regex.IGNORECASE if args.ignore_case else 0
        if args.regex:
            query: Pattern = regex.compile(args.pattern, flag)
        else:
            query: Pattern = regex.compile(regex.escape(args.pattern), flag)

        found = {}
        for name, content in contents.items():
            result = list(cls.match_lines(query, content, args))
            if result:
                found[name] = result

        line_number = args.line_number
        final = []
        unique = set()
        for name, sub in found.items():
            for num, value in sub:
                if args.unique and value in unique:
                    continue
                unique.add(value)

                if line_number:
                    final.append((f"{name}:" if name else "") + f"{num}: {value}")
                else:
                    final.append(value)

        return "\n".join(final)

    @classmethod
    @required("pattern")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        contents: dict[str, str] = {}
        if stdin:
            contents["-"] = str(stdin)

        for route in args.file:
            file = await get_path(route, event=event, directory=False)
            contents[route] = str(await file.read(event=event))

        if len(contents) == 1:
            contents = {"": tuple(contents.values())[0]}

        found = cls.find_all(contents, args)
        return found
