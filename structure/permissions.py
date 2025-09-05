from __future__ import annotations

from typing import Any, Literal, Optional, TYPE_CHECKING
from models.errors import PermissionDeniedError

if TYPE_CHECKING:
    from .filesystem import BaseFile
    from models.event import Event

__all__ = "Mode"


class Mode:
    indexes = {"read": 0, "write": 1, "execute": 2}

    def __init__(self, value: int, owner: int | str, group: int | str):
        self.value = value
        self.owner = owner
        self.group = group

    def __int__(self):
        return self.value

    def __oct__(self):
        return oct(self.value)

    def __iter__(self):
        numbers = (int(x) for x in format(self.value, "o").rjust(3, "0"))
        for num in numbers:
            if num - 4 >= 0:
                num -= 4
                yield "r"
            else:
                yield "-"

            if num - 2 >= 0:
                num -= 2
                yield "w"
            else:
                yield "-"

            if num == 1:
                yield "x"
            else:
                yield "-"

    def __str__(self):
        return "".join(self)

    def __repr__(self):
        return f"<Mode {self.info}>"

    @property
    def info(self) -> str:
        return f"{self.owner}:{self.group} {str(self)}"

    @property
    def grouped(self) -> list[list[Literal["r", "w", "x", "-"]]]:
        total = list(self)
        return [total[i : i + 3] for i in range(0, len(total), 3)]

    @property
    def bit_grouped(self) -> list[list[bool]]:
        total = [x != "-" for x in self]
        return [total[i : i + 3] for i in range(0, len(total), 3)]

    def set_value(self, value: int) -> None:
        self.value = value

    def check(
        self,
        file: BaseFile,
        action: str,
        *,
        event: Optional[Event] = None,
        exception: bool = True,
    ) -> bool:
        if action not in ("read", "write", "execute", "owner", "group"):
            raise ValueError("action must be read, write, execute, owner or group.")

        if event is True:
            return True
        elif not event:
            group = self.bit_grouped[2]
        if action == "owner" and event.state.object.id == self.owner:
            return True
        elif action == "group" and self.group in event.groups():
            return True
        elif event.state.object.id == self.owner:
            group = self.bit_grouped[0]
        elif self.group in event.groups():
            group = self.bit_grouped[1]
        else:
            group = self.bit_grouped[2]

        index = self.indexes[action]
        if not group[index]:
            if exception:
                raise PermissionDeniedError(file, action)
            else:
                return False

        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "mode",
            "owner": self.owner,
            "group": self.group,
            "value": self.value,
        }
