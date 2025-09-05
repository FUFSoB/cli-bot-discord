from __future__ import annotations

from models.packages import Command
from models.extra import required
from models.errors import CommandError
from models.utils import run_in_executor, translator
import regex
import googletrans
import pykakasi

from typing import Awaitable, Optional
from models.event import Event
from argparse import Namespace
from parser.wrapper import Result
from googletrans.models import Translated


class replace(Command):
    """
    Replace substrings in string.
    """

    usage = "%(prog)s <substring> <replacement>"
    epilog = "There must be any convertable into string input."

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument(
            "substring", help="any substring containing in input"
        )
        cls.argparser.add_argument("replacement", help="any string")
        cls.argparser.add_argument(
            "-e", "--regex", action="store_true", help="replace using regex"
        )
        cls.argparser.add_argument(
            "-t", "--times", default=0, type=int, help="times to replace"
        )

    @classmethod
    @required("stdin")
    @required("substring")
    @required("replacement")
    async def function(cls, event: Event, args: Namespace, stdin: Result) -> str:
        if args.regex:
            result = regex.sub(args.substring, args.replacement, str(stdin), args.times)
        else:
            result = str(stdin).replace(
                args.substring, args.replacement, args.times or -1
            )

        return result


class translate(Command):
    """
    Translate output.
    """

    usage = "%(prog)s [options*] [text*]"

    more_template = (
        "FROM:        {}  |\n"
        "CONFIDENCE:  {}  |\n"
        "INTO:        {}  ▼\n\n"
        "TRANSLATION:\n{}\n\n"
        "OTHER POSSIBLE TRANSLATIONS:\n{}"
    )

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("text", nargs="*", help="any text")
        cls.argparser.add_argument(
            "--available-languages",
            action="store_true",
            help="get list of available languages and exit",
        )
        cls.argparser.add_argument(
            "-f",
            "--from-language",
            help="pick language to translate from [Default: auto]",
        )
        cls.argparser.add_argument(
            "-i",
            "--into-language",
            help="pick language to translate into [Default: $language]",
        )
        cls.argparser.add_argument(
            "-m",
            "--more",
            action="store_true",
            help="return more information about translation",
        )

    @classmethod
    def setup(cls):
        cls.short_names = list(googletrans.LANGUAGES.keys())
        cls.long_names = list(googletrans.LANGUAGES.values())
        cls.max_len = max(len(x) for x in cls.short_names) + 1

        cls.full_list = "\n".join(
            f"{s.ljust(cls.max_len)} {i}" for s, i in googletrans.LANGUAGES.items()
        )

    @classmethod
    def more(cls, translated: Translated) -> str:
        extra = translated.extra_data

        from_language = googletrans.LANGUAGES[translated.src.lower()].title()
        into_language = googletrans.LANGUAGES[translated.dest.lower()].title()

        max_in_len = max(len(x) for x in (into_language, from_language))

        from_language = from_language.rjust(max_in_len)
        into_language = into_language.rjust(max_in_len)

        confidence = (str(round((extra["confidence"] or 0) * 100, 2)) + "%").rjust(
            max_in_len
        )

        translation = translated.text

        try:
            possible_gen = (
                x[0]
                for x in extra["possible-translations"][0][2]
                if x[0] != translation
            )
            possible = "\n".join(f"{n + 1}. {t}" for n, t in enumerate(possible_gen))
        except Exception:
            possible = ""
        return cls.more_template.format(
            from_language, confidence, into_language, translation, possible
        )

    @classmethod
    @run_in_executor
    def translate(
        cls, text: str, from_language: str, into_language: str, args: Namespace
    ) -> Awaitable[str]:
        try:
            translated = translator.translate(
                text, src=from_language, dest=into_language
            )
        except ValueError as ex:
            raise CommandError(str(ex))

        if not args.more:
            return translated.text
        else:
            return cls.more(translated)

    @classmethod
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        if args.available_languages:
            return cls.full_list

        from_language = args.from_language or "auto"
        into_language = (
            args.into_language or event.get_variable("language") or "english"
        )

        text = stdin and str(stdin) or " ".join(args.text)
        return await cls.translate(text, from_language, into_language, args)


class japanese(Command):
    """
    Convert Japanese text.
    """

    usage = "%(prog)s [options*] <text>"

    converter = pykakasi.kakasi().convert
    keys = {
        "romaji": "hepburn",
        "hiragana": "hira",
        "katakana": "kana",
        "furigana": "hepburn",
        "furigana-hira": "hira",
        "furigana-kata": "kana",
    }

    @classmethod
    def generate_argparser(cls):
        cls.argparser.add_argument("text", nargs="*", help="any japanese text")
        cls.argparser.add_argument(
            "-a",
            "--action",
            choices=(
                "all",
                "romaji",
                "hiragana",
                "katakana",
                "furigana",
                "furigana-hira",
                "furigana-kata",
            ),
            default="romaji",
            help="choose conversion type [Default: romaji]",
        )

    @classmethod
    @required("stdin", "text")
    async def function(
        cls, event: Event, args: Namespace, stdin: Optional[Result]
    ) -> str:
        text = args.text or str(stdin)
        action = args.action
        converted = cls.converter(text)
        if action == "all":
            return "\n".join(
                f"{d['orig']}: {d['hepburn']} | {d['hira']} | {d['kana']}"
                for d in converted
            )
        else:
            key = cls.keys[action]
            if "furigana" in action:
                result = (f"{d['orig']}[{d[key]}]" for d in converted)
            else:
                result = (d[key] for d in converted)
            return " ".join(result)
