from __future__ import annotations

from models.packages import Command
from models.utils import run_in_executor
from models.extra import required
from sympy.parsing.sympy_parser import (
    standard_transformations,
    implicit_multiplication_application,
    implicit_application,
    convert_xor,
)
from sympy import solve, Eq, simplify
from sympy.parsing.sympy_parser import parse_expr

from typing import Any, Awaitable, Generator, Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result


class math(Command):
    """
    Solve math problems.
    """

    usage = "%(prog)s <expression>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "expression", nargs="A...", help="any math problem to solve"
        )

    transformations = standard_transformations + (
        convert_xor,
        implicit_application,
        implicit_multiplication_application,
    )

    @classmethod
    def do_parse(cls, string: str) -> Generator[Any, None, None]:
        args = (
            line.split("=") if not any(i in line for i in (">=", "<=")) else [line]
            for line in string.splitlines()
        )

        for arg in args:
            expression = parse_expr(arg[0], transformations=cls.transformations)

            if len(arg) == 2:
                equalation = parse_expr(arg[1], transformations=cls.transformations)
                full = Eq(expression, equalation)
            else:
                full = expression

            yield full

    @classmethod
    @run_in_executor
    def calculate(cls, string: str) -> Awaitable[Any]:
        full = list(cls.do_parse(string))
        if len(full) == 1:
            full = full[0]
            result = (
                solve(full)
                if any(s in string for s in ("=", "<", ">"))
                else simplify(full)
            )
        else:
            result = solve(full, manual=True, force=True)

        return result

    @classmethod
    @required("stdin", "expression")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        expression = (stdin and str(stdin) or "") + " ".join(
            args.expression or ("+ 0",)
        )

        result = await cls.calculate(expression)
        result = str(result).replace("oo", "∞").replace("z∞", "±∞")

        return result
