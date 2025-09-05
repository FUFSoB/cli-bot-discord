from __future__ import annotations

from models.packages import Command
from models.errors import FileExistsError, NoFileFoundError
from structure.data import get_path, split_path
from structure.filesystem import RegularFile, file_kinds
from discord import File
import io
from models.utils import get_name, convert_bytes
from inspect import isfunction
from models.extra import required

from typing import Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result

if False:
    from models.typings import AllFilesType, DirectoryType, FileType


class pwd(Command):
    """
    Print full name of current working directory.
    """

    usage = "%(prog)s [-s]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "-s", "--short", action="store_true", help="make home pointers shorter"
        )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        if args.short:
            return event.state.directory.path.short(event=event)
        else:
            return str(event.state.directory.path)


class cd(Command):
    """
    Change current working directory.
    """

    usage = "%(prog)s [path]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("path", help="any directory available")
        cls.argparser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="print an absolute path to directory",
        )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str | None:
        directory = await get_path(args.path or "~", event=event, directory=True)
        event.state.set_directory(directory)
        if args.verbose:
            return str(directory.path)


class ls(Command):
    """
    List directory files.
    """

    usage = "%(prog)s [options*] [path*]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("path", nargs="*", help="any directory to list")
        cls.argparser.add_argument(
            "-a",
            "--all",
            action="store_true",
            help="do not ignore entries starting with .",
        )
        cls.argparser.add_argument(
            "-A",
            "--almost-all",
            action="store_true",
            help="do not list implied . and ..",
        )
        # cls.argparser.add_argument(
        #     "-F", "--full-path",
        #     action="store_true",
        #     help="print absolute path for every file"
        # )
        cls.argparser.add_argument(
            "-R",
            "--relative-path",
            action="store_true",
            help="print relative path for every file",
        )
        cls.argparser.add_argument(
            "-l", "--long", action="store_true", help="use a long listing format"
        )
        cls.argparser.add_argument(
            "-N",
            "--literal",
            action="store_true",
            help="print entry names without quoting",
        )
        cls.argparser.add_argument(
            "-E",
            "--every-line",
            action="store_true",
            help="print single entry per line",
        )
        # cls.argparser.add_argument(
        #     "-p", "--indicate-types",
        #     action="store_true",
        #     help="show type indicators"
        # )
        # cls.argparser.add_argument(
        #     "-U", "--unsorted",
        #     action="store_true",
        #     help="do not sort output alphabetically"
        # )

    width = 60

    @classmethod
    def colprint(cls, iterable: list[str], args: Namespace) -> str:
        final = ""

        strings = [repr(x) if not args.literal and " " in x else x for x in iterable]

        widest = max(len(x) for x in strings)
        columns = [x.ljust(widest) for x in strings]

        colwidth = len(columns[0]) + 2
        perline = cls.width // colwidth

        for i, column in enumerate(columns):
            final += column + "  "
            if i % perline == perline - 1:
                final += "\n"

        return final

    @classmethod
    async def long_string(
        cls, event: Event, file: AllFilesType, name: str = None
    ) -> str:
        name = name or file.name
        kind = file.kind
        ownership = str(file.mode.owner) + ":" + str(file.mode.group)
        perms = str(file.mode)
        size = await file.size(True, event=event)
        if kind in file_kinds and type(size) is int:
            size = convert_bytes(size)
        return (
            f"{name}\n"
            f"\tKind: {kind}\n"
            f"\tOwnership: {ownership}\n"
            f"\tPermissions: {perms}\n"
            f"\tSize: {size}\n"
        )

    @classmethod
    async def longprint(
        cls, event: Event, directory: DirectoryType, args: Namespace
    ) -> str:
        final = []
        all_ = args.all or args.almost_all

        if args.all:
            for name in (".", ".."):
                file = await directory.select(name, event=event)
                final.append(await cls.long_string(event, file, name))

        async for file in directory.read_files(event=event):
            if not all_ and file.name.startswith("."):
                continue
            final.append(await cls.long_string(event, file))

        return "\n".join(final)

    @classmethod
    async def generate(
        cls, args: Namespace, event: Event, key: str, directory: DirectoryType
    ) -> str:
        try:
            if args.long:
                return await cls.longprint(event, directory, args)

            lst = await directory.read(event=event)

            if args.all:
                lst = [".", ".."] + lst
            elif not args.almost_all:
                lst = [i for i in lst if not i.startswith(".")]

            if args.relative_path:
                return "\n".join(
                    key + "/" + value
                    # repr(x)
                    # if " " in (x := key + "/" + value)
                    # and not args.literal
                    # else x
                    for value in lst
                    if value not in (".", "..")
                )

            elif args.every_line:
                return "\n".join(lst)

            return cls.colprint(lst, args)

        except Exception:
            return ""

    @classmethod
    async def function(cls, event: Event, args: Namespace, stdin: Optional[Result]):
        total: list[tuple[str, DirectoryType]] = []
        for path in args.path:
            directory = await get_path(path, event=event, directory=True)

            total.append((path, directory))

        else:
            if not total:
                directory = event.state.directory
                total.append((".", directory))

        if len(total) == 1:
            return await cls.generate(args, event, *total[0])
        else:
            final = ""
            for key, directory in total:
                gen = await cls.generate(args, event, key, directory)
                final += f"{key}:\n{gen}\n\n"

            return final


class cat(Command):
    """
    Get file contents.
    """

    usage = "%(prog)s [options*] [path*]"

    highlightings = {"clirc": "bash", "command": "bash"}

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("path", nargs="*", help="any file")
        cls.argparser.add_argument(
            "-c", "--color", action="store_true", help="try to apply highlighting"
        )
        cls.argparser.add_argument(
            "-P",
            "--stdin-as-pathways",
            action="store_true",
            help="read stdin as pathways instead of content",
        )
        cls.argparser.add_argument(
            "-L", "--list", action="store_true", help="return contents in list"
        )

    @staticmethod
    def convert(content: str, reverse: bool, last: int | None) -> str:
        if last is not None:
            content_lines = content.split("\n")
            if reverse:
                lines = len(content_lines)
                content = "\n".join(content_lines[lines - last :])
            else:
                content = "\n".join(content_lines[:last])
        elif reverse:
            content = "\n".join(content.split("\n")[::-1])

        return content

    @classmethod
    async def function(
        cls,
        event: Event,
        args: Namespace,
        stdin: Optional[Result],
        *,
        reverse: bool = False,
        last: Optional[int] = None,
    ) -> str | list[str]:
        total: dict[str, str] = {}
        if args.stdin_as_pathways:
            ways = stdin
        else:
            ways: list[str] = args.path

        for path in ways:
            file = await get_path(path, event=event, directory=False)
            if args.color:
                ext = file.extension
                lang = cls.highlightings.get(ext, ext)
                event.apply_option("syntax", lang)

            total.update(
                {path: cls.convert(str(await file.read(event=event)), reverse, last)}
            )

        else:
            if not total:
                total.update({".": cls.convert(str(stdin), reverse, last)})

        if args.list:
            return list(total.values())
        elif len(total) == 1:
            return tuple(total.values())[0]
        else:
            final = ""
            for key, content in total.items():
                final += f"{key}:\n{content}\n\n"

            return final


class tac(cat):
    """
    Get reversed file contents.
    """

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str | list[str]:
        return await super().function(event, args, stdin, reverse=True)


class head(cat):
    """
    Get first lines.
    """

    usage = "%(prog)s [options*] [path*]"

    @classmethod
    def generate_argparser(cls):
        super().generate_argparser()
        cls.argparser.add_argument(
            "-n", "--lines", type=int, default=10, help="number of lines to show"
        )

    @classmethod
    async def function(
        cls,
        event: Event,
        args: Namespace,
        stdin: Optional[Result],
        *,
        reverse: bool = False,
    ) -> str | list[str]:
        return await super().function(
            event, args, stdin, reverse=reverse, last=args.lines
        )


class tail(head):
    """
    Get last lines.
    """

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str | list[str]:
        return await super().function(event, args, stdin, reverse=True)


class wc(Command):
    """
    Count occurrences.
    """

    usage = "%(prog)s [option*] [path*]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("path", nargs="*", help="any file")
        cls.argparser.add_argument(
            "-m",
            "--chars",
            action="store_const",
            dest="action",
            const="chars",
            help="return character counts",
        )
        cls.argparser.add_argument(
            "-l",
            "--lines",
            action="store_const",
            dest="action",
            const="lines",
            help="return newline counts",
        )
        cls.argparser.add_argument(
            "-w",
            "--words",
            action="store_const",
            dest="action",
            const="words",
            help="return newline counts",
        )

    @staticmethod
    def count(action: str, string: str) -> int:
        if not action:
            action = "chars"
        if action == "chars":
            return len(string)
        elif action == "lines":
            return len(string.split("\n"))
        elif action == "words":
            return len(string.split())
        else:
            return 0

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> int:
        final = 0

        for path in args.path:
            file = await get_path(path, event=event, directory=False)

            final += cls.count(args.action, await file.read(event=event))

        if stdin:
            final += cls.count(args.action, str(stdin))

        return final


class rm(Command):
    """
    Remove entries.
    """

    usage = "%(prog)s [options*] <path+>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("path", nargs="+", help="any file or directory")
        cls.argparser.add_argument(
            "-r", "--recursive", action="store_true", help="remove directory"
        )
        # cls.argparser.add_argument(
        #     "-v", "--verbose",
        #     action="store_true",
        #     help="print a message for each removed file"
        # )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        verbose = []
        for path in args.path:
            directory, name = await get_path(path, event=event, last_name=True)

            removed = await directory.remove(
                name, event=event, recursive=args.recursive
            )
            verbose.extend(removed)

        return "\n".join(verbose)


class pull(Command):
    """
    Receive files from filesystem.
    """

    usage = "%(prog)s <path+>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("path", nargs="+", help="any path to file")

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> list[File]:
        final: list[File] = []
        for path in args.path:
            file = await get_path(path, event=event, directory=False)

            content = await file.read(event=event)
            bytes_content = (
                bytes(content, "utf-8") if type(content) is str else bytes(content)
            )

            final.append(File(io.BytesIO(bytes_content), file.name))

        return final


class push(Command):
    """
    Upload files to filesystem.
    """

    usage = "%(prog)s [options*] [path*]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("path", nargs="*", help="any path to file")
        cls.argparser.add_argument(
            "-r",
            "--rename",
            action="store_true",
            help="rename file instead of replacing contents",
        )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        verbose: list[str] = []

        for num, file in enumerate(event.message.attachments):
            content = await file.read()
            try:
                content = content.decode("utf-8")
            except UnicodeDecodeError:
                pass

            if len(args.path) > num:
                dest = await get_path(args.path[num], event=event, create=True)
                if dest.kind in file_kinds:
                    await dest.write(content, event=event)
                    verbose.append(str(dest.path))
                    continue

            else:
                dest = event.state.directory

            if args.rename:
                name, *ext = file.filename.rsplit(".", 1)
                files = dest.files
                if isfunction(files):
                    files = []

                name = get_name(name, files)

                if ext:
                    name += "." + ext[0]
            else:
                name = file.filename

            try:
                new = await dest.create("file", name, content=content, event=event)

            except FileExistsError:
                new = await dest.select(name, event=event)
                await new.write(content, event=event)

            except Exception:
                raise

            verbose.append(str(new.path))

        return "\n".join(verbose)


class cp(Command):
    """
    Copy files.
    """

    usage = "%(prog)s <src+> <dest>"
    attr_name = "copy"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("src", nargs="+", help="source files")
        cls.argparser.add_argument("dest", help="destination path")

    @classmethod
    async def get_files(
        cls, event: Event, args: Namespace
    ) -> tuple[list[FileType], AllFilesType]:
        files = [await get_path(src, event=event, directory=False) for src in args.src]
        dest = await get_path(
            args.dest,
            event=event,
            directory=True if len(files) > 1 else None,
            create=True,
        )

        return files, dest

    @classmethod
    @required("src")
    @required("dest")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        files, dest = await cls.get_files(event, args)

        verbose: list[str] = []
        for file in files:
            try:
                func: RegularFile.copy = getattr(file, cls.attr_name)
                copy = await func(dest, event=event)
            except Exception as ex:
                verbose.append(str(ex))
            else:
                verbose.append(f"{file.path} -> {copy.path}")

        return "\n".join(verbose)


class mv(cp):
    """
    Move files.
    """

    attr_name = "move"


class mkdir(Command):
    """
    Create a new directory.
    """

    usage = "%(prog)s [options*] <directory>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("path", help="path to directory to create")
        cls.argparser.add_argument(
            "-p",
            "--parents",
            action="store_true",
            help="make parent directories as needed",
        )

    @classmethod
    @required("path")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        directory = event.state.directory
        routes = split_path(args.path)
        last_num = len(routes) - 1

        verbose: list[str] = []
        for num, route in enumerate(routes):
            try:
                directory = await get_path(
                    route, current=directory, event=event, directory=True
                )
            except NoFileFoundError:
                if args.parents or num == last_num:
                    new = await directory.create("directory", route, event=event)
                    directory = new
                    verbose.append(str(directory.path))
                else:
                    raise

        return "\n".join(verbose)


class chmod(Command):
    """
    Change mode of file.
    """

    usage = "%(prog)s <mode> <path>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "mode",
            type=lambda x: int(x.removeprefix("0o"), base=8),
            help="mode to set (0o000 - 0o777)",
        )
        cls.argparser.add_argument("path", nargs="+", help="path to file")

    @classmethod
    @required("mode")
    @required("path")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        verbose: list[str] = []
        for route in args.path:
            try:
                file = await get_path(route, event=event)
                await file.chmod(args.mode, event=event)
            except Exception as ex:
                verbose.append(str(ex))
            else:
                verbose.append(f"Mode changed: {file.path} [{file.mode}]")

        return "\n".join(verbose)
