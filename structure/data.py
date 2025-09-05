from __future__ import annotations

from typing import AsyncGenerator, Optional, Pattern, TYPE_CHECKING
from structure.permissions import Mode
from discord.utils import get
from .generator import (
    generate_binaries,
    generate_clients,
    generate_object_by_id,
    generate_object_by_name,
    generate_object_by_type,
    read_local_files,
)
from models.errors import NotADirectoryError, NotAFileError, NoFileFoundError
import regex

if TYPE_CHECKING:
    from models.bot import Client
    from models.event import Event
    from models.typings import AllFilesType, DirectoryType
    from .filesystem import Path, RootDirectory

__all__ = (
    "get_by_inode",
    "fill_defaults",
    "defaults",
    "get_root",
    "get_home",
    "get_path",
)

defaults: list[AllFilesType] = []  # 0..10000 inodes reserved


async def spawn_filesystem(
    client: Client, event: Event
) -> AsyncGenerator[AllFilesType, None]:
    from .filesystem import RootDirectory
    from models.database import db

    root = RootDirectory(client, await db.get_inodes())
    yield root

    binaries = await root.create(
        "generator", "bin", function=generate_binaries, event=True
    )
    yield binaries

    clients = await root.create(
        "generator",
        "clients",
        mode=Mode(0o770, "root", "root"),
        function=generate_clients,
        event=True,
    )
    yield clients

    home = await root.create("home_pointer", "home", event=True)
    yield home

    getter = await root.create(
        "generator", "get", function=generate_object_by_id, event=True
    )
    yield getter

    finder = await root.create(
        "generator", "find", function=generate_object_by_name, event=True
    )
    yield finder

    current = await root.create("directory", "current", event=True)
    yield current
    async for type_dir in generate_object_by_type(current):
        yield type_dir

    scripts = await root.create("directory", "scripts", event=True)
    yield scripts
    async for localfile in read_local_files(scripts, event):
        yield localfile


async def fill_defaults(client: Client, event: Event) -> None:
    async for a in spawn_filesystem(client, event):
        defaults.append(a)


async def get_by_inode(
    inode: int, name: str = None, path: Path = None
) -> Optional[AllFilesType]:
    in_defaults = get(defaults, inode=inode)
    if in_defaults:
        return in_defaults
    else:
        from models.database import db

        if path:
            new_path = path / [name, inode]
        else:
            new_path = path
        file = await db.get_file(inode, name, new_path)
        return file


def get_root() -> RootDirectory:
    return get(defaults, inode=1)


async def get_home(name: str, event: Optional[Event] = None):
    home_pointer = await get_root().select("home", event=event)
    return await home_pointer.select(name, event=event)


split_path: Pattern.split = regex.compile(r"(?<!\\)/").split


async def get_path(
    path: str,
    *,
    current: Optional[DirectoryType] = None,
    event: Optional[Event] = None,
    directory: Optional[bool] = None,
    create: bool = False,
    last_name: bool = False,
) -> AllFilesType | tuple[AllFilesType, str | None]:
    from .filesystem import dir_kinds

    first = new = current = current or event.state.directory

    parts: list[str] = split_path(path)
    part = None

    if parts and parts[0] == "":
        parts[0] = "/"

    last_index = len(parts) - 1

    for num, part in enumerate(parts):
        if num == last_index and last_name:
            continue

        if part in ("", "."):
            continue

        try:
            new = await current.select(part, event=event)
            if not new:
                raise NoFileFoundError(part)

        except NotImplementedError:
            raise NotADirectoryError(current)

        except NoFileFoundError:
            if create:
                new = await current.create(
                    "file" if num == last_index and not directory else "directory",
                    part,
                    event=event,
                )
            else:
                raise

        except Exception:
            raise

        if new.kind in dir_kinds:
            new.check("execute", event=event)

        if new.inode and first.inode == new.inode:
            current = first
        else:
            current = new
    else:
        if current.kind in dir_kinds:
            if directory is False:
                raise NotAFileError(new)
        elif directory is True:
            raise NotADirectoryError(new)

    if last_name:
        return current, part
    return current
