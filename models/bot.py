from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Callable, Optional
from .config import Config

# import sys
import discord

# from .errors import BaseError
from .event import Event
from .appendices import Finder
from .database import db
from structure.data import fill_defaults
from .state import get_state

__all__ = ("Client", "clients")

clients: list["Client"] = []

loop = asyncio.get_event_loop()


class Client(discord.AutoShardedClient, Finder):
    def __init__(self, name: str, data: dict, config: Config, **options):
        self.real: bool = data.get("real", False)
        self.config = config

        intents_config: list[str] | str = data.get("intents", "default")
        if type(intents_config) is str:
            intents = getattr(
                discord.Intents, intents_config, discord.Intents.default
            )()
        else:
            intents = discord.Intents(**{i: True for i in intents_config})

        self.name = name

        super().__init__(loop=loop, intents=intents, **options)

        self.fully_ready = asyncio.Event()
        self.start(data["token"], data["bot"])

    def __repr__(self):
        if self.user:
            return f"<Client {self.name!r} tag={self.user}>"
        return f"<Client {self.name!r}>"

    def create_event(self, data: dict[str, Any]) -> Event:
        """
        Create event object from dictionary.
        """
        event_ = Event(self, "data")
        event_.from_data(**data)
        return event_

    async def fetch_events(
        self,
        *args: tuple[str, Callable[[Event], bool]],
        timeout: Optional[float] = None,
    ) -> AsyncGenerator[Event | None, None]:
        """
        Setup async generator for fetching events multiple times.
        """
        while True:
            yield await self.fetch_event(*args, timeout=timeout)

    async def fetch_event(
        self,
        *args: tuple[str, Callable[[Event], bool]],
        timeout: Optional[float] = None,
    ) -> Event | None:
        """
        Easily fetch event result.
        """
        futures = []

        for event, check in args:
            if not check:

                def check(*a):
                    return True

            future = loop.create_future()

            if event not in self._listeners:
                listeners = self._listeners[event] = []
            else:
                listeners = self._listeners[event]

            listeners.append((future, check))
            futures.append(future)

        try:
            done, _ = await asyncio.wait(
                futures, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
            )
            result = done.pop().result()
        except Exception:
            result = None

        for future in futures:
            future.cancel()

        return result

    def start(self, token: str, bot: bool) -> None:
        """
        Syncore start function.
        """

        loop.create_task(super().start(token, bot=bot))

    def dispatch(self, event: str, *args, **kwargs) -> None:
        """
        Handle dispatching to create own methods.
        """
        if "socket" in event:
            super().dispatch(event, *args, **kwargs)
        else:
            asyncio.ensure_future(Event.execute(self, event, *args, **kwargs))

    # async def on_error(self, event: str, *args, **kwargs):
    #     """
    #     Handle user-only exceptions.
    #     """
    #     obj = sys.exc_info()[1]
    #     if isinstance(obj, BaseError):
    #         # args[0].safely_finalize(result=obj)
    #         print(obj)
    #     else:
    #         await super().on_error(event, *args, **kwargs)

    async def on_ready(self, event: Event) -> None:
        """
        Do important init things when bot is fully loaded and ready to work.
        """
        if self.real:
            self.app = await self.application_info()

            await fill_defaults(self, event)
            event.state.finalize()

            async for schedule in db.get_schedules():
                state = get_state(self, int(schedule.data["state_id"]))
                schedule.state = state
                state.append_event(schedule)
                schedule.cached_start(self)

            await self.change_presence(
                activity=discord.Game(name="$ help"), status=discord.Status.online
            )

            self.fully_ready.set()

            print("Hello world!")

    async def on_guild_available(self, event: Event) -> None:
        """
        Setup guilds.
        """
        if not self.real:
            return
        try:
            await event.guild_state.setup(event)
        except Exception as ex:
            print(ex)

    async def on_message(self, event: Event) -> None:
        """
        Do things when message is sent.
        """
        if not self.real:
            return
        if event.user.bot:
            return

        await event.background_finalize()

    async def on_raw_message_edit(self, event: Event) -> None:
        """
        Do things when message is edited.
        """
        if not self.real:
            return
        if event.prev_message and event.prev_message.content == event.message.content:
            return
        if event.user.bot:
            return

        await event.background_finalize()

    # async def on_any(self, event: Event):
    #     try:
    #         print(event)
    #     except Exception:
    #         __import__("traceback").print_exc()
