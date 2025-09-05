from __future__ import annotations

import functools
from models.errors import ObjectNotFoundError
import discord
from models.event import Event
from models.utils import get_discord_id
import parse


templates = {}


def template(cls: type) -> type:
    templates.update({cls.__name__: cls})
    cls.match = parse.compile(cls.file.strip()).parse
    return cls


def default_values(*names: str, allow_none=False):
    def decorator(func):
        @functools.wraps(func)
        def inner(cls, **kwargs):
            for key, value in kwargs.items():
                if value is not None:
                    continue
                if key in names:
                    kwargs[key] = cls.defaults[key]
                    continue
                if not allow_none:
                    raise ValueError(f"Value {key!r} is required.")

            return func(cls, **kwargs)

        return inner

    return decorator


# def defaults(cls: type, kwargs: dict[str], *names: str) -> dict[str]:
#     for name in names:
#         kwargs[name] = kwargs[name] or cls.defaults[name]
#     return kwargs


# def find_template(string: str) -> tuple[type, dict[str]]:
#     for template in templates.values():
#         if (match := template.match(string)):
#             return template, match.named


async def convert_channel(content: str, event: Event) -> int:
    id = get_discord_id(content)
    channel = event.guild.get_channel(id)
    if not channel or type(channel) is not discord.TextChannel:
        raise ObjectNotFoundError(id)
    return id


def quotes(s: str, _: Event) -> str:
    return s.replace('"', '\\"')


Content = str
FilePath = str


@template
class members:
    file = """#!/bin/event -n member_join -n member_remove --store

if [ _event == "member_join" ]; then
    send -c {welcome_channel} <<< "{welcome_message}"
else
    send -c {leave_channel} <<< "{leave_message}"
fi
"""
    destination = "guild"
    defaults = dict(
        welcome_channel=None,
        welcome_message="Welcome, $(< /current/user/mention)!",
        leave_channel=None,
        leave_message="Bye, **$(< /current/user/.str)**!",
    )

    converters = dict(
        welcome_channel=convert_channel,
        welcome_message=quotes,
        leave_channel=convert_channel,
        leave_message=quotes,
    )

    @classmethod
    @default_values("welcome_message", "leave_message")
    def finalize(cls, **kwargs) -> tuple[Content, FilePath]:
        return (
            cls.file.format(**kwargs),
            f"~{cls.destination}/.autostart/" + cls.__name__ + ".event",
        )


@template
class store_deleted:
    file = """#!/bin/event -n message_delete --store -b

name="{webhook_name}"
message -c | send -H --no-mentions --name "$name" --channel {channel}
"""
    destination = "guild"
    defaults = dict(
        webhook_name="$(< /current/user/.str) in #$(< /current/channel/.str)",
        channel=None,
    )

    converters = dict(webhook_name=quotes, channel=convert_channel)

    @classmethod
    @default_values("webhook_name")
    def finalize(cls, **kwargs) -> tuple[Content, FilePath]:
        return (
            cls.file.format(**kwargs),
            f"~{cls.destination}/.autostart/" + cls.__name__ + ".event",
        )


@template
class info_command:
    file = """#!/bin/argparse --store
! {name}
@ {description}
|||

send {send_options} << EOF
{text}
EOF
"""
    destination = "guild"
    defaults = dict(name=None, description="", text=None, send_options="-F")

    converters = dict(
        name=lambda s, _: s.lower().replace(" ", "_").replace("\n", "_"),
        description=lambda s, _: s.replace("\n", " "),
        text=lambda s, _: s.replace("EOF\n", "eof\n"),
        send_options=lambda s, _: s.replace("\n", " "),
    )

    @classmethod
    @default_values("description", "send_options")
    def finalize(cls, **kwargs) -> tuple[Content, FilePath]:
        return (
            cls.file.format(**kwargs),
            f"~{cls.destination}/.autostart/" + kwargs["name"] + ".command",
        )
