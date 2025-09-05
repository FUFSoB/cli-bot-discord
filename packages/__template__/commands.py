from models.packages import Command

from typing import Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result


class template(Command):
    """
    Description
    """

    package = "template"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("example_positional", help="example positional")
        cls.argparser.add_argument("-e", "--example-optional", help="example optional")

    @classmethod
    async def function(cls, event: Event, args: Namespace, stdin: Optional[Result]):
        return await super().function(event, args, stdin)
