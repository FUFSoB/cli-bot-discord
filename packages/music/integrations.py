from __future__ import annotations

from models.packages import Command
from ._lastfm import auth_with_token
from models.database import db

from typing import Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result


class lastfm(Command):
    """
    Auth to last.fm
    """

    usage = "lastfm [options*] [url]"
    epilog = "Note: scrobbles are not 100% correct"

    redirect = "http://127.0.0.1"
    auth = "https://www.last.fm/api/auth?api_key={}&cb=" + redirect

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("url", help="resulting url with auth token")
        cls.argparser.add_argument(
            "--remove", action="store_true", help="remove auth token from bot"
        )

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        config = event.client.config["lastfm"]
        if args.remove:
            await db.remove_auth_keys(event.user.id, "lastfm")
            return "LastFM auth successfully removed"

        if not args.url:
            return (
                "To complete authorization, please follow auth link:\n    "
                + cls.auth.format(config["key"])
                + "\n\n"
                "After authing please copy and paste resulting url as argument"
                " to `lastfm` command."
            )

        if not args.url.startswith(cls.redirect):
            return "Invalid auth url"

        token = args.url.rsplit("token=", 1)[-1]
        lastfm_client = await auth_with_token(config, token)
        await db.set_auth_keys(
            event.user.id, "lastfm", session_key=lastfm_client.session_key
        )
        return f"LastFM successfully authed as {lastfm_client.username}"
