from models.packages import Package

from models.bot import Client
from models.event import Event


class template(Package):
    """
    Description.
    """

    @staticmethod
    async def on_message(client: Client, event: Event):
        pass

    version = "0.0"
    commands = []
