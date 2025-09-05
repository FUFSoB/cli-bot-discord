from __future__ import annotations

from datetime import timedelta
from models.extra import has_object
from models.errors import ObjectNotFoundError, ObjectUnspecifiedError
import discord
from models.packages import Command
from models.utils import get_discord_id, run_in_executor
from ._classes import Mixin, QueueItem
from ._receivers import receivers
import youtube_dl

from typing import AsyncGenerator, Awaitable, Generator, Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result


class connect(Command, Mixin):
    """
    Connect to voice channel.
    """

    usage = "%(prog)s [channel]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "channel", nargs="?", type=get_discord_id, help="channel to connect into"
        )
        cls.argparser.add_argument(
            "-l", "--logs", type=get_discord_id, help="channel to log into"
        )

    @classmethod
    @has_object("guild")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        session = cls.get_and_check(event)
        voice = event.user.voice

        if args.channel:
            voice_channel = event.guild.get_channel(args.channel)
        elif voice:
            voice_channel = voice.channel
        else:
            raise ObjectUnspecifiedError("voice.channel")

        if type(voice_channel) is not discord.VoiceChannel:
            raise ObjectNotFoundError(args.channel)

        if args.logs:
            text_channel = event.guild.get_channel(args.logs)
            if not text_channel:
                raise ObjectNotFoundError(args.logs)
        else:
            text_channel = event.channel

        if session:
            await session.move_to(voice_channel)
        else:
            session = await voice_channel.connect()
            cls.set_session(event, session, text_channel)

        return f"Connected to {str(voice_channel)!r} ({voice_channel.id})"


class disconnect(Command, Mixin):
    """
    Disconnect from voice channel.
    """

    @classmethod
    @has_object("guild")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        session = cls.get_and_check(event)
        if session:
            session.stop_all()
            channel = session.original.channel
            await session.disconnect()
            return f"Disconnected from {str(channel)!r} ({channel.id})"
        else:
            return "Already not connected to any voice channel."


class play(Command, Mixin):
    """
    Play file or url in voice channel.
    """

    usage = "%(prog)s [query]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("query", nargs="*", help="query to search with")

        if cls.name != "play":
            return

        cls.argparser.add_argument(
            "-n",
            "--next",
            action="store_const",
            const=1,
            dest="index",
            help="insert after current song",
        )
        cls.argparser.add_argument(
            "-i", "--index", type=int, help="index to insert items at"
        )

    every_start = ("http://", "https://", "ftp://")

    @staticmethod
    def ydl_compatible(url: str) -> bool:
        extractors = youtube_dl.extractor.gen_extractors()
        for e in extractors:
            if e.suitable(url) and e.IE_NAME != "generic":
                return True
        return False

    @classmethod
    @run_in_executor
    def detect_query_type(
        cls, event: Event, query: Optional[str]
    ) -> Awaitable[Generator[str, None, None]]:
        if getattr(event.message, "attachments", None):
            yield "attachment"

        if not query:
            return

        if not query.startswith(cls.every_start):
            yield "ytdl_search"
            return

        if cls.ydl_compatible(query):
            yield "ytdl"
        else:
            yield "static"

    @classmethod
    async def create_item_generator(
        cls, event: Event, query: Optional[str]
    ) -> AsyncGenerator[QueueItem, None]:
        for t in await cls.detect_query_type(event, query):
            receiver = receivers[f"{t}_receiver"]
            async for item in receiver(event, query):
                yield item

    @classmethod
    @has_object("guild")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        session = await cls.fetch_and_check(event)

        count_index: int | None = args.index
        verbose: list[str] = []

        async for item in cls.create_item_generator(
            event, " ".join(args.query) or (str(stdin) if stdin else None)
        ):
            index = session.append(item, count_index)
            verbose.append(f"{index} -> {item.full_title}")
            if count_index:
                count_index += 1

        return "\n".join(verbose)


class queueitems(play):
    """
    Create music queue items to manipulate with them.
    """

    @classmethod
    @has_object("guild")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> list[QueueItem]:
        return [
            item
            async for item in cls.create_item_generator(
                event, " ".join(args.query) or str(stdin)
            )
        ]


class queue(Command, Mixin):
    """
    View or edit queue.
    """

    usage = "%(prog)s [action [extra]]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "action",
            choices=("clear", "shuffle", "remove"),
            help="action to take on queue",
        )
        cls.argparser.add_argument("extra", help="extra argument for action")

    @classmethod
    @has_object("guild")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        session = cls.get_and_check(event)
        action = args.action

        items = stdin and list(stdin.filter(QueueItem))

        if not session:
            if not items:
                return "No active music session"
            session = await cls.fetch_session(event)

        if items:
            verbose: list[str] = []
            count_index = int(args.extra) if args.extra else None

            for item in items:
                index = session.append(item)
                verbose.append(f"{index} -> {item.full_title}")
                if count_index:
                    count_index += 1

            return "\n".join(verbose)

        if not bool(session.queue):
            return "Queue is empty"

        if action == "clear":
            session.clear()
            return "Queue cleared"
        elif action == "shuffle":
            session.shuffle()
            return "Queue shuffled"
        elif action == "remove":
            index = int(args.extra)
            item = session.remove(index)
            return f"Removed from queue: {item.full_title}"

        shift = len(str(len(session.queue)))
        return "\n".join(
            f"{str(n).rjust(shift) if n else '>' * shift}| {str(i)}"
            for n, i in enumerate(session.queue)
        )


class player(Command, Mixin):
    """
    Manipulate with current music session.
    """

    usage = "%(prog)s [action [extra]]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "action",
            choices=(
                "stop",
                "pause",
                "play",
                "next",
                "previous",
                "repeat",
                "repeat-all",
                "reset",
                "seek",
                "info",
            ),
            default="pause",
            help="action to take on player",
        )
        cls.argparser.add_argument("extra", help="extra argument for action")

    @classmethod
    @has_object("guild")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        session = cls.get_and_check(event)
        action: str = args.action

        if not session:
            return "No active music session"

        if action == "stop":
            session.stop_all()
            return "Player stopped"

        elif action in ("play", "pause"):
            if session.is_paused():
                session.resume()
                return "Track resumed"
            else:
                session.pause()
                return "Track paused"

        elif action == "next":
            num = args.extra and int(args.extra)
            num = len(session.next(num))
            return f"{num} tracks skipped"

        elif action == "previous":
            num = args.extra and int(args.extra)
            num = len(session.previous(num))
            return f"{num} tracks returned"

        elif action == "repeat":
            r = session.repeat()
            return f"Repeat single track toggled {'on' if r else 'off'}"

        elif action == "repeat-all":
            r = session.repeat("all")
            return f"Repeat all tracks toggled {'on' if r else 'off'}"

        elif action == "reset":
            session.reset_current()
            return "Track started over"

        elif action == "seek":
            num = args.extra and float(args.extra) or 10
            sec = session.seek(num)
            if sec is None:
                return "Nothing to seek"
            return f"Track seeked to {sec}"

        elif action == "info":
            queue = session.queue
            item = queue.current
            if not item:
                return "There is no track playing now"
            duration = timedelta(seconds=item.duration) if item.duration else "null"
            passed = item.time_passed
            return "\n".join(
                (
                    f"Title: {item.title or 'null'}",
                    f"Track: {item.track or 'null'}",
                    f"Uploader: {item.uploader or 'null'}",
                    f"Artist: {item.artist or 'null'}",
                    f"Album: {item.album or 'null'}",
                    f"Position: {str(passed).split('.')[0]} (out of {duration})",
                    f"URL: {item.url}",
                    "",
                    f"Up next: {getattr(queue.next_track, 'full_title', 'null')}",
                )
            )
