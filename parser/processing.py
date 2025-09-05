from __future__ import annotations

from typing import Any, Callable, Coroutine, Optional, TYPE_CHECKING
from .wrapper import (
    Command,
    Word,
    List,
    Operator,
    Pipeline,
    Pipe,
    Redirect,
    Assignment,
    Parameter,
    Compound,
    Reservedword,
    If,
    For,
    Loop,
    Function,
    Tilde,
    Substitution,
    Expression,
    Result,
)
from models.errors import ReturnError, BaseError, InternalError

if TYPE_CHECKING:
    from bashlex.ast import node
    from models.event import Event
    from models.typings import WrapperType

__all__ = ("Processor",)


class Processor:
    def __init__(
        self, string: str, data: Optional[list] = None, final: Optional[list] = None
    ):
        self.string = string
        self.data = data
        self.final = final

    # def __getattr__(self, attr):
    #     return self.process_dummy

    def __getitem__(
        self, item: str
    ) -> Callable[[node, int], Coroutine[Any, Any, WrapperType]]:
        return getattr(self, "process_" + item)

    async def finalize(
        self,
        event: Optional[Event] = None,
        result: Optional[Result] = None,
        extra: bool = False,
    ) -> tuple[Result, bool, bool] | Result:
        final = await self.process_self()
        result = (
            (result if type(result) is Result else Result())
            if result is not None
            else event.result
        )

        returned = raised = False
        for wrapper in final:
            try:
                result << await wrapper.finalize(event)
            except ReturnError as ex:
                result << ex.value
                returned = True
                break
            except BaseError as ex:
                result << ex
                raised = True
            except Exception as ex:
                result << InternalError(ex)
                raised = True

        if extra:
            return result, returned, raised
        return result

    async def process_self(self) -> list[WrapperType]:
        if not self.final:
            self.final = await self.process_everything(self.data)

        return self.final

    async def process_everything(
        self, nodes: list[node], level: int = 0
    ) -> list[WrapperType]:
        return [await self[node.kind](node, level) for node in nodes]

    async def process_dummy(*args, **kwargs):
        return None

    async def process_command(self, node: node, level: int):
        data = await self.process_everything(node.parts, level + 1)
        if len(data) > 2 and data[0].word == "[" and data[-1].word == "]":
            return Expression(self, node, level)
        return Command(self, node, level, data)

    async def process_commandsubstitution(self, node: node, level: int):
        command = node.command
        return Substitution(self, node, level, await self[command.kind](command, level))

    async def process_word(self, node: node, level: int):
        data = await self.process_everything(node.parts, level + 1)
        return Word(self, node, level, data)

    process_quotedword = process_word

    async def process_list(self, node: node, level: int):
        data = await self.process_everything(node.parts, level + 1)
        return List(self, node, level, data)

    async def process_operator(self, node: node, level: int):
        return Operator(self, node, level)

    async def process_pipeline(self, node: node, level: int):
        data = await self.process_everything(node.parts, level + 1)
        return Pipeline(self, node, level, data)

    async def process_pipe(self, node: node, level: int):
        return Pipe(self, node, level)

    async def process_redirect(self, node: node, level: int):
        output = await self.process_word(node.output, level + 1)
        return Redirect(self, node, level, output)

    async def process_assignment(self, node: node, level: int):
        data = await self.process_everything(node.parts, level + 1)
        return Assignment(self, node, level, data)

    async def process_parameter(self, node: node, level: int):
        return Parameter(self, node, level)

    async def process_compound(self, node: node, level: int):
        data = await self.process_everything(node.list, level + 1)
        return Compound(self, node, level, data)

    async def process_reservedword(self, node: node, level: int):
        return Reservedword(self, node, level)

    async def process_if(self, node: node, level: int):
        data = await self.process_everything(node.parts, level + 1)
        return If(self, node, level, data)

    async def process_for(self, node: node, level: int):
        data = await self.process_everything(node.parts, level + 1)
        return For(self, node, level, data)

    async def process_while(self, node: node, level: int):
        data = await self.process_everything(node.parts, level + 1)
        return Loop(self, node, level, data)

    async def process_until(self, node: node, level: int):
        data = await self.process_everything(node.parts, level + 1)
        return Loop(self, node, level, data)

    async def process_function(self, node: node, level: int):
        data = await self.process_everything(node.parts, level + 1)
        return Function(self, node, level, data)

    async def process_tilde(self, node: node, level: int):
        return Tilde(self, node, level)
