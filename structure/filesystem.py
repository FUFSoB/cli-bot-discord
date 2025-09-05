from __future__ import annotations

import asyncio
from models.utils import convert_bytes
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Coroutine,
    Literal,
    Optional,
    Pattern,
    TYPE_CHECKING,
)
import discord
from models.errors import (
    FalseError,
    FileExistsError,
    FileSizeError,
    NoFileFoundError,
    NonEmptyDirectoryError,
    NotAnExecutableError,
)
from .data import get_root, get_by_inode, defaults, get_home
from .permissions import Mode
from parser import get_processor
from inspect import isfunction, iscoroutinefunction, ismethod, isawaitable
import regex
import hashlib
import aiohttp
import math
import random

if TYPE_CHECKING:
    from models.typings import (
        DirectoryType,
        FileType,
        AllFilesType,
        BasicFileType,
        WrapperType,
        StateType,
        GeneratedNetworkType,
    )
    from parser.processing import Processor
    from parser.wrapper import Result
    from models.event import Event
    from models.bot import Client

__all__ = (
    "Path",
    "RegularFile",
    "Directory",
    "Link",
    "Generator",
    "GeneratedDirectory",
    "GeneratedFile",
    "RootDirectory",
    "NetworkFile",
    "NetworkDirectory",
    "FilterDirectory",
)


parsed_files: dict[int | AllFilesType, list[str, Processor]] = {}


class Path:
    def __init__(
        self,
        names: Optional[list[str]] = None,
        references: Optional[list[int | AllFilesType]] = None,
    ):
        self.names = names or [""]
        self.references: list[int | AllFilesType] = references or [1]

    def __str__(self):
        return "/".join(self.names) or "/"

    def __truediv__(self, args: list[str, int | AllFilesType] | "Path") -> "Path":
        if type(args) is Path:
            return Path(self.names + args.names, self.references + args.references)

        return Path(self.names + args[:1], self.references + args[1:])

    def __getitem__(self, slc: int | slice) -> "Path":
        return Path(self.names[slc], self.references[slc])

    async def get_parent(self) -> AllFilesType:
        try:
            reference = self.references[-2]
            name = self.names[-2]
        except IndexError:
            reference = self.references[0]
            name = self.names[0]
        if type(reference) is int:
            return await get_by_inode(reference, name, self[:-1])
        else:
            return reference

    def absolute(self) -> str:
        return str(self)

    def relative(
        self, name: Optional[str] = None, *, inode: Optional[int | AllFilesType] = None
    ) -> str:
        if name:
            index = len(self.names) - 1 - self.names[::-1].index(name)
        elif inode:
            index = len(self.references) - 1 - self.references[::-1].index(inode)
        else:
            index = 0

        if not index:
            return str(self)

        return "/".join(self.names[index:])

    def short(self, event: Optional[Event] = None) -> str:
        no_home = str(self).removeprefix("/home/")
        if not event:
            pass
        elif type(event.state.object) is discord.User:
            no_home = no_home.removeprefix("user")
        elif type(event.state.object) is discord.Guild:
            no_home = no_home.removeprefix("guild")

        return "~" + no_home


class ConstructorFile:
    def __init__(
        self,
        name: str,
        mode: Mode,
        inode: Optional[int] = None,
        path: Optional[Path] = None,
        *,
        refs: Optional[list[int]] = None,
    ):
        self.name = name
        self.mode = mode
        self.inode = inode
        self.path = path
        self.refs = refs or []  # inodes referring to it

    def __str__(self):
        return self.name or "/"

    def add_reference(self, inode: int) -> None:
        if inode not in self.refs:
            self.refs.append(inode)

    def remove_reference(self, inode: int) -> None:
        if inode in self.refs:
            self.refs.remove(inode)

    def apply_inode(self, inode: int) -> None:
        self.inode = inode

    def apply_path(self, path: Path) -> None:
        self.path = path

    @property
    def root(self) -> "RootDirectory":
        return get_root()

    @property
    def kind(self) -> str:
        return kinds_reversed[type(self)]

    def to_dict(self) -> dict[str, Any]:
        kind = self.kind
        data = {
            "kind": kind,
            "name": self.name,
            "inode": self.inode,
            "mode": self.mode.to_dict(),
            "refs": self.refs,
        }
        if kind == "file":
            data |= {"content": self.content}
        elif kind in ("directory", "home"):
            data |= {"files": self.files}
        elif kind == "link":
            pass
        return data


class BaseFile(ConstructorFile):
    def check(
        self,
        action: str = "read",
        *,
        event: Optional[Event] = None,
        exception: bool = True,
    ) -> bool:
        """
        Check for user permissions.
        """
        return self.mode.check(self, action, event=event, exception=exception)

    async def select(
        self, name: str, *, event: Optional[Event] = None
    ) -> AllFilesType | None:
        """
        Select file or directory.
        """
        self.check(event=event)
        if "file" in self.kind:
            raise NotImplementedError
        elif not name or name == ".":
            return self
        elif name == "..":
            return await self.path.get_parent()
        elif name == "/":
            return self.root
        elif name == "~":
            return await get_home(event.state.kind, event)
        elif name.startswith("~"):
            return await get_home(name.removeprefix("~"), event)
        elif name.startswith("%"):
            return await FilterDirectory.initialize(self, name, event=event)

        return None

    async def read(self, *, event: Optional[Event] = None):
        """
        Access file contents.
        """
        raise NotImplementedError

    async def size(
        self, efficient: bool = False, *, event: Optional[Event] = None
    ) -> int | Literal["--"]:
        """
        Get size of file or directory.
        """
        if efficient and self.kind in (
            "generator",
            "network_file",
            "network_directory",
            "home_pointer",
        ):
            return "--"

        content = await self.read(event=event)
        if type(content) is str:
            content = content.encode("utf-8")
        elif type(content) is int:
            return math.ceil(len(f"{content:b}") / 8)

        try:
            return len(content)
        except TypeError:
            return 0

    async def execute(self, *args, event: Optional[Event] = None):
        """
        Execute file or change directory.
        """
        raise NotImplementedError

    def generate_checksum(self):
        """
        Generate checksum for files.
        """
        raise NotImplementedError

    async def copy(
        self,
        dest: AllFilesType,
        name: Optional[str] = None,
        *,
        event: Optional[Event] = None,
    ):
        """
        Copy file.
        """
        raise NotImplementedError

    async def move(
        self,
        dest: AllFilesType,
        name: Optional[str] = None,
        *,
        event: Optional[Event] = None,
    ):
        """
        Move file into directory.
        """
        raise NotImplementedError

    async def chmod(self, value: int, *, event: Optional[Event] = None) -> None:
        """
        Change mode of file.
        """
        self.check("group", event=event)
        self.mode.set_value(value)
        await self.save()

    async def chown(
        self,
        owner: Optional[int | str] = None,
        group: Optional[int | str] = None,
        *,
        event: Optional[Event] = None,
    ):
        """
        Change owner and group of file.
        """
        raise NotImplementedError

    async def create(
        self,
        kind: str,
        name: str,
        mode: Optional[Mode] = None,
        *args,
        event: Optional[Event] = None,
        **kwargs,
    ):
        """
        Create file.
        """
        raise NotImplementedError

    async def write(
        self, content: Any, replace: bool = True, *, event: Optional[Event] = None
    ):
        """
        Change contents of file.
        """
        raise NotImplementedError

    async def soft_link(
        self, name: str, directory: DirectoryType, *, event: Optional[Event] = None
    ):
        """
        Create soft-link to file into directory.
        """
        raise NotImplementedError

    async def hard_link(
        self, name: str, directory: DirectoryType, *, event: Optional[Event] = None
    ):
        """
        Create soft-link to file into directory.
        """
        raise NotImplementedError

    async def remove(
        self,
        name: Optional[str] = None,
        *,
        event: Optional[Event] = None,
        recursive: bool = False,
        file: Optional[AllFilesType] = None,
    ) -> list[str]:
        """
        Remove reference to file completely.
        """
        if type(self) is RegularFile:
            raise NotImplementedError

        self.check("write", event=event)
        if file:
            selected = file
            name = file.name
        elif name:
            selected = await self.select(name, event=event)
        else:
            raise TypeError("missing both name and file arguments")

        if selected and selected.kind in dir_kinds and selected.files and not recursive:
            raise NonEmptyDirectoryError(selected)

        try:
            self.files.pop(selected.name)
        except KeyError:
            raise NoFileFoundError(name)

        if selected:
            selected.remove_reference(self.inode)
            files = [
                str(removed.path)
                async for removed in selected.__delete(recursive=recursive)
            ]
        else:
            files = [name]

        await self.save()
        return files

    async def __delete(
        self, *, recursive: bool = False
    ) -> AsyncGenerator[BasicFileType, None]:
        """
        Remove file completely.
        """
        from models.database import db

        if self.refs:
            return

        if self.kind in dir_kinds and recursive:
            for name, inode in self.files.items():
                file = await get_by_inode(inode, name, self.path)

                async for removed in file.__delete(recursive=recursive):
                    yield removed

        self.root.free_inodes_list.append(self.inode)
        await db.remove_file(self)
        yield self

    async def save(self, *, event: Optional[Event] = None) -> None:
        """
        Save file in database.
        """
        from models.database import db

        if "generat" in self.kind:
            return

        if self.inode >= 10000:
            await db.save_file(self)

            # parent = await self.path.get_parent()
            # await parent.save(event=event, skip_next=True)

            await self.root.save()

        else:
            if self not in defaults:
                defaults.append(self)


class RegularFile(BaseFile):
    max_size = 1024 * 1024 * 8
    max_size_str = convert_bytes(1024 * 1024 * 8)

    def __init__(self, *args, content: Any = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.content = self.check_content(content)
        self._parsed = asyncio.Event()

    def __repr__(self):
        return f"<RegularFile {{{self.inode}}} {str(self)!r} {self.mode.info}>"

    def check_content(self, content: Any, replace: bool = True) -> Any:
        """
        Check if content length is higher than limit.
        """
        if type(content) not in (str, bytes):
            return content

        length = len(content) + (
            len(self.content) if not replace and self.content else 0
        )

        if length > self.max_size:
            raise FileSizeError(convert_bytes(length), self.max_size_str)

        return content

    @property
    def extension(self) -> str:
        if "." not in self.name and "execute" in dir(self.content):
            if not self.content.apply_to_package:
                return "bash"
            return "py"
        elif self.name.endswith(".event"):
            return "bash"
        else:
            return self.name.rsplit(".", 1)[-1]

    async def read(self, *, event: Optional[Event] = None) -> Any:
        """
        Access file contents.
        """
        self.check(event=event)
        content = self.content

        if ismethod(content):
            content = content()
            if isawaitable(content):
                content = await content

        elif iscoroutinefunction(content):
            content = await content()

        elif isfunction(content):
            content = content()

        elif "execute" in dir(content):
            content = content.source

        if type(content) is bool:
            return str(content).lower()
        else:
            return content

    async def write(
        self, content: Any, replace: bool = True, *, event: Optional[Event] = None
    ) -> Any:
        """
        Change contents of file.
        """
        self.check("write", event=event)
        self.check_content(content, replace)

        if replace or self.content is None:
            self.content = content
        else:
            if type(content) is bytes:
                nl = b"\n"
            else:
                nl = "\n"

            self.content += nl + content

        await self.save()
        return self.content

    async def copy(
        self,
        dest: AllFilesType,
        name: Optional[str] = None,
        *,
        event: Optional[Event] = None,
    ) -> AllFilesType:
        """
        Copy file into directory.
        """
        self.check(event=event)
        if dest.kind in file_kinds:
            await dest.write(self.content, event=event)
            return dest

        name = name or self.name

        try:
            file = await dest.create(self.kind, name, content=self.content, event=event)
            await file.save()
            await dest.save()
            return file
        except FileExistsError:
            dest = await dest.select(name, event=event)
            await dest.write(self.content, event=event)
            return dest

    async def move(
        self,
        dest: AllFilesType,
        name: Optional[str] = None,
        *,
        event: Optional[Event] = None,
    ) -> AllFilesType:
        """
        Move file into directory.
        """
        copy = await self.copy(dest, name, event=event)

        parent = await self.path.get_parent()
        if parent.inode and parent.inode == event.state.directory.inode:
            parent = event.state.directory

        await parent.remove(file=self, event=event)
        return copy

    @property
    def checksum(self) -> str | None:
        return parsed_files.get(self.inode, (None,))[0]

    @property
    def processor(self) -> Processor | None:
        return parsed_files.get(self.inode, (None,))[-1]

    def generate_checksum(self) -> str:
        checksum = hashlib.blake2s(
            self.content.encode("utf-8"), digest_size=4
        ).hexdigest()
        parsed_files[self.inode] = [checksum, self.processor]
        return checksum

    async def parse_as_command(
        self, *, event: Optional[Event] = None
    ) -> Result | list[WrapperType]:
        if self.checksum != self.generate_checksum():
            parsed_files[self.inode][1] = await get_processor(
                self.content, str(self.path)
            )

        if self.processor:
            self._parsed.set()

        await self._parsed.wait()
        if event:
            return await self.processor.finalize(event, True)
        return await self.processor.process_self()

    async def execute(self, event: Optional[Event] = None, *args):  # ?
        """
        Execute file.
        """
        state: Optional[StateType] = getattr(event, "state", None)
        self.check("execute", event=event)

        if self.kind in file_kinds:
            content = self.content
            type_ = type(content)

            if type_ is str:
                if not state.skip_top_priority:
                    state.skip_top_priority = True
                    skipped = True
                else:
                    skipped = False

                result = await self.parse_as_command(event=event)

                if skipped:
                    state.skip_top_priority = False
            elif "execute" in dir(content):
                result = await content.execute(event, *args)
            elif type_ is bool:
                if not content:
                    raise FalseError()
                result = None
            else:
                raise NotAnExecutableError(self)

            return result

        else:
            state.set_directory(self)
            return None


class Directory(BaseFile):
    def __init__(
        self, *args, files: Optional[dict[str, int | AllFilesType]] = None, **kwargs
    ):
        super().__init__(*args, **kwargs)

        self.files: Optional[dict[str, int | AllFilesType]] = files or {}

    def __iter__(self):
        yield from self.files.values()

    def __truediv__(self, other: str):
        return self.select(other)

    def __repr__(self):
        return (
            f"<Directory {{{self.inode}}} {str(self)!r} {self.mode.info} "
            f"files={list(self.files.keys())}>"
        )

    async def select(
        self, name: str, *, event: Optional[Event] = None
    ) -> AllFilesType | None:
        """
        Select file or directory.
        """
        if selected := await super().select(name, event=event):
            return selected

        inode = self.files.get(name)
        if not inode:
            raise NoFileFoundError(name)

        if type(inode) is not int:
            return inode

        return await get_by_inode(inode, name, self.path)

    async def create(
        self,
        kind: str,
        name: str,
        mode: Optional[Mode] = None,
        *args,
        event: Optional[Event] = None,
        **kwargs,
    ) -> AllFilesType:
        """
        Create file or directory in current directory.
        """
        self.check("write", event=event)
        if name in self.files:
            raise FileExistsError(name)

        file: AllFilesType = kinds[kind](name, mode or self.mode, *args, **kwargs)

        inode = self.root.create_inode(self.inode >= 10000)
        file.apply_inode(inode)
        file.apply_path(self.path / [name, inode])

        self.files[file.name] = file.inode

        file.add_reference(self.inode)

        await self.save()
        await file.save()

        return file

    async def read(self, *, event: Optional[Event] = None) -> list[str]:
        """
        Access directory contents.
        """
        self.check(event=event)
        return list(self.files.keys())

    async def read_files(
        self, *, event: Optional[Event] = None
    ) -> AsyncGenerator[AllFilesType]:
        """
        Iterate through files.
        """
        self.check(event=event)
        for name, inode in self.files.items():
            if type(inode) is int:
                yield await get_by_inode(inode, name, self.path)
            else:
                yield inode


class Link(BaseFile):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class Generator(BaseFile):
    def __init__(
        self,
        *args,
        function: Callable[
            [AllFilesType, Event, Optional[str]], AsyncGenerator[AllFilesType, None]
        ],
        extra: Optional[tuple] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.function = function
        self.extra = extra or ()

    # def __iter__(self):
    #     yield from self.files(self, self.event)

    def __truediv__(self, other: str):
        return self.select(other)

    def __repr__(self):
        return f"<Generator {{{self.inode}}} {str(self)!r} {self.mode.info}>"

    def files(
        self, event: Event, name: Optional[str] = None
    ) -> AsyncGenerator[AllFilesType, None]:
        return self.function(self, event, name, *self.extra)

    async def select(self, name: str, *, event: Optional[Event] = None) -> AllFilesType:
        """
        Select file or directory.
        """
        if selected := await super().select(name, event=event):
            return selected

        if name == ".cache":
            return await self.cache(event=event)

        async for file in self.files(event, name):
            if name == file.name:
                return file

        raise NoFileFoundError(name)

    async def create(
        self,
        kind: str,
        name: str,
        mode: Optional[Mode] = None,
        *args,
        event: Optional[Event] = None,
        **kwargs,
    ) -> GeneratedNetworkType:
        """
        Create file or directory in current directory.
        """
        self.check("write", event=event)
        file: GeneratedNetworkType = kinds[
            (
                "generated_" + kind
                if not any(w in kind for w in ("generat", "network"))
                else kind
            )
        ](name, mode or self.mode, 0, *args, **kwargs)
        file.apply_path(self.path / [name, file])

        return file

    async def read(self, *, event: Optional[Event] = None) -> list[str]:
        """
        Access directory contents.
        """
        self.check(event=event)
        return [i.name async for i in self.files(event)] + [".cache"]

    async def read_files(
        self, *, event: Optional[Event] = None
    ) -> AsyncGenerator[AllFilesType, None]:
        """
        Iterate through files.
        """
        self.check(event=event)
        async for file in self.files(event):
            yield file

    async def cache(self, *, event: Optional[Event] = None) -> "GeneratedDirectory":
        """
        Cache every file generator has into new directory with same properties.
        """
        self.check(event=event)
        files = {file.name: file async for file in self.files(event)}

        file: GeneratedDirectory = kinds["generated_directory"](
            self.name, self.mode, self.inode, files=files
        )
        file.apply_path(self.path[:-1] / [self.name, file])

        return file


class GeneratedFile(RegularFile):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __repr__(self):
        return f"<GeneratedFile {str(self)!r} {self.mode.info}>"


class GeneratedDirectory(Directory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __repr__(self):
        return (
            f"<GeneratedDirectory {str(self)!r} {self.mode.info} "
            f"files={list(self.files.keys())}>"
        )


class RootDirectory(Directory):
    def __init__(self, client: Client, inodes: dict[str, Any]):
        super().__init__("", Mode(0o775, "root", "root"), 1, Path())
        self.client = client
        self.free_inodes_list: list[int] = inodes.get("free", [])
        self.next_public_inode: int = inodes.get("next", 10000)
        self.next_private_inode = 2

    @property
    def free_public_inodes(self) -> list[int]:
        return [i for i in self.free_inodes_list if i >= 10000]

    @property
    def free_private_inodes(self) -> list[int]:
        return [i for i in self.free_inodes_list if i < 10000]

    def create_inode(self, public: bool) -> int:
        if public is True:
            if self.free_public_inodes:
                inode = self.free_public_inodes[0]
                self.free_inodes_list.remove(inode)
            else:
                inode = self.next_public_inode
                self.next_public_inode += 1
        else:
            if self.free_private_inodes:
                inode = self.free_private_inodes[0]
                self.free_inodes_list.remove(inode)
            else:
                inode = self.next_private_inode
                self.next_private_inode += 1
        return inode

    async def save(self, *, event: Optional[Event] = None) -> None:
        """
        Save inode counter to database.
        """
        from models.database import db

        await db.save_inodes(self)


class HomePointer(BaseFile):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __iter__(self):
        yield from ("user", "guild")

    def __truediv__(self, other: str):
        return self.select(other)

    def __repr__(self):
        return f"<HomePointer {{{self.inode}}} {str(self)!r} {self.mode.info}>"

    async def select(
        self, name: str, *, event: Optional[Event] = None
    ) -> "HomeDirectory":
        """
        Select home directory.
        """
        if selected := await super().select(name, event=event):
            return selected

        if name == "user":
            inode = getattr(event.user, "id", None)
        elif name == "guild":
            inode = getattr(event.guild, "id", None)
        else:
            try:
                inode = int(name)
                name = str(inode)
            except ValueError:
                inode = None

        if not inode or len(str(inode)) < 17:
            raise NoFileFoundError(name)

        file = await get_by_inode(inode, name, self.path)
        if not file:
            file = await self.create(inode, name, event=True)

        return file

    async def read(self, *, event: Optional[Event] = None) -> list[str]:
        """
        Access directory contents.
        """
        self.check(event=event)
        return [item for item in self if getattr(event, item)]

    async def read_files(
        self, *, event: Optional[Event] = None
    ) -> AsyncGenerator["HomeDirectory", None]:
        """
        Iterate through files.
        """
        self.check(event=event)
        if event.user:
            yield await get_by_inode(event.user.id, "user", self.path)
        if event.guild:
            yield await get_by_inode(event.guild.id, "guild", self.path)

    async def create(
        self, inode, name, mode=None, *args, event: Optional[Event] = None, **kwargs
    ) -> "HomeDirectory":
        """
        Create file or directory in current directory.
        """
        self.check("write", event=event)
        file: HomeDirectory = kinds["home"](
            name,
            Mode(0o770, inode, inode),
            inode,
            self.path / [name, inode],
            *args,
            **kwargs,
        )

        file.add_reference(self.inode)

        await file.save()

        return file


class HomeDirectory(Directory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __repr__(self):
        return f"<HomeDirectory {self.inode} " f"files={list(self.files.keys())}>"


class NetworkFile(RegularFile):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __repr__(self):
        return f"<NetworkFile {{{self.inode}}} {str(self)!r} {self.mode.info}>"

    async def read(self, *, event: Optional[Event] = None) -> bytes:
        """
        Access file contents.
        """
        self.check(event=event)
        async with aiohttp.ClientSession() as session:
            data = await session.get(self.content)
            return await data.read()


class NetworkDirectory(Directory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __repr__(self):
        return (
            f"<NetworkDirectory {{{self.inode}}} {str(self)!r} "
            f"{self.mode.info} files={list(self.files.keys())}>"
        )


class FilterDirectory(ConstructorFile):
    def __init__(
        self,
        *args,
        files: Optional[list[str]] = None,
        prev: AllFilesType = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.files: list[str] = files or []
        self.prev = prev

    def __repr__(self):
        return (
            f"<FilterDirectory {str(self)!r} "
            f"{self.mode.info} files={list(self.files)}>"
        )

    def __getattr__(self, attr):
        return getattr(self.prev, attr)

    def __iter__(self):
        yield from self.prev

    async def select(self, name: str, *, event: Optional[Event] = None) -> AllFilesType:
        """
        Select file or directory.
        """
        file = await self.prev.select(name, event=event)

        if self in file.path.references and type(file) is not FilterDirectory:
            if name not in self.files:
                raise NoFileFoundError(name)

        return file

    async def read(self, *, event: Optional[Event] = None) -> list[str]:
        self.check(event=event)
        return self.files

    async def read_files(
        self, *, event: Optional[Event] = None
    ) -> AsyncGenerator[AllFilesType, None]:
        async for file in self.prev.read_files(event=event):
            if file.name in self.files:
                yield file

    split: Pattern.split = regex.compile(r"(?<!\\)%").split

    @staticmethod
    async def by_name(pattern: str, files: list[str], *_):
        compiled: Pattern = regex.compile(pattern)
        for name in files:
            if compiled.match(name):
                yield name

    @staticmethod
    async def by_range(rng: str, files: list[str], *_):
        rng = rng.split(":")
        if len(rng) == 1:
            yield files[int(rng[0])]
            return
        elif len(rng) == 2:
            slc = slice(
                rng[0] and int(rng[0]) or None, rng[1] and int(rng[1]) or None, None
            )
        else:
            slc = slice(*(int(r) if r != "" else None for r in rng))

        for name in files[slc]:
            yield name

    @staticmethod
    async def by_type(
        kind: str, files: list[str], select: Callable[..., Coroutine], event: Event
    ):
        for name in files:
            file = await select(name, event=event)
            if kind in file.kind:
                yield name

    @staticmethod
    async def by_inside(
        inside: str, files: list[str], select: Callable[..., Coroutine], event: Event
    ):
        if "!=" in inside:
            filename, value = inside.split("!=", 1)
            truth = False
        elif "==" in inside:
            filename, value = inside.split("==", 1)
            truth = True
        else:
            filename = inside
            value = truth = None

        for name in files:
            file = await select(name, event=event)

            try:
                inside_file = await file.select(filename, event=event)
            except (NoFileFoundError, NotImplementedError):
                continue
            except Exception:
                raise

            if value is not None:
                try:
                    assert (value == str(await inside_file.read(event=event))) is truth
                except Exception:
                    continue

            yield name

    @staticmethod
    async def by_relative(filename: str, files: list[str], *_):
        if filename.startswith("^"):
            filename = filename.removeprefix("^")

            def func(name: str):
                return filename + "/" + name

        else:

            def func(name: str):
                return name + "/" + filename

        for name in files:
            yield func(name)

    @classmethod
    async def initialize(
        cls, prev: AllFilesType, string: str, *, event: Optional[Event] = None
    ) -> AllFilesType:
        if prev.kind == "generator":
            prev = await prev.cache(event=event)

        files = await prev.read(event=event)

        patterns = cls.split(string.removeprefix("%"))
        return_value = None

        for pattern in patterns:
            if pattern == "return" and not return_value:
                return_value = "first"
                continue
            elif pattern == "random" and not return_value:
                return_value = "random"
                continue

            name, value = pattern.split("=", 1)
            generator = getattr(cls, "by_" + name)
            files = [file async for file in generator(value, files, prev.select, event)]

        if return_value:
            if not files:
                return None
            if return_value == "first":
                file = files[0]
            elif return_value == "random":
                file = random.choice(files)
            else:
                file = None

            return await prev.select(file, event=event)

        self = cls(string, 0, prev.mode, files=files, prev=prev)
        self.apply_path(prev.path / [string, self])

        return self


dir_kinds: dict[str, DirectoryType] = {
    "directory": Directory,
    "link": Link,
    "generator": Generator,
    "generated_directory": GeneratedDirectory,
    "home_pointer": HomePointer,
    "home": HomeDirectory,
    "network_directory": NetworkDirectory,
    "rootfs": RootDirectory,
    "filter": FilterDirectory,
}

file_kinds: dict[str, FileType] = {
    "file": RegularFile,
    "generated_file": GeneratedFile,
    "network_file": NetworkFile,
}

kinds: dict[str, AllFilesType] = {**dir_kinds, **file_kinds}

kinds_reversed = {v: k for k, v in kinds.items()}
