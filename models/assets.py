import random

__all__ = ("assets",)


class Assets:
    def __init__(self):
        attach = "https://cdn.discordapp.com/attachments/{CHANNEL_ID}/"
        emoji = "https://cdn.discordapp.com/emojis/"
        self.dict = {
            "textchannel": attach + "{MESSAGE_ID}/textchannel.png",
            "locked_textchannel": attach + "{MESSAGE_ID}/locked_textchannel.png",
            "nsfw_textchannel": attach + "{MESSAGE_ID}/nsfw_textchannel.png",
            "news_textchannel": attach + "{MESSAGE_ID}/news_textchannel.png",
            "voicechannel": attach + "{MESSAGE_ID}/voicechannel.png",
            "locked_voicechannel": attach + "{MESSAGE_ID}/locked_voicechannel.png",
            "categorychannel": attach + "{MESSAGE_ID}/categorychannel.png",
            "no_image": "https://cdn.discordapp.com/embed/avatars/0.png",
            "online": emoji + "{EMOJI_ID}.png",
            "idle": emoji + "{EMOJI_ID}.png",
            "dnd": emoji + "{EMOJI_ID}.png",
            "offline": emoji + "{EMOJI_ID}.png",
            "streaming": emoji + "{EMOJI_ID}.png",
            "bot": emoji + "{EMOJI_ID}.png",
            "bug_hunter": emoji + "{EMOJI_ID}.png",
            "partner": emoji + "{EMOJI_ID}.png",
            "nitro": emoji + "{EMOJI_ID}.png",
            "early_supporter": emoji + "{EMOJI_ID}.png",
            "verified": emoji + "{EMOJI_ID}.png",
            "staff": emoji + "{EMOJI_ID}.png",
            "hypesquad": emoji + "{EMOJI_ID}.png",
            "hypesquad_bravery": emoji + "{EMOJI_ID}.png",
            "hypesquad_balance": emoji + "{EMOJI_ID}.png",
            "hypesquad_brilliance": emoji + "{EMOJI_ID}.png",
            "owner": emoji + "{EMOJI_ID}.png",
            "booster_level1": emoji + "{EMOJI_ID}.png",
            "booster_level2": emoji + "{EMOJI_ID}.png",
            "booster_level3": emoji + "{EMOJI_ID}.png",
            "booster_level4": emoji + "{EMOJI_ID}.png",
        }
        self.list = list(self.dict)

    def __getitem__(self, item: str) -> str:
        return self.dict[item]

    def __getattr__(self, attr: str) -> str:
        try:
            return self.dict[attr]
        except Exception:
            raise AttributeError

    def random(self) -> str:
        return random.choice(list(self.dict.values()))


assets = Assets()
