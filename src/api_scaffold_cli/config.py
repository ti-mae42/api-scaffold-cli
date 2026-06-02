from __future__ import annotations

import os
from pathlib import Path


ENV_BASE_REPO_URL_KEY = "BASE_REPO_URL"
FALLBACK_BASE_REPO_URL = "https://github.com/ti-mae42/python-flask-base-api"


def load_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")

    return values


def get_default_base_repo_url() -> str:
    if env_value := os.getenv(ENV_BASE_REPO_URL_KEY):
        return env_value

    dotenv_values = load_dotenv(Path.cwd() / ".env")
    return dotenv_values.get(ENV_BASE_REPO_URL_KEY, FALLBACK_BASE_REPO_URL)
