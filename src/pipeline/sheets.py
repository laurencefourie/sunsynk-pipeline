from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from .fetch import TABS

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _client(sa_info: dict) -> gspread.Client:
    creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    return gspread.authorize(creds)


def open_sheet(sa_info: dict, sheet_id: str) -> gspread.Spreadsheet:
    return _client(sa_info).open_by_key(sheet_id)


def _ensure_tab(ss: gspread.Spreadsheet, name: str, header: list[str]) -> gspread.Worksheet:
    try:
        ws = ss.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=name, rows=1000, cols=max(26, len(header)))
        ws.append_row(header, value_input_option="USER_ENTERED")
        return ws

    # Tab exists. If it's empty, write the header; otherwise leave columns
    # alone (column order is sacred — see CLAUDE.md).
    if not ws.row_values(1):
        ws.append_row(header, value_input_option="USER_ENTERED")
    return ws


def _row_header(snapshot: dict[str, Any], tab: str) -> list[str]:
    return ["timestamp_utc", "inverter_sn", *snapshot["rows"][tab].keys()]


def _row_values(snapshot: dict[str, Any], tab: str, header: list[str]) -> list[Any]:
    base = {"timestamp_utc": snapshot["timestamp_utc"], "inverter_sn": snapshot["inverter_sn"]}
    full = {**base, **snapshot["rows"][tab]}
    return [full.get(col) for col in header]


def read_tails(ss: gspread.Spreadsheet) -> dict[str, dict[str, Any] | None]:
    """Last row of each tab, as {column_name: value}. None if tab is empty or missing."""
    tails: dict[str, dict[str, Any] | None] = {}
    for tab in TABS:
        try:
            ws = ss.worksheet(tab)
        except gspread.WorksheetNotFound:
            tails[tab] = None
            continue
        rows = ws.get_all_values()
        if len(rows) < 2:
            tails[tab] = None
            continue
        header = rows[0]
        last = rows[-1]
        tails[tab] = {h: v for h, v in zip(header, last, strict=False)}
    return tails


def append_snapshots(
    ss: gspread.Spreadsheet,
    snapshots: list[dict[str, Any]],
) -> dict[str, int]:
    """Append one row per snapshot per tab. Returns rows-appended count per tab.

    Idempotency: if a tab's current last row has the same (timestamp_utc, inverter_sn)
    pair as a snapshot we're about to write, that snapshot's row for that tab is skipped.
    Protects against double-invocation within the same fetch second.
    """
    tails = read_tails(ss)
    counts: dict[str, int] = dict.fromkeys(TABS, 0)
    if not snapshots:
        return counts

    sample = snapshots[0]
    for tab in TABS:
        header = _row_header(sample, tab)
        ws = _ensure_tab(ss, tab, header)
        # Re-read header from the sheet in case the tab pre-existed with a different one.
        sheet_header = ws.row_values(1) or header

        rows_to_append: list[list[Any]] = []
        for snap in snapshots:
            tail = tails.get(tab)
            if tail and tail.get("timestamp_utc") == snap["timestamp_utc"] \
                    and tail.get("inverter_sn") == snap["inverter_sn"]:
                continue
            rows_to_append.append(_row_values(snap, tab, sheet_header))

        if rows_to_append:
            ws.append_rows(rows_to_append, value_input_option="USER_ENTERED")
            counts[tab] = len(rows_to_append)
    return counts
