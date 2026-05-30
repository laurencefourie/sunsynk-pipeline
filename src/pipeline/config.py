import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv


class MissingEnvError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    sunsynk_username: str
    sunsynk_password: str
    google_service_account_info: dict
    google_sheet_id: str


def load(require_sheets: bool = True) -> Config:
    load_dotenv()

    username = os.getenv("SUNSYNK_USERNAME")
    password = os.getenv("SUNSYNK_PASSWORD")
    if not username or not password:
        raise MissingEnvError("SUNSYNK_USERNAME and SUNSYNK_PASSWORD must be set")

    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if require_sheets:
        if not sa_json:
            raise MissingEnvError("GOOGLE_SERVICE_ACCOUNT_JSON must be set")
        if not sheet_id:
            raise MissingEnvError("GOOGLE_SHEET_ID must be set")

    sa_info: dict = {}
    if sa_json:
        try:
            sa_info = json.loads(sa_json)
        except json.JSONDecodeError as e:
            raise MissingEnvError(
                "GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON — paste the full key contents, "
                "not a file path"
            ) from e

    return Config(
        sunsynk_username=username,
        sunsynk_password=password,
        google_service_account_info=sa_info,
        google_sheet_id=sheet_id or "",
    )
