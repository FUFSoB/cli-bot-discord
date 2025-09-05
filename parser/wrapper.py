from __future__ import annotations

import regex
import discord
from models.packages import get_command, get_commands
from models.errors import (
    BaseError,
    UnknownCommandError,
    IgnoreError,
    LimitExceededError,
    KeywordError,
    ContinueError,
    BreakError,
    ReturnError,
    FalseError,
    InternalError,
    ParsingError,
    NoFileFoundError,
    # IfEndError,
    # IfPreEndError,
)
from structure.data import get_path
from models.utils import NoneType
from models.extra import Getter, types, Deferred, Setup, DynamicDictionary, get_type
import pwnlib.util.safeeval as safeeval
import traceback
import shlex
from typing import Any, Iterator, Optional, Iterable, Callable, Pattern, TYPE_CHECKING
import copy

if TYPE_CHECKING:
    from .processing import Processor
    from bashlex.ast import node
    from models.typings import WrapperType, StdoutCallable, Some, GetterType
    from models.event import Event


class Result:
    """
    Class for mixing and sorting results.
    """

    ignore_errors: bool = True
    prefix: str = ""
    syntax: str = ""
    post_prefix: str = ""
    suffix: str = ""
    send: bool = True
    return_on_error: bool = False

    # def __class_getitem__(cls, item: type | tuple[type]):
    #     def convert(i): return i.__name__ if type(i) is type else str(i)

    #     if type(item) is tuple:
    #         return f"""{cls.__name__}[{', '.join(
    #             convert(i) for i in item
    #         )}]"""

    #     return f"{cls.__name__}[{convert(item)}]"

    def __init__(self, *, data: Any = None, name: Optional[str] = None):
        self.data = []
        if data:
            self.append(data)
        self.name = name
        self.last: Any = None

    def __repr__(self):
        return f"Result{self.data!r}"

    def __len__(self):
        return len(self.data)

    def __getitem__(self, item: int | slice) -> Any:
        return self.data[item]

    def __iter__(self) -> Iterator:
        yield from self.data

    def __lshift__(self, other: Any):
        self.append(other)
        return self

    def __rlshift__(self, other: Any):
        self.insert(other)
        return self

    def __rshift__(self, other: Any):
        self.append(other)
        return self

    def __rrshift__(self, other: Any):
        self.insert(other)
        return self

    @property
    def short_content(self) -> str | None:
        name = self.name
        if name:
            return (
                (name[:17] + "<...>" + name[-17:]) if len(name) > 40 else name
            ).replace("\n", "\\n")
        else:
            return None

    @property
    def total_options(self) -> dict[str, Any]:
        return {key: getattr(self, key, None) for key in self.__annotations__.keys()}

    def set_name(self, name: str) -> None:
        self.name = name

    def clear(self) -> None:
        self.data.clear()
        self.last = None

    def apply_option(self, option: str, value: Any) -> None:
        setattr(self, option, value)

    def append(self, object: Any, inside: bool = False):
        if type(object) in (list, Result):
            for element in object:
                self.append(element, True)
        elif object is not None:
            self.data.append(object)

        if not inside:
            self.last = object

    def insert(self, object: Any, inside: bool = False):
        if type(object) in (list, Result):
            for element in object[::-1]:
                self.insert(element, True)
        elif object is not None:
            self.data.insert(0, object)

        if not inside:
            self.last = object

    def pop(self) -> "Result":
        copy = self.data.copy()
        self.data.clear()
        return Result(data=copy)

    def filter(
        self,
        *types: type[Some],
        truth: bool = True,
        instance: bool = False,
        iterable: Optional[Iterable[Any]] = None,
        convert: Optional[Callable[[Any], Any]] = None,
    ) -> Iterator[Some]:
        if truth:
            if instance:

                def check(element):
                    return isinstance(element, types)

            else:

                def check(element):
                    return type(element) in types

        else:
            if instance:

                def check(element):
                    return not isinstance(element, types)

            else:

                def check(element):
                    return type(element) not in types

        for element in iterable or self.data:
            if check(element):
                yield convert(element) if convert else element

    def are_getters(self) -> Iterator[GetterType]:
        yield from self.filter(Getter, instance=True)

    def non_getters(self) -> Iterator:
        yield from self.filter(Getter, truth=False, instance=True)

    @property
    def getters(self) -> list[GetterType]:
        return list(self.are_getters())

    @property
    def not_getters(self) -> list:
        return list(self.non_getters())

    def are_errors(self) -> Iterator[BaseError]:
        yield from self.filter(BaseError, instance=True)

    def are_ignore_errors(self) -> Iterator[IgnoreError]:
        yield from self.filter(IgnoreError, instance=True)

    @property
    def errors(self) -> list[BaseError]:
        return list(self.are_errors())

    def non_discord(self) -> Iterator:
        yield from self.filter(NoneType, discord.Embed, discord.File, truth=False)

    def non_errors(self) -> Iterator:
        yield from self.filter(
            BaseError, truth=False, instance=True, iterable=self.non_discord()
        )

    def non_ignore_errors(self) -> Iterator:
        yield from self.filter(
            IgnoreError, truth=False, instance=True, iterable=self.non_discord()
        )

    def __str__(self):
        return "\n".join(
            str(x)
            for x in (
                self.non_ignore_errors() if self.ignore_errors else self.non_discord()
            )
        )

    def are_embeds(self) -> Iterator[discord.Embed]:
        yield from self.filter(discord.Embed)

    @property
    def embeds(self) -> list[discord.Embed]:
        return list(self.are_embeds())

    def are_files(self) -> Iterator[discord.File]:
        yield from self.filter(discord.File)

    @property
    def files(self) -> list[discord.File]:
        return list(self.are_files())

    def are_bytes(self) -> Iterator[bytes]:
        yield from self.filter(bytes)

    def __bytes__(self):
        return b"\n".join(self.are_bytes())

    def as_data(self) -> bytes | str:
        return bytes(self) or str(self)

    def keyword_error(self) -> None:
        if isinstance(self.last, KeywordError):
            raise self.last

    def last_keyword_error(self) -> None:
        if type(self.last) is Result:
            self.last.keyword_error()


class Wrapper:
    node: node
    processor: Processor
    word: str

    @property
    def pos(self) -> tuple[int, int]:
        return self.node.pos

    @property
    def kind(self) -> str:
        return self.node.kind

    def __str__(self):
        return self.processor.string[slice(*self.pos)]

    @property
    def after(self) -> str:
        return self.processor.string[self.pos[0] :]

    @property
    def before(self) -> str:
        return self.processor.string[: self.pos[0]]


class Word(Wrapper):
    def __init__(
        self, processor: Processor, node: node, level: int, data: list[WrapperType]
    ):
        self.processor = processor
        self.node = node
        self.level = level
        self.word = node.word
        self.data = data

    def __repr__(self):
        return f"<Word {self.word!r} data={self.data}>"

    async def finalize(
        self, event: Event, *, split: bool = True, typed: bool = False
    ) -> str | Result | Any:
        final = self.word

        if not self.data:
            return final

        for object in self.data:
            result = await object.finalize(event)
            if typed and final == str(object):
                return result
            final = final.replace(str(object), str(result), 1)

        if self.node.kind == "word" and split:
            return final.split()
        else:
            return final


class Command(Wrapper):
    def __init__(
        self,
        processor: Processor,
        node: node,
        level: int,
        data: list[WrapperType | str],
    ):
        self.processor = processor
        self.node = node
        self.level = level
        self.data = data
        self.name: Optional[str] = None

    def __repr__(self):
        if not self.name:
            return f"<Command data={self.data}>"
        return f"<Command name={self.name!r} args={self.args}>"

    def top_priority(self, event):
        return (
            self.level == 0
            and not event.state.skip_top_priority
            # or self.substitution
        )

    async def finalize(
        self,
        event: Event,
        *,
        stdin: Optional[Result] = None,
        stdout: Optional[StdoutCallable] = None,
    ) -> Optional[Result | Any]:
        args: list[str] = []
        self.args = args

        for object in self.data:
            if type(object) is str:
                result: str = object
            else:
                result: list | str | Assignment | Redirect = await object.finalize(
                    event
                )

            if type(object) is Assignment:
                continue

            elif type(object) is Redirect:
                if "<" in object.type:
                    stdin: Result | Any = result
                else:
                    stdout: StdoutCallable = result

            elif type(result) is list:
                args.extend(result)
            else:
                args.append(result)

        if not args:
            if stdout and stdin:
                await stdout(stdin.as_data())
                return None
            return stdin

        if self.top_priority(event):
            old_args = event.state.command_args
            event.state.set_command_arguments(*args)
        else:
            old_args = None

        self.name = name = args.pop(0)

        try:
            command = await get_command(name, event)

            if not command:
                return UnknownCommandError(name)

            if type(command) is list:
                return await AliasedSequence(name, self, command, args).finalize(event)

            result = await command.execute(event, args, stdin)
        except KeywordError:
            raise
        except BaseError as ex:  # here
            result = ex
        except Exception:
            raise

        if old_args:
            event.state.set_command_arguments(*old_args)

        final = Result() << result

        if stdout:
            try:
                await stdout(final.as_data())
            except BaseError as ex:
                final = Result() << ex
            except Exception:
                raise
            else:
                return None

        return final


class AliasedSequence(Wrapper):
    def __init__(
        self, name: str, original: Command, data: list[WrapperType], left: list[str]
    ):
        self.name = name
        self.original = original
        self.processor = original.processor
        self.node = original.node
        self.level = original.level
        self.data = copy.deepcopy(data)
        self.data_left = left

    def __repr__(self):
        return repr(self.original)

    def top_priority(self, event: Event) -> bool:
        return self.original.top_priority(event)

    async def finalize(self, event: Event) -> Result:
        last = self.data[-1]

        while type(last) is not Command:
            last = last.data[-1]

        last.data.extend(self.data_left)
        result = Result()

        event.used_aliases.append(self.name)

        for wrapper in self.data:
            result << await wrapper.finalize(event)

        event.used_aliases.remove(self.name)

        return result


class Substitution(Wrapper):
    def __init__(self, processor: Processor, node: node, level: int, actual: Command):
        self.processor = processor
        self.node = node
        self.level = level
        self.actual = actual

    def __repr__(self):
        return f"<Substitution {self.actual}>"

    async def finalize(self, event: Event) -> Optional[Result | Any]:
        return await self.actual.finalize(event)


class List(Wrapper):
    def __init__(
        self, processor: Processor, node: node, level: int, data: list[WrapperType]
    ):
        self.processor = processor
        self.node = node
        self.level = level
        self.data = data

    def __repr__(self):
        return f"<List {self.data}>"

    async def finalize(self, event: Event) -> Result:
        result = Result()
        skip = False

        for object in self.data:
            if skip:
                skip = False

            elif type(object) is Operator:
                op = await object.finalize(event, previous=result.last)
                if not op:
                    skip = True

            else:
                try:
                    result << await object.finalize(event)
                # except ReturnError:
                #     raise
                except KeywordError as ex:
                    result << ex
                    break
                except BaseError as ex:
                    result << ex
                except Exception as ex:
                    result << InternalError(ex)
                    print(traceback.format_exc())

        return result


class Operator(Wrapper):
    def __init__(self, processor, node, level):
        self.processor = processor
        self.node = node
        self.level = level
        self.type = node.op

    def __repr__(self):
        return f"<Operator {self.type}>"

    async def finalize(self, event=None, *, previous):
        was_exception = isinstance(previous, BaseError) or bool(
            getattr(previous, "errors", False)
        )

        if self.type == "&&" and was_exception:
            return False
        elif self.type == "||" and not was_exception:
            return False
        elif self.type != "||" and isinstance(previous, ReturnError):
            return False

        return True


class Pipe(Wrapper):
    def __init__(self, processor, node, level):
        self.processor = processor
        self.node = node
        self.level = level

    def __repr__(self):
        return "<Pipe>"


class Pipeline(Wrapper):
    def __init__(self, processor, node, level, data):
        self.processor = processor
        self.node = node
        self.level = level
        self.data = data

    def __repr__(self):
        return f"<Pipeline {self.data}>"

    async def finalize(self, event):
        result = Result()
        pipe = False

        for num, object in enumerate(self.data):
            if type(object) is Pipe:
                pipe = True
            else:
                try:
                    result << await object.finalize(
                        event, stdin=result.pop() if pipe else None
                    )
                    result.last_keyword_error()
                except ReturnError:
                    raise

                pipe = False

        return result


class Redirect(Wrapper):
    def __init__(self, processor, node, level, output):
        self.processor = processor
        self.node = node
        self.level = level
        self.heredoc = node.heredoc
        self.output = output
        self.input = node.input
        self.type = node.type

    def __repr__(self):
        return f"<Redirect ({self.type})>"

    async def finalize(self, event):
        type_ = self.type
        output = await self.output.finalize(event, split=False)
        result = None

        if "<" in type_:
            result = Result()
            if type_ == "<":
                result << await (
                    await get_path(output, event=event, directory=False)
                ).read(event=event)
            elif type_ == "<<":
                result << self.heredoc.value.removesuffix(f"\n{output}")
            elif type_ == "<<<":
                result << output

        elif ">" in type_:
            get_file = get_path(output, event=event, directory=False, create=True)
            if type_ == ">":

                async def result(content):
                    file = await get_file
                    await file.write(content, event=event)

            elif type_ == ">>":

                async def result(content):
                    file = await get_file
                    await file.write(content, False, event=event)

        return result


class Assignment(Wrapper):
    pattern: Pattern = regex.compile(r"(.+?)(\+?=)(.*)", regex.DOTALL)

    def __init__(self, processor, node, level, data):
        self.processor = processor
        self.node = node
        self.level = level
        self.word = node.word
        self.data = data

    def __repr__(self):
        return f"<Assignment {self.word!r} data={self.data}>"

    @classmethod
    def function(cls, match, event, export):
        name, type_, value = match.groups()

        if type_ == "+=":

            def edit(x, y):
                return x + y

        else:
            edit = None

        event.set_variable(name, value, export=export, edit=edit)

    async def finalize(self, event):
        final = self.word

        for object in self.data:
            result = str(await object.finalize(event))
            final = final.replace(str(object), result, 1)

        final = final.replace("\\n", "\n")

        self.function(self.pattern.match(final), event, False)


class Parameter(Wrapper):
    extra_regex: Pattern = regex.compile(r"(.+?)(?:\[(.*?)\])+", regex.DOTALL)

    def __init__(self, processor, node, level):
        self.processor = processor
        self.node = node
        self.level = level
        self.value = node.value
        if match := self.extra_regex.match(self.value):
            self.value = match.groups()[0]
            self.get_value = match.captures(2)
        else:
            self.get_value = ()

    def __repr__(self):
        return f"<Parameter {self.value}>"

    async def finalize(self, event):
        var = event.get_variable(self.value)

        for capture in self.get_value:
            if type(var) in (str, list, Result):
                capture = int(capture)
            var = var[capture]

        return var


class Compound(Wrapper):
    def __init__(self, processor, node, level, data):
        self.processor = processor
        self.node = node
        self.level = level
        self.data = data

    def __repr__(self):
        return f"<Compound data={self.data}>"

    async def finalize(self, event, *, stdin=None, stdout=None):
        result = Result()

        for object in self.data:
            if (
                type(object)
                is Reservedword
                # and object.word in Function.actions
            ):
                continue

            result << await object.finalize(event)

        return result


class Reservedword(Wrapper):
    def __init__(self, processor, node, level):
        self.processor = processor
        self.node = node
        self.level = level
        self.word = node.word

    def __repr__(self):
        return f"<Reservedword {self.word!r}>"

    async def finalize(self, event=None):
        return self.word


class If(Wrapper):
    actions = {
        "if": "condition",
        "elif": "condition",
        ";": None,
        "then": "action",
        "else": "else_action",
        "fi": "end",
    }

    def __init__(self, processor, node, level, data):
        self.processor = processor
        self.node = node
        self.level = level
        self.data = data

    def __repr__(self):
        return f"<If data={self.data}>"

    async def finalize(self, event):
        condition_result = None
        result = Result()
        action = None

        for object in self.data:
            if type(object) is Reservedword:
                action = self.actions[object.word]

            elif action == "condition":
                condition_result = await object.finalize(event)

            elif (
                action == "action"
                and condition_result is not None
                and not any(isinstance(x, BaseError) for x in condition_result)
            ) or (action == "else_action"):
                try:
                    result << await object.finalize(event)
                    result.last_keyword_error()
                # except IfEndError:
                #     break
                except ReturnError as ex:
                    raise ReturnError(result << ex.value)
                # except IfPreEndError:
                #     raise IfEndError()
                break

        return result


class For(Wrapper):
    actions = {
        "for": "variable",
        "in": "list",
        ";": None,
        "do": "action",
        "done": "end",
    }

    def __init__(self, processor, node, level, data):
        self.processor = processor
        self.node = node
        self.level = level
        self.data = data

    def __repr__(self):
        return f"<For data={self.data}>"

    async def finalize(self, event):
        name = None
        iterable = []
        result = Result()
        action = None

        for object in self.data:
            if type(object) is Reservedword:
                action = self.actions[object.word]

            elif action == "variable":
                name = await object.finalize(event)

            elif action == "list":
                output = await object.finalize(event, typed=True)
                if type(output) in (list, Result):
                    iterable.extend(output)
                else:
                    iterable.append(output)

            elif action == "action":
                for variable in iterable:
                    event.set_variable(name, variable)
                    try:
                        result << await object.finalize(event)
                        result.last_keyword_error()
                    except BreakError:
                        break
                    except ContinueError:
                        continue
                    except ReturnError as ex:
                        raise ReturnError(result << ex.value)
                    except Exception:
                        pass
                break

        return result


class Loop(Wrapper):
    actions = {
        "while": "condition",
        "until": "false_condition",
        "do": "action",
        "done": "end",
    }

    def __init__(self, processor, node, level, data):
        self.processor = processor
        self.node = node
        self.level = level
        self.data = data

    def __repr__(self):
        return f"<Loop data={self.data}>"

    async def finalize(self, event):
        condition = None
        is_true = True
        result = Result()
        action = None

        for object in self.data:
            if type(object) is Reservedword:
                action = self.actions[object.word]

            elif action == "condition":
                condition = object.finalize

            elif action == "false_condition":
                condition = object.finalize
                is_true = False

            elif action == "action":
                total = 0
                while True:
                    total += 1
                    if total > 1000:
                        raise LimitExceededError(1000, "maximum repeatings")

                    condition_result = not any(
                        isinstance(x, BaseError) for x in (await condition(event))
                    )  # is true when no errors found

                    if (not condition_result and is_true) or (
                        condition_result and not is_true
                    ):
                        break

                    try:
                        result << await object.finalize(event)
                        result.last_keyword_error()
                    except BreakError:
                        break
                    except ContinueError:
                        continue
                    except ReturnError as ex:
                        raise ReturnError(result << ex.value)
                    except Exception:
                        pass
                break

        return result


class Function(Wrapper):
    actions = {"function": None, "(": None, ")": None}

    def __init__(self, processor, node, level, data):
        self.processor = processor
        self.node = node
        self.level = level
        self.data = data
        self.function = None
        self.name = None

    def __repr__(self):
        return f"<Function data={self.data}>"

    async def finalize(self, event):
        name = None

        for object in self.data:
            if type(object) is Reservedword:
                continue

            elif type(object) is Word:
                self.name = name = await object.finalize(event)

            elif type(object) is Compound:
                self.function = object.finalize

        event.set_function(name, self)

    async def execute(self, event, args, stdin):
        old_args = event.state.command_args
        event.state.set_command_arguments(self.name, *args)

        event.set_variable("_stdin", stdin)
        result = None
        try:
            result = await self.function(event)
            result.last_keyword_error()
        except ReturnError as ex:
            result = ex.value
        except Exception:
            pass
        event.pop_variable("_stdin")

        event.state.set_command_arguments(*old_args)

        return result


class Tilde(Wrapper):
    def __init__(self, processor, node, level):
        self.processor = processor
        self.node = node
        self.value = node.value
        self.level = level

    def __repr__(self):
        return f"<Tilde {self.value}>"

    async def finalize(self, event=None):
        return self.value


class Expression(Wrapper, Setup):
    codes = safeeval._values_codes + [
        "COMPARE_OP",
        "POP_JUMP_IF_FALSE",
        "JUMP_IF_TRUE_OR_POP",
        "JUMP_IF_FALSE_OR_POP",
        "CONTAINS_OP",
        "CALL_FUNCTION",
        "IS_OP",
        "LIST_EXTEND",
        "BUILD_CONST_KEY_MAP",
        "BINARY_SUBSCR",
        "CALL_FUNCTION_KW",
        "STORE_NAME",
        "BUILD_SLICE",
        "FORMAT_VALUE",
        "BUILD_STRING",
        "PUSH_NULL",
        "CALL",
        "TO_BOOL",
        "BINARY_SLICE",
        "FORMAT_WITH_SPEC",
    ]

    def __init__(self, processor, node, level):
        self.processor = processor
        self.node = node
        self.level = level
        string = (
            str(self)  # .replace("\\\n", " ")
            .removeprefix("[")
            .removesuffix("]")
            .strip()
        )

        self.return_value = False
        self.return_expr = False

        if string.startswith("return"):
            self.return_value = True
            string = string.removeprefix("return").lstrip()
        elif string.startswith("expr"):
            self.return_expr = True
            string = string.removeprefix("expr").lstrip()

        if string.startswith("from"):
            string = string.removeprefix("from").lstrip()
            if not (string[0] == string[-1] == "'"):
                raise ParsingError(
                    f"From-expression <{string}> has no "
                    "opening or closing single 'quotation marks'."
                )
            string = string[1:-1].strip()

        self.expression = string.replace("\\(", "(").replace("\\)", ")")
        self.tested = safeeval.test_expr(self.expression, self.codes)

    def __repr__(self):
        return f"<Expression {self.expression}>"

    async def finalize(self, event, *args, **kwargs):
        if self.return_expr:
            return Result() << self.expression

        env = self.dynamic_env.prepare_event(event)
        result = eval(self.tested, env)

        if type(result) is Deferred:
            result = await result()

        # print(self.expression, repr(result))

        if self.return_value:
            return Result() << result
        elif not result:
            raise FalseError()

    @staticmethod
    async def command(event, string, stdin=None):
        name, *args = shlex.split(string)

        command = await get_command(name, event)

        if not command:
            return UnknownCommandError(name)

        if stdin is not None:
            if type(stdin) is Deferred:
                stdin = await stdin()
            stdin = Result() << stdin

        try:
            return await command.execute(event, args, stdin)
        except BaseError as ex:
            return ex
        except Exception as ex:
            return InternalError(ex)

    @staticmethod
    async def file(event, path, action=None):
        directory = {"directory-like": True, "file-like": False}.get(action, None)

        try:
            file = await get_path(path, event=event, directory=directory)
        except NoFileFoundError as ex:
            if action in (None, "exists"):
                return False
            return ex
        except BaseError as ex:
            return ex
        except Exception as ex:
            return InternalError(ex)

        if action in ("read", "write", "execute"):
            return file.check(action, event=event, exception=False)
        elif action in ("owner", "group"):
            return getattr(file.mode, action)
        elif action in ("size",):
            return await getattr(file, action)(event=event)
        elif action in ("kind",):
            return getattr(file, action)
        elif action == "content":
            return await file.read(event=event)

        return True

    @staticmethod
    async def all(*args):
        async for arg in (
            await arg() if type(arg) is Deferred else arg for arg in args
        ):
            if not arg:
                return arg
        return True

    @staticmethod
    async def any(*args):
        async for arg in (
            await arg() if type(arg) is Deferred else arg for arg in args
        ):
            if arg:
                return arg
        return False

    @staticmethod
    async def contains(*args):
        args = [await arg() if type(arg) is Deferred else arg for arg in args]
        if args[0] in args[1]:
            return args[0]
        return False

    @classmethod
    def setup(cls):
        converters = {
            **types,
            "re": regex.match,
            "bool": bool,
            "dict": dict,
            "type": get_type,
        }

        async def convert(func, *args):
            args = [
                await value() if type(value) is Deferred else value for value in args
            ]

            return func(*args)

        def converter_fab(func):
            def inner(*args):
                return Deferred(convert, func, *args)

            return inner

        def command_fab(name, event):
            def inner(string="", stdin=None):
                return Deferred(
                    cls.command, event, (name + " " + string).strip(), stdin
                )

            return inner

        def file_fab(event):
            def inner(path, action=None):
                return Deferred(cls.file, event, path, action)

            return inner

        cls.dynamic_env = DynamicDictionary(
            {
                "__builtins__": {},
                "all": lambda *args: Deferred(cls.all, *args),
                "any": lambda *args: Deferred(cls.any, *args),
                "contains": lambda *args: Deferred(cls.contains, *args),
            }
        )
        cls.dynamic_env.add_converter(
            tuple(converters), lambda name: converter_fab(converters[name])
        )
        cls.dynamic_env.add_converter(
            lambda: [c.name for c in get_commands()],
            lambda name, event: command_fab(name, event),
            event=True,
        )
        cls.dynamic_env.add_converter(
            ("exec",), lambda _, event: command_fab("", event), event=True
        )
        cls.dynamic_env.add_converter(
            ("file",), lambda _, event: file_fab(event), event=True
        )
