# UploadBot

A private Telegram file-receiver bot. Send files to the bot and it saves them in the project's files/ directory.

## Features

- Accepts documents of any file type, photos, videos, animations, audio, voice messages, video notes, stickers, and live photos.
- Uses Telegram's Local Bot API Server for large-file downloads.
- Saves files directly to files/, preserving the supplied filename when possible.
- Sanitizes filenames and prevents existing files from being overwritten.
- Restricts every command and file handler to one configured Telegram user ID, in private chats only.
- Streams downloads to disk; file contents are not loaded into memory as one large byte array.
- Includes /start, /help, and /status commands.

## Telegram file-size limits

The default hosted Telegram Bot API currently allows bots to download files up to **20 MB** with getFile. Telegram's Local Bot API Server removes that download-size limit. The Local Bot API Server documents uploads up to 2000 MB, but that upload figure applies to files sent by the bot.

This project uses the Local Bot API Server by default. There is no application-level file-size cap, but Telegram's own client/upload rules, available disk space, network capacity, and filesystem limits still apply. No bot can guarantee files of literally unlimited size.

References:
- [Telegram Bot Features — Local Bot API limits](https://core.telegram.org/bots/features)
- [Telegram Bot API — getFile](https://core.telegram.org/bots/api#getfile)
- [Local Bot API Server Docker image documentation](https://github.com/aiogram/telegram-bot-api)

## Requirements

- Docker Engine and Docker Compose plugin.
- A Telegram bot token from [@BotFather](https://t.me/BotFather).
- Your numeric Telegram user ID.
- Telegram API ID and API hash from [my.telegram.org](https://my.telegram.org) for the Local Bot API Server.

## Setup

1. Create a bot with @BotFather and copy its token.
2. Get your numeric user ID from a Telegram ID bot. Do not use your username; usernames can change.
3. Sign in at [my.telegram.org](https://my.telegram.org), open **API development tools**, and copy your api_id and api_hash.
4. Create the environment file:

   ~~~bash
   cp .env.example .env
   ~~~

5. Fill in BOT_TOKEN, OWNER_ID, TELEGRAM_API_ID, and TELEGRAM_API_HASH in .env.

### Switching an existing bot to the Local Bot API Server

If this bot token has already been used with Telegram's hosted Bot API, call logOut once before starting it against the local server:

~~~bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/logOut"
~~~

Replace <YOUR_BOT_TOKEN> with the real token. Do not run this step repeatedly. A bot that has never used the hosted Bot API can start directly against the local server.

6. Start the bot and Local Bot API Server:

   ~~~bash
   docker compose up -d --build
   ~~~

7. Follow the bot logs:

   ~~~bash
   docker compose logs -f uploadbot
   ~~~

8. Open the bot in Telegram from the account whose ID is configured in OWNER_ID, then send /start.

## Where files are stored

Every accepted attachment is copied into the repository's files/ directory on the host. For example:

~~~text
uploadbot/
├── files/
│   ├── archive.zip
│   ├── photo_12345.jpg
│   └── report.pdf
├── main.py
├── settings.py
└── storage.py
~~~

If a file with the same name already exists, UploadBot adds a timestamp and unique suffix instead of replacing it.

The Local Bot API Server uses a separate persistent Docker volume as its working directory. The bot container mounts that same volume read-only to access the downloaded file and then copies it into files/.

## Owner-only access

Set OWNER_ID to your numeric Telegram user ID. The bot registers handlers only for that user in private chats. Messages from all other users and all group chats are ignored.

The bot does not use a username allowlist, so changing a Telegram username will not affect access.

## Run without Docker (small files only)

You can use Telegram's hosted Bot API without the Local Bot API Server:

1. Install Python 3.12 or newer.
2. Install dependencies:

   ~~~bash
   pip install -r requirements.txt
   ~~~

3. Set BOT_API_MODE=cloud in .env.
4. Run:

   ~~~bash
   python main.py
   ~~~

In this mode Telegram's hosted getFile download limit applies (currently 20 MB). Use Docker Compose and local mode for large files.

## Useful commands

~~~bash
# View logs
docker compose logs -f uploadbot

# Restart
docker compose restart uploadbot

# Stop containers (saved files remain in files/)
docker compose down

# Run unit tests locally
python -m unittest discover -s tests -v
~~~

Do not use docker compose down -v unless you intentionally want to delete the Local Bot API Server's persistent data volume. Files already copied to files/ are kept separately.

## Security notes

- Never commit .env; it contains the bot token and Telegram API credentials.
- Keep the bot token and API hash private.
- The bot accepts files only from the configured owner ID and only in private chats.
- Make regular backups of files/. The bot does not automatically upload files to another storage provider.
