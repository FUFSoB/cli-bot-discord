from __future__ import annotations

import discord
from models.errors import ObjectNotFoundError
from models.extra import has_object
from models.utils import get_discord_id, try_coro
from models.packages import Command

from typing import Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result


class Mixin:
    @classmethod
    async def get_member(cls, event: Event, id: int) -> discord.Member:
        guild = event.guild
        member = guild.get_member(id) or await try_coro(guild.fetch_member(id))
        if not member:
            raise ObjectNotFoundError(id)
        return member

    @classmethod
    async def get_user(cls, event: Event, id: int) -> discord.User:
        client = event.client
        user = client.get_user(id) or await try_coro(client.fetch_user(id))
        if not user:
            raise ObjectNotFoundError(id)
        return user


class kick(Command, Mixin):
    """
    Kick member from guild.
    """

    usage = "%(prog)s <user> [reason*]"
    group = "moderator"

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("user", type=get_discord_id, help="any user")
        cls.argparser.add_argument("reason", nargs="*", help="reason for audit")

    @classmethod
    @has_object("guild")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        member = await cls.get_member(event, args.user)
        await member.kick(reason=" ".join(args.reason))
        return f"User kicked: {member} ({member.id})"


class ban(kick):
    """
    Ban user in guild.
    """

    usage = "%(prog)s [options*] <user> [reason*]"

    @classmethod
    def generate_argparser(cls):
        super().generate_argparser()
        cls.argparser.add_argument(
            "-d",
            "--delete-message-days",
            nargs="?",
            action="store",
            const=1,
            default=0,
            type=int,
            choices=range(8),
            help="delete messages from banned user",
        )

    @classmethod
    @has_object("guild")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        user = await cls.get_user(event, args.user)
        await event.guild.ban(
            user,
            reason=" ".join(args.reason),
            delete_message_days=args.delete_message_days,
        )
        return f"User banned: {user} ({user.id})"


class unban(kick):
    """
    Unban user in guild.
    """

    @classmethod
    @has_object("guild")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        user = await cls.get_user(event, args.user)
        await event.guild.unban(user, reason=" ".join(args.reason))
        return f"User unbanned: {user} ({user.id})"
