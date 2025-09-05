from __future__ import annotations

from typing import Any, AsyncGenerator, TYPE_CHECKING
import copy
from structure.filesystem import (
    Path,
    RegularFile,
    Directory,
    Link,
    HomeDirectory,
    RootDirectory,
)
from structure.permissions import Mode
from .extra import Schedule

if TYPE_CHECKING:
    from models.config import Config
    from models.typings import BasicFileType

__all__ = ("db",)


class Encoder:
    @staticmethod
    def encode(file: BasicFileType) -> dict[str, Any]:
        kind = file.kind
        data = {
            "kind": kind,
            "inode": file.inode,
            "mode": Encoder.encode_mode(file.mode),
            "refs": file.refs,
        }
        if kind == "file":
            data |= {"content": file.content}
        elif kind in ("directory", "home"):
            data |= {"files": file.files}
        elif kind == "link":
            pass
        return data

    @staticmethod
    def encode_mode(mode: Mode) -> dict[str, int | str]:
        return {
            "kind": "mode",
            "owner": mode.owner,
            "group": mode.group,
            "value": mode.value,
        }

    @staticmethod
    def decode(document: dict[str, Any]) -> BasicFileType | Mode:
        try:
            kind: str = document.pop("kind")
        except Exception:
            return document
        else:
            file = {
                "file": RegularFile,
                "directory": Directory,
                "link": Link,
                "home": HomeDirectory,
                "mode": Mode,
            }[kind](**document)

            return file


class db:
    # In-memory storage collections
    _filesystem: dict[int, dict[str, Any]] = {}
    _webhooks: dict[int, str] = {}
    _schedules: list[dict[str, Any]] = []
    _auth_keys: dict[tuple[int, str], dict[str, Any]] = {}
    _initialized: bool = False

    @classmethod
    def setup(cls, config: Config) -> None:
        """Initialize the in-memory database (no external connections needed)"""
        cls._initialized = True
        # Clear any existing data
        cls._filesystem.clear()
        cls._webhooks.clear()
        cls._schedules.clear()
        cls._auth_keys.clear()

    @classmethod
    async def get_file(cls, inode: int, name: str, path: Path) -> BasicFileType:
        data = cls._filesystem.get(inode)

        if not data:
            return None

        # Deep copy to avoid modifying stored data
        data = copy.deepcopy(data)
        data["mode"] = Encoder.decode(data["mode"])
        data["name"] = name
        file = Encoder.decode(data)
        file.apply_path(path)
        return file

    @classmethod
    async def save_file(cls, file: BasicFileType) -> None:
        cls._filesystem[file.inode] = Encoder.encode(file)

    @classmethod
    async def remove_file(cls, file: BasicFileType) -> None:
        cls._filesystem.pop(file.inode, None)

    @classmethod
    async def get_inodes(cls) -> dict[str, Any]:
        return cls._filesystem.get(0, {})

    @classmethod
    async def save_inodes(cls, root: RootDirectory) -> None:
        data = {
            "inode": 0,
            "free": root.free_public_inodes,
            "next": root.next_public_inode,
        }
        cls._filesystem[0] = data

    @classmethod
    async def get_webhook(cls, id: int) -> str | None:
        return cls._webhooks.get(id)

    @classmethod
    async def append_webhook(cls, id: int, url: str) -> None:
        cls._webhooks[id] = url

    @classmethod
    async def save_schedule(cls, schedule: Schedule) -> None:
        cls._schedules.append(copy.deepcopy(schedule.data))

    @classmethod
    async def remove_schedule(cls, schedule: Schedule) -> None:
        # Find and remove matching schedule
        schedule_data = schedule.data
        cls._schedules = [s for s in cls._schedules if s != schedule_data]

    @classmethod
    async def get_schedules(cls) -> AsyncGenerator[Schedule, None]:
        for data in cls._schedules:
            yield Schedule(**copy.deepcopy(data))

    @classmethod
    async def set_auth_keys(cls, id: int, service: str, **values) -> None:
        key = (id, service)
        cls._auth_keys[key] = copy.deepcopy(values)

    @classmethod
    async def get_auth_keys(cls, id: int, service: str) -> dict[str] | None:
        key = (id, service)
        data = cls._auth_keys.get(key)
        return copy.deepcopy(data) if data else None

    @classmethod
    async def remove_auth_keys(cls, id: int, service: str) -> None:
        key = (id, service)
        cls._auth_keys.pop(key, None)
