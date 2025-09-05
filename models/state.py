from __future__ import annotations

import asyncio
from operator import attrgetter
from typing import Any, Callable, Coroutine, Literal, Optional, TYPE_CHECKING
from inspect import isfunction
import discord
from discord.utils import get
from .errors import (
    NoProcessFoundError,
    UndefinedVariableError,
    ReservedVariableError,
    NoFileFoundError,
)
from structure.data import get_home, get_path, get_root
from .packages import file_commands
from .utils import try_coro
import ujson

if TYPE_CHECKING:
    from .typings import (
        FunctionType,
        StateObject,
        GetStateObject,
        AllStateType,
        DirectoryType,
    )
    from .bot import Client
    from .event import Event
    from parser.wrapper import Result
    from structure.filesystem import RootDirectory

__all__ = ("states", "get_state", "UserState", "GuildState", "DefaultState")

states = []


def get_state(client: Client, object: GetStateObject) -> AllStateType:
    object_type = type(object)
    if object_type is discord.Member:
        object = object._user
    elif object_type is int:
        object = client.get_guild(object) or client.get_user(object)
        if not object:
            return None
        object_type = type(object)

    state = get(states, object__id=object.id, client=client)

    if not state:
        if object_type is discord.Guild:
            state = GuildState(client, object)
        elif object_type is discord.Object:
            state = DefaultState(client, object)
        else:
            state = UserState(client, object)
        states.append(state)

    return state


class BaseState:
    def __init__(self, client: Client, object: StateObject):
        self.client = client
        self.object = object

        self.exported_variables: dict[str, Any] = {}
        self.exported_functions: dict[str, FunctionType] = {}
        self.aliases: dict[str, list] = {}

        self.command_args: tuple[str] = ("cli",)

        self.directory: Optional[DirectoryType] = None

        self.special_variables: dict[str, Callable[[Event], Any]] = {
            "_args": lambda _: self.command_args,
            "@": lambda _: " ".join(self.command_args[1:]),
            "_groups": lambda event: list(event.groups()),
            "_pid": lambda event: event.pid,
            "_prefixes": lambda event: event.prefixes,
            "_event": lambda event: event.name,
        }

        self.skip_top_priority: bool = False
        self.redirects: list[Callable[[Event], Coroutine]] = []

        self.pid: int = 0
        self.last_pid: int = 0
        self.short_content: str = f"(state {object.id})"
        self.events: list = [self]

        if self.kind == "guild":
            self.config: dict[str] = {}

    @property
    def kind(self) -> Literal["user", "guild", "default"]:
        if type(self.object) is discord.Guild:
            return "guild"
        elif not self.object:
            return "default"
        else:
            return "user"

    async def setup(self, event: Event) -> Optional[Result]:
        if not self.directory:
            prev_guild_only = event.guild_only
            if self.kind == "guild":
                event.guild_only = True

            self.directory = await get_home(self.kind, event=event)

            try:
                rc = await self.directory.select(".clirc", event=event)
                result = await rc.execute(event=event)
            except NoFileFoundError:
                rc = await get_path("/scripts/.clirc", event=event)
                result = await rc.execute(event=event)
            except Exception:
                result = None

            if self.kind == "guild":
                try:
                    cfg = await self.directory.select(".config.json")
                    cfg = ujson.loads(await cfg.read(event=event))
                    self.config.update(cfg)
                except Exception:
                    pass

            try:
                auto = await self.directory.select(".autostart", event=event)
                async for file in auto.read_files(event=event):
                    await try_coro(file.execute(event=event))
            except Exception:
                pass

            event.temporary_variables.clear()
            event.temporary_functions.clear()

            event.guild_only = prev_guild_only

            return result

    @property
    def get_pid(self) -> int:
        self.last_pid += 1
        return self.last_pid

    @property
    def processes(self) -> list:
        return self.events + self.redirects

    @property
    def sorted_processes(self) -> list:
        return list(sorted(self.processes, key=attrgetter("pid")))

    def append_event(self, event: Any) -> None:
        event.set_pid(self.get_pid)
        self.events.append(event)

    def get_process(self, pid: int) -> Any:
        proc = get(self.processes, pid=pid)
        if not proc:
            raise NoProcessFoundError(pid)
        return proc

    def remove_event(self, event: Any) -> None:
        try:
            self.events.remove(event)
        except ValueError:
            pass

    def add_redirect(self, object: Callable[[Event], Coroutine]) -> None:
        object.set_pid(self.get_pid)
        self.redirects.append(object)

    def pop_redirect(self, object: Any) -> None:
        try:
            self.redirects.remove(object)
        except ValueError:
            pass

    def variables(self, event: Event) -> dict[str, Any]:
        return (
            event.objects_cli
            | self.special_variables
            | self.exported_variables
            | event.temporary_variables
        )

    def set_variable(
        self,
        event: Event,
        name: str,
        value: Any,
        export: bool = False,
        edit: Optional[Callable[[Any, Any], Any]] = None,
    ) -> Any:
        if name in event.objects_cli | self.special_variables:
            raise ReservedVariableError(name)

        if export:
            variable_dict = self.exported_variables
        else:
            variable_dict = event.temporary_variables

        if edit:
            previous_value = self.variables(event).get(name)
            if previous_value is None:
                raise UndefinedVariableError(name)

            value = edit(previous_value, value)

        variable_dict[name] = value

        return value

    def get_variable(
        self, event: Event, name: str, variables: Optional[dict] = None
    ) -> Any:
        variables = variables or self.variables(event)
        variable = variables.get(name, None)

        if isfunction(variable):
            variable = variable(event)
        elif variable is None:
            try:
                variable = self.command_args[int(name)]
            except (ValueError, IndexError):
                pass

        return "" if variable is None else variable

    def pop_variable(self, event: Event, name: str, export: bool = False) -> Any:
        if export:
            variable_dict = self.exported_variables
        else:
            variable_dict = event.temporary_variables

        try:
            return variable_dict.pop(name) or ""
        except KeyError:
            return ""

    def functions(self, event: Event) -> dict[str, FunctionType]:
        return self.exported_functions | event.temporary_functions

    def set_function(
        self, event: Event, name: str, body: FunctionType, export: bool = False
    ) -> FunctionType:
        if export:
            function_dict = self.exported_functions
        else:
            function_dict = event.temporary_functions

        function_dict[name] = body

        return body

    def get_function(
        self,
        event: Event,
        name: str,
        functions: Optional[dict[str, FunctionType]] = None,
    ) -> Optional[FunctionType]:
        functions = functions or self.functions(event)
        return functions.get(name, None)

    def pop_function(
        self, event: Event, name: str, export: bool = False
    ) -> Optional[FunctionType]:
        if export:
            function_dict = self.exported_functions
        else:
            function_dict = event.temporary_functions

        try:
            return function_dict.pop(name)
        except KeyError:
            return None

    def set_alias(self, name: str, value: list) -> None:
        self.aliases[name] = value

    def get_alias(
        self, event: Event, name: str, aliases: Optional[dict[str, list]] = None
    ) -> Optional[list]:
        if name in event.used_aliases:
            return None
        aliases = aliases or self.aliases
        return aliases.get(name, None)

    def pop_alias(self, name: str) -> Optional[list]:
        try:
            return self.aliases.pop(name)
        except KeyError:
            return None

    def set_command_arguments(self, *args: str):
        self.command_args = args

    def set_directory(self, directory: DirectoryType) -> None:
        self.directory = directory

    def clear(self) -> None:
        self.exported_variables.clear()
        self.exported_functions.clear()

    def reset(self) -> list:
        active = []

        for proc in self.events[1:-1]:
            if type(proc).__name__.lower() == "schedule":
                active.append(proc)
                continue
            asyncio.ensure_future(proc.cancel())

        states.remove(self)
        return active

    async def cancel(self) -> list:
        return self.reset()


class UserState(BaseState):
    def __init__(self, client: Client, user: discord.User):
        super().__init__(client, user)

        self.special_variables |= {"_user": user.id}


class GuildState(BaseState):
    def __init__(self, client: Client, guild: discord.Guild):
        super().__init__(client, guild)

        self.special_variables |= {"_guild": guild.id}


class DefaultState(BaseState):
    def __init__(self, client: Client, object: discord.Object):
        super().__init__(client, object)
        self.directory: RootDirectory = get_root()

    def finalize(self) -> None:
        file_commands.extend(self.exported_functions.values())
