# Discord CLI Bot

This is a complex CLI-like bot for Discord that allows users to interact with their Discord server through a command-line interface. The bot is designed to be highly customizable and extensible, making it easy to add new features and commands as needed. The bot was developed during 2020~2021, using Discord.py 1.7.3 and older Discord API versions.

The bot was using a MongoDB database for storing user data and command configurations, but for the sake of simplicity and ease of use, it has been switched to an in-memory storage system. This means that all data will be lost when the bot is restarted, but it simplifies the setup process and eliminates the need for a separate database server.

The bot is for exploration purposes only and may not be suitable for production use.

## Features

- **Command Prompt**: A built-in command prompt for executing commands using Bash-like syntax.
- **Custom Commands and Scripts**: Easily create and manage custom commands and scripts for your server using Bash-like syntax.
- **Imaginary Filesystem**: Interact with a virtual filesystem, allowing users to navigate and manipulate files and directories as if they were in a real terminal.
- **Like any other moderation bot**: Manage server roles and permissions, respond to user input, and integrate with other services.

### Bash-like Syntax

See how it works and looks with examples in [scripts directory](scripts/), with [coin command](scripts/coin.command) being the most basic example.

## How to run

1. Clone the repository:
   ```bash
   git clone https://github.com/FUFSoB/cli-bot-discord.git
   cd cli-bot-discord
   ```

2. Copy configuration files:
   ```bash
   cp config.json.example config.json
   ```

   Edit the `config.json` file to include your Discord bot token and any other required configuration.

3. Install the required dependencies and run the bot:
   ```bash
   ./start.sh
   ```

## Configuration

```jsonc
{
    "bots": {
        "NAME": {
            "token": "BOT_TOKEN", // Your Discord bot token
            "bot": true,  // Whether the bot is a bot account
            "real": true, // If false, will not store messages in memory, will appear offline
            "intents": "all" // The intents the bot should use
        }
    },
    "root": [
        "USER_ID" // Your Discord user ID
    ],
    "mongo": {
        "username": "USERNAME",
        "password": "PASSWORD"
    },
    "lastfm": {
        "key": "LASTFM_KEY",
        "secret": "LASTFM_SECRET"
    },
    "other": {},
    "other_accounts": {}
}
