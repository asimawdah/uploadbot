from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    owner_id: int
    files_dir: Path
    api_mode: str
    api_base_url: str
    api_file_url: str

    @property
    def local_mode(self) -> bool:
        return self.api_mode == "local"


def load_settings() -> Settings:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise ValueError("BOT_TOKEN is missing. Set it in your .env file.")

    owner_id_value = os.getenv("OWNER_ID", "").strip()
    try:
        owner_id = int(owner_id_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "OWNER_ID must be your numeric Telegram user ID."
        ) from exc

    if owner_id <= 0:
        raise ValueError("OWNER_ID must be a positive Telegram user ID.")

    api_mode = os.getenv("BOT_API_MODE", "local").strip().lower()
    if api_mode not in {"local", "cloud"}:
        raise ValueError("BOT_API_MODE must be either 'local' or 'cloud'.")

    files_dir = Path(os.getenv("FILES_DIR", "files")).expanduser()
    api_base_url = os.getenv(
        "BOT_API_BASE_URL", "http://127.0.0.1:8081/bot"
    ).strip()
    api_file_url = os.getenv(
        "BOT_API_FILE_URL", "http://127.0.0.1:8081/file/bot"
    ).strip()

    if api_mode == "local" and (not api_base_url or not api_file_url):
        raise ValueError(
            "BOT_API_BASE_URL and BOT_API_FILE_URL are required in local mode."
        )

    files_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        bot_token=bot_token,
        owner_id=owner_id,
        files_dir=files_dir.resolve(),
        api_mode=api_mode,
        api_base_url=api_base_url,
        api_file_url=api_file_url,
    )
