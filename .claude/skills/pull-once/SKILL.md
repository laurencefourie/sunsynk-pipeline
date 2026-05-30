---
name: pull-once
description: Run a single Sunsynk → Google Sheets pull cycle locally with a fetch-diff-confirm-write flow. Use this skill whenever the user wants to manually trigger a Sunsynk data pull, smoke-test the fetcher, preview what would be written to the sheet, test the cron job logic without waiting for the schedule, debug auth/sheet errors, or sanity-check the writer after changing the data model. Also use when the user says things like "pull now", "run the fetcher", "test the writer", "see what data we'd get", "smoke test", or any variant referring to this project's data ingestion. The skill exists because writing directly to an append-only spreadsheet is irreversible — a four-step fetch → diff → confirm → write flow catches drift, auth problems, and schema mistakes before they corrupt the history.
---

# pull-once

A manual, interactive single-shot of the Sunsynk → Google Sheets pipeline. Designed for local development, sanity checks before a deploy, and debugging auth/sheet issues without waiting for the cron run.

## When to use

- The user wants to verify the fetcher works end-to-end before merging a change.
- The cron run failed and the user wants to reproduce locally with full visibility.
- The data model changed (new column, new tab) and the user wants to confirm the next append won't break historical rows.
- Onboarding to a new machine and verifying credentials work.

## The flow

This skill runs four steps in order. **Do not skip steps**, even if the user asks — the steps exist because Google Sheets appends are irreversible and silent failures are easy.

### Step 1 — Fetch (dry, no writes)

Run:

```
uv run sunsynk pull --dry-run --json
```

Expected output: a JSON object with one key per tab (`battery`, `grid`, `pv`, `load`, `inverter`), each containing the row that *would* be appended. Example shape:

```json
{
  "timestamp_utc": "2026-05-30T10:05:00Z",
  "inverter_sn": "SN1234",
  "rows": {
    "battery": {"soc_pct": 78, "power_w": -1240, "voltage_v": 53.1, "temp_c": 31.2},
    "grid":    {"power_w": 320, "voltage_v": 232.4, "freq_hz": 50.01},
    "pv":      {"power_w": 2600, "string1_w": 1840, "string2_w": 760},
    "load":    {"power_w": 1380, "voltage_v": 232.0},
    "inverter":{"temp_c": 42.8, "status": "normal"}
  }
}
```

If this fails with an auth error, jump to **Troubleshooting → Sunsynk auth**. Do not proceed to Step 2 with stale or partial data.

### Step 2 — Read the current sheet tail

Run:

```
uv run sunsynk sheet-tail --json
```

Expected output: the **last row** of each tab, in the same shape as Step 1's `rows`. This is what's already in the sheet — your reference for what "normal" looks like right now.

If this fails with a 403, the service account isn't shared on the sheet. Jump to **Troubleshooting → Sheet 403**.

### Step 3 — Diff and confirm

Render a side-by-side comparison: for each tab, show the last sheet row and the new row, highlighting:

- **New columns** in the new row that don't exist in the last sheet row → this means the schema is about to widen. That's fine for a sheet (appending columns is safe) but the user should know.
- **Missing columns** in the new row that exist in the last sheet row → this means the fetcher dropped a field. That's almost always a bug. **Stop and ask** before continuing.
- **Suspicious values** — `power_w` that's > 20kW (inverter limit), SOC outside 0–100, missing timestamp, timestamp not in UTC, timestamp more than 5 minutes stale. Surface these as warnings, don't auto-fail.

Then ask the user: "Append these rows to the sheet? (yes / no)". Wait for confirmation. Do not interpret "looks fine" or "sure" as a no.

### Step 4 — Write

On explicit yes, run:

```
uv run sunsynk pull --write
```

This re-fetches and appends in one transaction. **Do not** pipe the JSON from Step 1 into the writer — re-fetch so the timestamp reflects the actual write moment, not the dry-run moment. (A stale timestamp in an append-only sheet is worse than a slightly delayed one.)

On success, report: the timestamp written, which tabs got appended, and the new row count per tab. Suggest the user open the sheet to eyeball it.

## Contract for the Python entry point

If the commands above don't exist yet, the fetcher hasn't been built. Tell the user, and offer to build it to this contract:

- **`sunsynk pull --dry-run --json`** — fetch from the Sunsynk API, return JSON as shown in Step 1. No Sheets calls. Exit 0 on success, non-zero with stderr message on auth/network failure.
- **`sunsynk sheet-tail --json`** — read the last row of each tab. Exit 0 on success, non-zero with stderr on Sheets auth/permission failure.
- **`sunsynk pull --write`** — fetch + append in one go. Idempotent within a 60-second window (don't append twice if invoked twice quickly — check the last timestamp on the battery tab and skip if it matches the new fetch's timestamp to the second).
- All commands respect `SUNSYNK_USERNAME`, `SUNSYNK_PASSWORD`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_SHEET_ID` from env (or `.env` via `python-dotenv` in local runs).

These commands should be registered as a `[project.scripts]` entry in `pyproject.toml` so `uv run sunsynk ...` works.

## Troubleshooting

### Sunsynk auth (401 / `Invalid credentials`)

- Confirm `SUNSYNK_USERNAME` and `SUNSYNK_PASSWORD` are set: `uv run python -c "import os; print(bool(os.getenv('SUNSYNK_USERNAME')))"`.
- The Sunsynk Connect cloud occasionally rotates session tokens; the client library should handle this, but if errors persist, log in via the Sunsynk Connect app to confirm the credentials still work.
- Do not log the password value in any diagnostic.

### Sheet 403 / `PERMISSION_DENIED`

- The service account email (look it up: `uv run python -c "import json,os; print(json.loads(os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON'))['client_email'])"`) must be added as an **editor** on the Google Sheet.
- The Google Sheets API must be enabled on the GCP project that owns the service account.
- `GOOGLE_SHEET_ID` is the long string in the sheet URL between `/d/` and `/edit`, not the URL itself.

### `ModuleNotFoundError` or `command not found: sunsynk`

- Run `uv sync` to install dependencies into the project venv.
- Run from the project root, not a subdirectory — `uv run` resolves the venv from the nearest `pyproject.toml`.
- If `sunsynk` isn't a registered script yet, the fetcher hasn't been built; see **Contract** above.

### A column disappeared from the new row

This is a Sunsynk API change or a fetcher bug — investigate before writing. Appending a row with missing columns means future analysis on that column has a gap that looks like the inverter went offline, when really we just stopped recording it. Almost always worth fixing the fetcher first.

## What this skill does NOT do

- It does not schedule anything. Scheduling is GitHub Actions cron.
- It does not modify historical rows. Ever. The sheet is append-only by design.
- It does not back-fill missed cron runs. If you want to back-fill, that's a separate skill (write one if it comes up repeatedly).
- It does not reformat the sheet, add tabs, or change column order. Schema migrations are manual and deliberate.
