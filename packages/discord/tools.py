from __future__ import annotations

from models.packages import Command
from models.errors import ObjectNotFoundError
from models.utils import (
    get_discord_id,
    try_get_discord_id,
    try_get_discord_obj_or_date,
    get_discord_repr,
    try_coro,
    get_discord_str,
    get_message_url,
    try_get_message_url,
)
from models.extra import required, has_group, has_object
import discord
from discord.utils import get
from .message import message as message_command

from typing import Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result

if False:
    from models.typings import GetType, UserType


class dism(Command):
    """
    Wrap ID into discord mention.
    """

    usage = "%(prog)s [options*] <id>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "id", type=try_get_discord_id, help="any available id"
        )
        cls.argparser.add_argument(
            "-c",
            "--channel",
            action="store_const",
            dest="type",
            const="channel",
            help="format as channel mention",
        )
        cls.argparser.add_argument(
            "-e",
            "--emoji",
            action="store_const",
            dest="type",
            const="emoji",
            help="format as emoji mention (gif will be static)",
        )
        cls.argparser.add_argument(
            "-E",
            "--animated-emoji",
            action="store_const",
            dest="type",
            const="animated-emoji",
            help="format as animated emoji mention (gif only)",
        )
        cls.argparser.add_argument(
            "-r",
            "--role",
            action="store_const",
            dest="type",
            const="role",
            help="format as role mention",
        )
        cls.argparser.add_argument(
            "-u",
            "--user",
            action="store_const",
            dest="type",
            const="user",
            help="format as user mention",
        )
        cls.argparser.add_argument(
            "-R", "--reversed", action="store_true", help="return id from mention"
        )
        cls.argparser.add_argument(
            "-n",
            "--name",
            default="emoji",
            help=(
                "set name for emoji (visible only via mobile notifications, "
                "code blocks and escapes)"
            ),
        )

    @staticmethod
    async def get_mention(id: int, event: Event) -> str | None:
        object = await event.client.fetch_object(id, event)
        assert type(object) is not discord.Object

        return get_discord_repr(object)

    @classmethod
    @required("id")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str | int | None:
        if args.reversed:
            return try_get_discord_id(args.id)

        if not args.type:
            try:
                return await cls.get_mention(args.id, event)
            except Exception:
                raise ObjectNotFoundError(args.id)
        else:
            mention = {
                "channel": "<#{id}>",
                "emoji": "<:{name}:{id}>",
                "animated-emoji": "<a:{name}:{id}>",
                "role": "<@&{id}>",
                "user": "<@{id}>",
            }[args.type].format(id=args.id, name=args.name)

        return mention


class purge(Command):
    """
    Purge number of messages.
    """

    usage = "%(prog)s [options*] [amount]"
    group = "moderator"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "amount",
            nargs="?",
            default=100,
            type=int,
            help="amount of messages to delete [Default: 100] (0 = no limit)",
        )
        cls.argparser.add_argument(
            "-c",
            "--channel",
            type=get_discord_id,
            help="pick channel to delete messages from",
        )
        cls.argparser.add_argument(
            "-b",
            "--before",
            type=try_get_discord_obj_or_date,
            help="delete messages written before date or id",
        )
        cls.argparser.add_argument(
            "-a",
            "--after",
            type=try_get_discord_obj_or_date,
            help="delete messages written after date or id",
        )

    @classmethod
    @has_object("guild")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        channel = (
            args.channel and event.guild.get_channel(args.channel) or event.channel
        )

        if channel == event.channel:
            await try_coro(event.message.delete())

        messages = await channel.purge(
            limit=args.amount or None, before=args.before, after=args.after
        )

        return f"Messages deleted: {len(messages)}"


class role(Command):
    """
    Remove or add roles.
    """

    usage = "%(prog)s [options*] <role+>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "role",
            nargs="+",
            type=try_get_discord_id,
            help="any role id, name or mention",
        )
        cls.argparser.add_argument(
            "-u",
            "--user",
            type=get_discord_id,
            help="pick user to edit their roles",
            metavar="USER",
        )
        cls.argparser.add_argument("--all", action="store_true", help="get all roles")
        cls.argparser.add_argument(
            "-g",
            "--give",
            dest="action",
            action="store_const",
            const="give",
            help="explicitly give roles",
        )
        cls.argparser.add_argument(
            "-r",
            "--remove",
            dest="action",
            action="store_const",
            const="remove",
            help="explicitly remove roles",
        )

    @classmethod
    @has_group("admin")
    async def admin_action(
        cls, event: Event, args: Namespace, user: discord.Member
    ) -> str:
        guild = event.guild
        maximum_available: int = (
            guild.me.top_role.position if guild.owner.id != guild.me.id else 10000
        )
        all_roles: list[discord.Role] = [
            role
            for role in event.guild.roles[1:]
            if not role.managed and role.position < maximum_available
        ]

        return await cls.action(event, args, user, True, all_roles)

    @classmethod
    async def public_action(cls, event: Event, args: Namespace) -> str:
        all_roles: list[discord.Role] = [
            event.guild.get_role(r)
            for r in event.guild_state.config.get("public_roles", [])
        ]
        return await cls.action(event, args, event.user, False, all_roles)

    @classmethod
    async def action(
        cls,
        event: Event,
        args: Namespace,
        user: discord.Member,
        admin: bool,
        all_roles: list[discord.Role],
    ) -> str:
        guild = event.guild

        user_roles: list[discord.Role] = user.roles[1:]
        prev_user_roles = user_roles.copy()

        if args.all:
            roles = all_roles
        else:
            roles: list[discord.Role] = [
                (
                    guild.get_role(role)
                    if type(role) is int
                    else get(guild.roles, name=role)
                )
                for role in args.role
            ]

        if args.action == "give":
            cls.give_roles(roles, user_roles, prev_user_roles, all_roles)
        elif args.action == "remove":
            cls.remove_roles(roles, user_roles, all_roles)
        else:
            cls.toggle_roles(roles, user_roles, prev_user_roles, all_roles)

        await user.edit(roles=user_roles)

        set_current = set(user_roles)
        set_previous = set(prev_user_roles)

        added = "\n".join(
            f"\tRole added: {role} ({role.id})" for role in (set_current - set_previous)
        )
        removed = "\n".join(
            f"\tRole removed: {role} ({role.id})"
            for role in (set_previous - set_current)
        )

        return "\n".join((f"User {user}:", added, removed))

    @classmethod
    def give_roles(
        cls,
        roles: list[discord.Role],
        user_roles: list[discord.Role],
        prev_user_roles: list[discord.Role],
        all_roles: list[discord.Role],
    ):
        for role in roles:
            if role in prev_user_roles:
                continue
            if role in all_roles:
                user_roles.append(role)

    @classmethod
    def remove_roles(
        cls,
        roles: list[discord.Role],
        user_roles: list[discord.Role],
        all_roles: list[discord.Role],
    ):
        for role in roles:
            if role in all_roles:
                try:
                    user_roles.remove(role)
                except Exception:
                    pass

    @classmethod
    def toggle_roles(
        cls,
        roles: list[discord.Role],
        user_roles: list[discord.Role],
        prev_user_roles: list[discord.Role],
        all_roles: list[discord.Role],
    ):
        for role in roles:
            if role in all_roles:
                if role in prev_user_roles:
                    try:
                        user_roles.remove(role)
                    except Exception:
                        pass
                elif role not in user_roles:
                    user_roles.append(role)

    @classmethod
    @has_object("guild")
    @required("role")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        if args.user:
            user = event.guild.get_member(args.user) or await try_coro(
                event.guild.fetch_member(args.user)
            )
            if not user:
                raise ObjectNotFoundError(args.user)

            return await cls.admin_action(event, args, user)

        else:
            return await cls.public_action(event, args)


class reaction(Command):
    """
    Remove or add reactions.
    """

    usage = "%(prog)s [options*] <emoji+>"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("emoji", nargs="+", help="any emoji")
        cls.argparser.add_argument(
            "-u",
            "--user",
            type=get_discord_id,
            help="pick user to remove their reactions",
            metavar="USER",
        )
        cls.argparser.add_argument(
            "-m",
            "--message",
            type=get_message_url,
            help="pick message to manipulate with its reactions",
            metavar="MESSAGE_URL",
        )
        cls.argparser.add_argument(
            "--all", action="store_true", help="get all guild emojis"
        )
        cls.argparser.add_argument(
            "-a",
            "--add",
            dest="action",
            action="store_const",
            const="add",
            help="explicitly add reactions",
        )
        cls.argparser.add_argument(
            "-c",
            "--clear",
            dest="action",
            action="store_const",
            const="clear",
            help="explicitly clear reactions",
        )
        cls.argparser.add_argument(
            "-r",
            "--remove",
            dest="action",
            action="store_const",
            const="remove",
            help="explicitly remove reactions",
        )

    @classmethod
    @has_group("moderator")
    @has_object("message")
    async def moderator_action(
        cls,
        event: Event,
        args: Namespace,
        reactions: list[str | discord.Emoji],
        message: discord.Message,
        user: Optional[UserType],
    ) -> str:
        final = [f"Message {message.id}:"]
        if user:
            for reaction in reactions:
                await message.remove_reaction(reaction, user)
                final.append(f"\tReaction removed: {reaction} by {user}")
        else:
            if args.all:
                await message.clear_reactions()
                final.append("\tReactions cleared")

            else:
                for reaction in reactions:
                    await message.clear_reaction(reaction)
                    final.append(f"\tReaction cleared: {reaction}")

        return "\n".join(final)

    @classmethod
    @has_object("message")
    async def public_action(
        cls,
        event: Event,
        args: Namespace,
        reactions: list[str | discord.Emoji],
        message: discord.Message,
        user: Optional[UserType],
    ) -> str:
        action = args.action
        final = [f"Message {message.id}:"]
        client_user = event.guild and event.guild.me or event.client.user

        if action == "remove" or user:
            user = user or client_user
            for reaction in reactions:
                await message.remove_reaction(reaction, user)
                final.append(f"\tReaction removed: {reaction} by {user}")

        elif action == "add":
            for reaction in reactions:
                await message.add_reaction(reaction)
                final.append(f"\tReaction added: {reaction}")

        else:
            prev_reactions: dict[str, bool] = {str(r): r.me for r in message.reactions}
            user = client_user

            for reaction in reactions:
                if prev_reactions.get(str(reaction)):
                    await message.remove_reaction(reaction, user)
                    final.append(f"\tReaction removed: {reaction} by {user}")
                else:
                    await message.add_reaction(reaction)
                    final.append(f"\tReaction added: {reaction}")

        return "\n".join(final)

    @classmethod
    @required("emoji")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        guild = event.guild
        if args.message:
            channel_id, message_id = args.message

            if not channel_id:
                channel = event.channel
            else:
                channel = guild.get_channel(channel_id)
                if not channel:
                    raise ObjectNotFoundError(channel_id)

            message = get(
                event.client.cached_messages, id=message_id
            ) or await try_coro(channel.fetch_message(message_id))
            if not message:
                raise ObjectNotFoundError(message_id)
        else:
            message = event.message

        if args.user:
            user = guild.get_member(args.user) or await try_coro(
                guild.fetch_member(args.user)
            )
            if not user:
                raise ObjectNotFoundError(args.user)
        else:
            user = None

        if args.all:
            reactions = guild.emojis
        else:
            reactions = []
            for emoji in args.emoji:
                try:
                    emoji = int(emoji)
                except ValueError:
                    reactions.append(emoji)
                else:
                    reactions.append(event.client.get_emoji(emoji))

        if user not in (None, event.user) or args.action == "clear":
            return await cls.moderator_action(event, args, reactions, message, user)
        else:
            return await cls.public_action(event, args, reactions, message, user)


class delete(Command):
    """
    Delete message or any object in guild.
    """

    usage = "%(prog)s [options*] [object]"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "object", type=get_message_url, help="any discord object in guild"
        )
        cls.argparser.add_argument("-R", "--reason", help="set reason")

    @classmethod
    @has_group("admin")
    def admin_check(cls, event: Event) -> None:
        pass

    @classmethod
    async def get_guild_object(cls, event: Event, args: Namespace) -> GetType:
        object_channel_id, object_id = args.object

        if object_channel_id:
            _, object = await message_command.get_from_url(args.object, event)
        else:
            object = await event.client.fetch_object(object_id, event, event.guild)
            if type(object) is discord.Object:
                raise ObjectNotFoundError(object_id)

        is_message_type = type(object) is discord.Message
        author_is_client_or_user = is_message_type and object.author in (
            getattr(event.guild, "me", event.client.user),
            event.user,
        )
        author_is_webhook = is_message_type and object.author.discriminator == "0000"

        if author_is_webhook:
            if not object.guild.me.guild_permissions.manage_messages:
                webhook = await event.client.fetch_webhook(object.author.id)
                await webhook.delete_message(object.id)
                return object
        elif not author_is_client_or_user:
            cls.admin_check(event)

        await (
            object.delete(reason=args.reason)
            if not is_message_type
            else object.delete()
        )

        return object

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        if args.object:
            object = await cls.get_guild_object(event, args)
        else:
            object = event.message
            await object.delete()

        return (
            f"Deleted object: {get_discord_str(object)} "
            f"({type(object).__name__.lower()}, {object.id})"
            + (f" [{args.reason}]" if args.reason else "")
        )


class edit(delete):
    """
    Edit objects.
    """

    usage = "%(prog)s <object>"
    epilog = "There must be dictionary in stdin."

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "object", type=try_get_message_url, help="object to edit"
        )

    @classmethod
    @required("object")
    @required("stdin")
    async def function(cls, event: Event, args: Namespace, stdin: Result) -> None:
        object_channel_id, object_id = args.object
        if object_channel_id:
            _, object = await message_command.get_from_url(args.object, event)
        elif type(object_id) is int:
            object = await event.client.fetch_object(object_id, event, event.guild)
        else:
            object = {
                "author": event.user,
                "me": event.user,
                "guild": event.guild,
                "channel": event.channel,
                "category": event.channel.category,
                "message": event.message,
            }[object_id.lower()]

        if type(object) is discord.Message and object.author.discriminator == "0000":
            webhook = await event.client.fetch_webhook(object.author.id)

            def edit(**fields):
                return webhook.edit_message(object.id, **fields)

        else:
            cls.admin_check(event)
            edit = object.edit

        await edit(**next(stdin.filter(dict)))
