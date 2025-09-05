from __future__ import annotations

from itertools import zip_longest
import aiohttp
import io
import discord
from models.packages import Command
from models.extra import has_object, required
from models.errors import ObjectNotFoundError, ObjectUnspecifiedError
from models.utils import get_discord_id, try_get_discord_id, get_message_url, try_coro
from models.response import generate_pages_dictionary
from models.database import db
from models.assets import assets

from typing import Any, AsyncGenerator, Callable, Coroutine, Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result

if False:
    from models.typings import Some

EmbedEmpty = discord.Embed.Empty


class embed(Command):
    """
    Create discord embed.
    """

    usage = "%(prog)s [options*]"
    epilog = "You can provide dictionary that represents embed to stdin."

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "-t", "--title", help="title to set", metavar="string"
        )
        cls.argparser.add_argument(
            "-d", "--description", help="description to set", metavar="string"
        )
        cls.argparser.add_argument(
            "-c",
            "--color",
            help="color to set",
            type=lambda x: int(x.removeprefix("0x"), base=16),
            metavar="hex",
        )
        cls.argparser.add_argument(
            "--timestamp", help="set timestamp to embed", action="store_true"
        )
        cls.argparser.add_argument("-u", "--url", help="url to set", metavar="url")
        cls.argparser.add_argument(
            "-f", "--footer", help="footer to set", metavar="string"
        )
        cls.argparser.add_argument(
            "--footer-icon", help="footer icon to set", metavar="image_url"
        )
        cls.argparser.add_argument(
            "-i", "--image", help="image to set", metavar="image_url"
        )
        cls.argparser.add_argument(
            "-T", "--thumbnail", help="thumbnail to set", metavar="image_url"
        )
        cls.argparser.add_argument(
            "-a", "--author", help="author to set", metavar="string"
        )
        cls.argparser.add_argument(
            "--author-url", help="author url to set", metavar="url"
        )
        cls.argparser.add_argument(
            "--author-icon", help="author icon to set", metavar="image_url"
        )
        cls.argparser.add_argument(
            "-D",
            "--as-dict",
            action="store_true",
            help="convert embed into dictionary object",
        )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> discord.Embed | dict[str]:
        if stdin:
            if args.as_dict:
                return next(stdin.filter(dict))
            return discord.Embed.from_dict(next(stdin.filter(dict)))

        def get(attr: str):
            return getattr(args, attr) or EmbedEmpty

        image, thumbnail, author, footer = (
            get(i) for i in ("image", "thumbnail", "author", "footer")
        )
        final = discord.Embed(
            title=get("title"),
            description=(get("description") or (str(stdin) if stdin else EmbedEmpty)),
            url=get("url"),
            color=get("color"),
            timestamp=get("timestamp"),
        )

        if image:
            final.set_image(url=image)

        if thumbnail:
            final.set_thumbnail(url=thumbnail)

        if author:
            final.set_author(
                name=author, icon_url=get("author_icon"), url=get("author_url")
            )

        if footer:
            final.set_footer(text=footer, icon_url=get("footer_icon"))

        if args.as_dict:
            return final.to_dict()
        return final


class files(Command):
    """
    Create discord file objects.
    """

    epilog = (
        "Note: file list starts with uploaded files first, "
        "then manually provided urls"
    )
    usage = "%(prog)s [options*] [url*]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "url", nargs="*", help="any url to be uploaded as file"
        )
        cls.argparser.add_argument(
            "-e", "--as-embeds", action="store_true", help="return files as embeds"
        )
        cls.argparser.add_argument(
            "--first", type=int, help="first file to return", metavar="number"
        )
        cls.argparser.add_argument(
            "--last", type=int, help="last file to return", metavar="number"
        )
        cls.argparser.add_argument(
            "--names",
            nargs="*",
            help="set names for manually listed urls",
            metavar="name",
        )

    @staticmethod
    async def create_file(
        name: Optional[str], object: discord.Attachment | str
    ) -> discord.File:
        if type(object) is discord.Attachment:
            return await object.to_file()

        async with aiohttp.ClientSession() as session:
            return discord.File(
                io.BytesIO(await (await session.get(object)).read()),
                filename=name or object.rsplit("/", 1)[-1],
            )

    @staticmethod
    async def create_embed(
        name: Optional[str], object: discord.Attachment | str, cached: bool = False
    ) -> discord.Embed:
        if type(object) is discord.Attachment:
            object = object.proxy_url if cached else object.url

        no_garbage = object.rsplit("?", 1)[0].rsplit("/", 1)[-1]

        if no_garbage.endswith((".png", ".gif", ".jpg", ".jpeg", ".webp")):
            return discord.Embed().set_image(url=object)
        else:
            return discord.Embed(title=no_garbage, url=object)

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> list[discord.File] | list[discord.Embed]:
        attachments = [(None, a) for a in event.message.attachments]
        attachments.extend(zip_longest(args.names or [], args.url or []))

        if args.as_embeds:
            create = cls.create_embed
        else:
            create = cls.create_file

        final = []
        for name, url in attachments[args.first or 0 : args.last or len(attachments)]:
            if not url:
                break

            final.append(await create(name, url))

        return final


class embeds(Command):
    """
    Copy embeds from current message.
    """

    @classmethod
    @has_object("message")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> list[discord.Embed]:
        return event.message.embeds


class message(Command):
    """
    Copy discord message.
    """

    usage = "%(prog)s [message_url]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "message_url",
            nargs="?",
            help="any message url available in scope",
            type=get_message_url,
        )
        cls.argparser.add_argument(
            "-c", "--cached", action="store_true", help="use cached files"
        )
        cls.argparser.add_argument(
            "-e", "--files-as-embeds", action="store_true", help="get files as embeds"
        )

        cls.argparser.add_argument(
            "-C",
            "--no-content",
            action="store_false",
            help="ignore content of message",
            dest="content",
        )
        cls.argparser.add_argument(
            "-E",
            "--no-embeds",
            action="store_false",
            help="ignore message embeds",
            dest="embeds",
        )
        cls.argparser.add_argument(
            "-F",
            "--no-files",
            action="store_false",
            help="ignore message files",
            dest="files",
        )

    @staticmethod
    async def get_from_url(
        message_url: tuple[int, int], event: Event, partial: bool = False
    ) -> tuple[
        discord.TextChannel | discord.DMChannel,
        discord.Message | discord.PartialMessage,
    ]:
        channel_id, message_id = message_url

        if not message_id:
            raise ObjectUnspecifiedError("message")

        channel = (
            (event.client.get_channel(channel_id) or event.client.get_user(channel_id))
            if channel_id
            else event.channel
        )

        if not channel:
            if channel_id:
                raise ObjectNotFoundError(channel_id)
            else:
                raise ObjectUnspecifiedError("channel")

        if partial:
            message = channel.get_partial_message(message_id)
        else:
            message = discord.utils.get(
                event.client.cached_messages, channel=channel, id=message_id
            ) or await try_coro(channel.fetch_message(message_id))

        if not message:
            raise ObjectNotFoundError(message_id)

        return channel, message

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> list[str | discord.File | discord.Embed | None]:
        if args.message_url:
            _, message = await cls.get_from_url(args.message_url, event)
        else:
            message = event.message

        files_list = []
        if args.files:
            for attachment in message.attachments:
                try:
                    assert args.files_as_embeds
                    file = await attachment.to_file(use_cached=args.cached)
                except Exception:
                    file = await files.create_embed(
                        None, attachment, cached=args.cached
                    )
                files_list.append(file)

        return [
            message.system_content if args.content else None,
            *files_list,
            *(message.embeds if args.embeds else []),
        ]


class send(Command):
    """
    Send as separate message. Doesn't support pagination.
    """

    usage = "%(prog)s [options*]"
    epilog = "Requires stdin to work."

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "-c",
            "--channel",
            type=get_discord_id,
            help="channel to send message in",
            metavar="mention/id",
        )
        cls.argparser.add_argument(
            "-D",
            "--direct-message",
            action="store_true",
            help="send message to DMs; has preference over --channel",
        )

        cls.argparser.add_argument(
            "-H", "--webhook", help="send as webhook", action="store_true"
        )
        cls.argparser.add_argument(
            "-m",
            "--mimic",
            type=try_get_discord_id,
            help="mimic a discord object as webhook",
            metavar="type/mention/id",
        )
        cls.argparser.add_argument("-n", "--name", help="webhook name to set")
        cls.argparser.add_argument(
            "-a", "--avatar", help="webhook avatar to set", metavar="image_url"
        )

        cls.argparser.add_argument(
            "-F",
            "--format",
            help="format text as if it was basic bot response",
            action="store_true",
        )
        cls.argparser.add_argument(
            "-U",
            "--unexclusive",
            help="do not suppress sending basic bot response",
            action="store_true",
        )
        cls.argparser.add_argument(
            "-R",
            "--reply",
            action="store",
            const=True,
            nargs="?",
            type=get_message_url,
            help="reply to message",
            metavar="message_url",
        )

        cls.argparser.add_argument(
            "--everyone", help="allow mentioning everyone", action="store_true"
        )
        cls.argparser.add_argument(
            "--reply-mention",
            help="mention user of replied message",
            action="store_true",
        )
        cls.argparser.add_argument(
            "--no-mentions",
            help=(
                "do not mention anything; has preference over --reply-mention "
                "and --everyone"
            ),
            action="store_true",
        )
        cls.argparser.add_argument(
            "-A",
            "--all",
            help="send all pages instead of cutting them down",
            action="store_true",
        )

    @staticmethod
    def get_allowed_mentions(args: Namespace) -> discord.AllowedMentions:
        return discord.AllowedMentions(
            everyone=not args.no_mentions and args.everyone,
            users=not args.no_mentions,
            roles=not args.no_mentions,
            replied_user=not args.no_mentions and args.reply_mention,
        )

    @classmethod
    def send(
        cls,
        event: Event,
        args: Namespace,
        stdin: Result,
        destination: (
            discord.TextChannel
            | discord.DMChannel
            | discord.Member
            | discord.User
            | discord.Webhook
        ),
        content: str,
        *,
        embed: Optional[discord.Embed] = None,
        files: Optional[list[discord.File]] = None,
        **kwargs,
    ) -> Coroutine[Any, Any, discord.Message]:
        if args.format:
            result = event.result
            content = (
                (result.prefix or "```")
                + result.syntax
                + (result.post_prefix or "\n")
                + content
                + (result.suffix or "```")
                if content
                else ""
            ) + (f"\nCommand: `{result.short_content}` — *{event.user}*")
        else:
            content = (
                stdin.prefix + stdin.syntax + stdin.post_prefix + content + stdin.suffix
                if content
                else ""
            )

        return destination.send(
            content,
            embed=embed,
            files=files,
            allowed_mentions=cls.get_allowed_mentions(args),
            **kwargs,
        )

    @classmethod
    async def process_bot(
        cls, event: Event, args: Namespace, stdin: Result
    ) -> AsyncGenerator[discord.Message, None]:
        if args.direct_message:
            channel = event.user
            if not channel:
                raise ObjectUnspecifiedError("user")

        elif args.channel:
            channel = (
                event.guild
                and event.guild.get_channel(args.channel)
                or event.client.get_user(args.channel)
                or await try_coro(event.client.fetch_user(args.channel))
            )
            if not channel:
                raise ObjectNotFoundError(args.channel)

        else:
            channel = event.channel
            if not channel:
                raise ObjectUnspecifiedError("channel")

        reference = args.reply and (
            (await message.get_from_url(args.reply, event))[1]
            if args.reply is not True
            else event.message
        )

        pages = await generate_pages_dictionary(stdin)

        lst: list[tuple[str | None, discord.Embed | None]] = list(
            zip_longest(pages["content"], pages["embeds"])
        )

        for num, (content, embed) in enumerate(lst):
            files = pages["files"] if (num == len(lst) - 1 or not args.all) else None

            yield await cls.send(
                event,
                args,
                stdin,
                channel,
                content,
                embed=embed,
                reference=reference,
                files=files,
            )

            if not args.all:
                break

        if not args.unexclusive:
            event.apply_option("send", False)

    @staticmethod
    async def get_webhook(
        channel: discord.TextChannel | discord.DMChannel, session: aiohttp.ClientSession
    ) -> discord.Webhook:
        return discord.Webhook.from_url(
            await db.get_webhook(channel.id) or "",
            adapter=discord.AsyncWebhookAdapter(session),
        )

    @staticmethod
    def get_webhook_by_url(url: str, session: aiohttp.ClientSession) -> discord.Webhook:
        return discord.Webhook.from_url(
            url, adapter=discord.AsyncWebhookAdapter(session)
        )

    avatar_association: dict[type[Some], Callable[[Some, bool], str]] = {
        discord.User: lambda object, *_: object.avatar_url,
        discord.Member: lambda object, *_: object.avatar_url,
        discord.Guild: lambda object, *_: object.icon_url,
        discord.Emoji: lambda object, *_: object.url,
        discord.TextChannel: lambda object, is_locked: (
            assets.news_textchannel
            if object.is_news()
            else (
                assets.locked_textchannel
                if is_locked
                else assets.nsfw_textchannel if object.is_nsfw() else assets.textchannel
            )
        ),
        discord.VoiceChannel: lambda object, is_locked: (
            assets.locked_voicechannel if is_locked else assets.voicechannel
        ),
        discord.CategoryChannel: lambda object, *a: assets.categorychannel,
    }

    @classmethod
    def get_avatar(cls, object: Any, is_locked: bool) -> str | None:
        return cls.avatar_association.get(type(object), lambda *_: None)(
            object, is_locked
        )

    @classmethod
    async def process_webhook(
        cls, event: Event, args: Namespace, stdin: Result
    ) -> AsyncGenerator[discord.Message, None]:
        client = event.client
        guild = event.guild

        if args.channel:
            channel = guild and guild.get_channel(args.channel)
            if not channel:
                raise ObjectNotFoundError(args.channel)

        else:
            channel = event.channel
            if not channel:
                raise ObjectUnspecifiedError("channel")

        pages = await generate_pages_dictionary(stdin)

        total_embeds = pages["embeds"]
        total_embeds = [
            total_embeds[i : i + 10] for i in range(0, len(total_embeds), 10)
        ]

        lst: list[tuple[str | None, list[discord.Embed] | None]] = list(
            zip_longest(pages["content"], total_embeds)
        )

        webhook = None

        if args.mimic:
            try:
                object = (
                    {
                        "author": event.user,
                        "me": event.user,
                        "guild": guild,
                        "channel": channel,
                        "category": channel.category,
                        "client": guild.me,
                    }.get(str(args.mimic).lower())
                    or guild
                    and guild.get_member(args.mimic)
                    or client.get_user(args.mimic)
                    or client.get_guild(args.mimic)
                    or client.get_channel(args.mimic)
                    or client.get_emoji(args.mimic)
                    or (await client.fetch_user(args.mimic))
                )

            except Exception:
                raise ObjectNotFoundError(args.mimic)

        else:
            object = event.message.author

        if type(object) in (discord.TextChannel, discord.VoiceChannel):
            is_locked = (
                object.overwrites_for(object.guild.default_role).read_messages is False
            )
        else:
            is_locked = False

        options = {
            "username": args.name
            or (
                object.display_name
                if isinstance(object, discord.abc.User)
                else object.name
            ),
            "avatar_url": args.avatar or cls.get_avatar(object, is_locked),
        }

        def send(
            webhook: discord.Webhook,
            content: Optional[str],
            embeds: Optional[list[discord.Embed]],
            files: Optional[list[discord.File]],
        ):
            return cls.send(
                event,
                args,
                stdin,
                webhook,
                content,
                embeds=embeds,
                files=files,
                wait=True,
                **options,
            )

        async with aiohttp.ClientSession() as session:
            for num, (content, embeds) in enumerate(lst):
                files = (
                    pages["files"] if (num == len(lst) - 1 or not args.all) else None
                )

                try:
                    if not webhook:
                        webhook = await cls.get_webhook(channel, session)
                    yield await send(webhook, content, embeds, files)

                except (discord.NotFound, discord.InvalidArgument):
                    webhook_url = (
                        await channel.create_webhook(name="CLI say-hook")
                    ).url

                    await db.append_webhook(channel.id, webhook_url)
                    webhook = cls.get_webhook_by_url(webhook_url, session)

                    yield await send(webhook, content, embeds, files)

                if not args.all:
                    break

        if not args.unexclusive:
            event.apply_option("send", False)

    @classmethod
    @required("stdin")
    async def function(cls, event: Event, args: Namespace, stdin: Result) -> list[str]:
        if any(getattr(args, i) for i in ("mimic", "name", "avatar", "webhook")):
            return [
                f"{getattr(msg.channel, 'id', '')}/{msg.id}"
                async for msg in cls.process_webhook(event, args, stdin)
            ]

        else:
            return [
                f"{msg.channel.id}/{msg.id}"
                async for msg in cls.process_bot(event, args, stdin)
            ]


class read(message):
    """
    Read user input.
    """

    usage = "%(prog)s [options*]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "-c", "--contents", nargs="*", default=None, help="read contents"
        )
        cls.argparser.add_argument(
            "-r", "--reactions", nargs="*", default=None, help="read reactions"
        )
        cls.argparser.add_argument(
            "-m",
            "--message",
            type=get_message_url,
            help="set message to read input from",
            metavar="message_url",
        )
        cls.argparser.add_argument(
            "-t",
            "--timeout",
            type=float,
            default=60,
            help="set timeout in seconds [Default: 60] (0 = no timeout)",
        )
        cls.argparser.add_argument(
            "-u", "--user", type=get_discord_id, help="select other user in guild"
        )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str | None:
        contents = args.contents
        reactions = args.reactions
        if contents is None and reactions is None:
            contents = []

        if args.message:
            channel, message = await cls.get_from_url(args.message, event)
            message_id = message.id

        else:
            channel = event.channel
            message_id = event.message.id

        channel_id = channel.id

        if args.user:
            user = (
                (
                    event.client.get_user(args.user)
                    or await try_coro(event.guild.fetch_user(args.user))
                )
                if channel.type == "private"
                else (
                    event.guild.get_member(args.user)
                    or await try_coro(event.guild.fetch_member(args.user))
                )
            )
            if not user:
                raise ObjectNotFoundError(args.user)

        else:
            user = event.user

        user_id = user.id

        def check_message(inner):
            user = inner.user
            content = inner.object.system_content

            if not user:
                return False
            if inner.channel.id != channel_id:
                return False
            if contents and content not in contents:
                return False
            if content.startswith(inner.prefixes):
                return False
            if user_id and user.id != user_id:
                return False

            return True

        def check_reaction(inner):
            user = inner.user

            if not user:
                return False
            if inner.message.id != message_id:
                return False
            if reactions and str(inner.reaction) not in reactions:
                return False
            if user_id and user.id != user_id:
                return False

            return True

        actions = ([("message", check_message)] if contents is not None else []) + (
            [("raw_reaction_add", check_reaction)] if reactions is not None else []
        )

        inner = await event.client.fetch_event(*actions, timeout=args.timeout or None)

        if inner:
            if inner.name == "message":
                return inner.object.system_content
            else:
                return str(inner.object.emoji)
