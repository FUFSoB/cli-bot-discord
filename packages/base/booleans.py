from __future__ import annotations

from models.packages import Command
from models.errors import FalseError, NullError
from models.utils import random_bool

from typing import NoReturn, Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result


class true(Command):
    """
    Do nothing, successfully.
    """

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> None:
        return


class false(Command):
    """
    Do nothing, unsuccessfully.
    """

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> NoReturn:
        raise FalseError()


class null(Command):
    """
    Do nothing, null.
    """

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> None:
        if not stdin:
            raise NullError()


class rand(Command):
    """
    Return true or false randomly.
    """

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> None:
        if not random_bool():
            raise FalseError()
