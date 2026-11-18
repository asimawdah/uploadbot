from __future__ import annotations

import asyncio
import logging
import mimetypes
import shutil
from pathlib import Path
from typing import Any

from telegram import Message, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from settings import Settings, load_settings
from storage import copy_local_file, create_temp_path, finalize_temp_file


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("uploadbot")


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def get_message_file(message: Message) -> tuple[Any, str] | None:
    """Return the first supported Telegram file attachment and its filename."""
    candidates = (
        ("document", ".bin"),
        ("video", ".mp4"),
        ("animation", ".mp4"),
        ("audio", ".audio"),
        ("voice", ".ogg"),
        ("video_note", ".mp4"),
        ("sticker", ".webp"),
    )

    for attribute, fallback_extension in candidates:
        media = getattr(message, attribute, None)
        if media is None:
            continue

        filename = getattr(media, "file_name", None)
        if not filename:
            mime_type = getattr(media, "mime_type", None)
            extension = mimetypes.guess_extension(mime_type or "") or fallback_extension

            if attribute == "sticker":
                if getattr(media, "is_video", False):
                    extension = ".webm"
                elif getattr(media, "is_animated", False):
                    extension = ".tgs"
                else:
                    extension = ".webp"

            file_unique_id = getattr(media, "file_unique_id", "telegram-file")
            filename = f"{attribute}_{file_unique_id}{extension}"

        return media, filename

    if message.photo:
        media = message.photo[-1]
        return media, f"photo_{media.file_unique_id}.jpg"

    return None


async def start_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    await update.effective_message.reply_text(
        "UploadBot is ready.\n\n"
        "Send me a document, photo, video, audio, voice message, animation, "
        "video note, or sticker. I will save the file in the project's files/ "
        "directory.\n\n"
        "Only the configured owner can use this bot."
    )


async def help_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    await update.effective_message.reply_text(
        "Send a file or supported media attachment in this private chat. "
        "The bot saves it to files/ without replacing an existing file.\n\n"
        "Use /status to check storage information."
    )


async def status_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    settings: Settings = context.application.bot_data["settings"]
    files = [
        path for path in settings.files_dir.iterdir()
        if path.is_file() and not path.name.startswith(".uploadbot-")
    ]
    total_bytes = sum(path.stat().st_size for path in files)
    disk = await asyncio.to_thread(shutil.disk_usage, settings.files_dir)

    await update.effective_message.reply_text(
        f"Mode: {'Local Bot API (large files)' if settings.local_mode else 'Official Telegram Bot API'}\n"
        f"Saved files: {len(files)}\n"
        f"Total saved size: {human_size(total_bytes)}\n"
        f"Free disk space: {human_size(disk.free)}\n"
        f"Storage directory: {settings.files_dir}"
    )


async def save_attachment(
    media: Any,
    original_name: str,
    context: ContextTypes.DEFAULT_TYPE,
    settings: Settings,
) -> Path:
    telegram_file = await context.bot.get_file(
        media.file_id,
        read_timeout=120,
        connect_timeout=30,
        pool_timeout=30,
    )

    if settings.local_mode:
        # In local mode getFile returns an absolute path on the Bot API server.
        # docker-compose mounts that same volume into this container.
        source_path = Path(telegram_file.file_path or "")
        return await asyncio.to_thread(
            copy_local_file,
            source_path,
            settings.files_dir,
            original_name,
        )

    # The official hosted Bot API currently limits getFile downloads to 20 MB.
    temp_path = create_temp_path(settings.files_dir)
    try:
        await telegram_file.download_to_drive(
            custom_path=temp_path,
            read_timeout=600,
            write_timeout=600,
            connect_timeout=30,
            pool_timeout=30,
        )
        return await asyncio.to_thread(
            finalize_temp_file,
            temp_path,
            settings.files_dir,
            original_name,
        )
    finally:
        temp_path.unlink(missing_ok=True)


async def handle_incoming_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    if message is None:
        return

    attachment = get_message_file(message)
    if attachment is None:
        await message.reply_text(
            "Please send a file or supported media attachment in this private chat."
        )
        return

    media, original_name = attachment
    expected_size = getattr(media, "file_size", None)
    size_text = f" ({human_size(expected_size)})" if expected_size is not None else ""
    status_message = await message.reply_text(
        f"File received{size_text}. Saving it to files/..."
    )

    semaphore: asyncio.Semaphore = context.application.bot_data["save_semaphore"]
    settings: Settings = context.application.bot_data["settings"]

    try:
        async with semaphore:
            saved_path = await save_attachment(
                media, original_name, context, settings
            )

        actual_size = saved_path.stat().st_size
        relative_path = Path("files") / saved_path.name
        await status_message.edit_text(
            "File saved successfully.\n\n"
            f"Name: {saved_path.name}\n"
            f"Size: {human_size(actual_size)}\n"
            f"Path: {relative_path.as_posix()}"
        )
        logger.info(
            "Saved file %s (%s bytes) from owner %s",
            saved_path.name,
            actual_size,
            update.effective_user.id if update.effective_user else "unknown",
        )
    except (TelegramError, OSError, ValueError) as exc:
        logger.exception("Could not save incoming Telegram file")
        await status_message.edit_text(
            "I could not save this file. Check the bot logs and available disk space.\n"
            f"Details: {str(exc)[:350]}"
        )


async def error_handler(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    logger.error("Unhandled bot error", exc_info=context.error)


def build_application(settings: Settings) -> Application:
    builder = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .concurrent_updates(2)
        .connection_pool_size(8)
        .connect_timeout(30)
        .read_timeout(60)
        .write_timeout(60)
        .pool_timeout(30)
    )

    if settings.local_mode:
        builder = (
            builder
            .base_url(settings.api_base_url)
            .base_file_url(settings.api_file_url)
            .local_mode(True)
        )

    application = builder.build()
    application.bot_data["settings"] = settings
    application.bot_data["save_semaphore"] = asyncio.Semaphore(2)

    # Every command and message handler is restricted to the owner's private chat.
    owner_private = filters.User(user_id=settings.owner_id) & filters.ChatType.PRIVATE
    application.add_handler(CommandHandler("start", start_command, filters=owner_private))
    application.add_handler(CommandHandler("help", help_command, filters=owner_private))
    application.add_handler(CommandHandler("status", status_command, filters=owner_private))
    application.add_handler(
        MessageHandler(owner_private & ~filters.COMMAND, handle_incoming_message)
    )
    application.add_error_handler(error_handler)

    return application


def main() -> None:
    try:
        settings = load_settings()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    application = build_application(settings)
    logger.info(
        "Starting UploadBot in %s mode. Files directory: %s",
        settings.api_mode,
        settings.files_dir,
    )
    application.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
