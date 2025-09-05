#!/usr/local/bin/python3.9
import json
import asyncio
import importlib
import discord
from models.config import Config
from models.database import db
from models.bot import Client, clients

allowed_mentions = discord.AllowedMentions(everyone=False)

loop = asyncio.get_event_loop()


async def start():
    config = Config()

    with open("./config.json", "r") as config_file:
        loaded_configuration: dict = json.load(config_file)

        config["root"] = loaded_configuration["root"]
        config["mongo"] = loaded_configuration["mongo"]
        config["lastfm"] = loaded_configuration["lastfm"]

        importlib.import_module("packages")

        for name, data in loaded_configuration["bots"].items():
            if data["real"]:
                new = Client(
                    name, data, config,
                    allowed_mentions=allowed_mentions,
                    max_messages=1000,
                    status=discord.Status.online
                )
            else:
                new = Client(
                    name, data, config,
                    max_messages=None,
                    status=discord.Status.offline
                )

            clients.append(new)

    db.setup(config)


if __name__ == "__main__":
    loop.create_task(start())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print("")
