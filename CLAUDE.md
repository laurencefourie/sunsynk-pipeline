# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A Python script that pulls telemetry from the Sunsynk Connect cloud API, appends it to a Google Sheet, and supports analysis aimed at **optimising inverter setup** (battery thresholds, time-of-use windows, charge/discharge limits, grid-export behaviour). Reference client: https://github.com/jamesridgway/sunsynk-api-client.

## Stack

- Python managed with **uv** (not pip or poetry). Use `uv add <pkg>`, `uv sync`, `uv run <cmd>`. Do not edit `requirements.txt` by hand.
- `sunsynk-api-client` — async client (`SunsynkClient`, used inside `async with`). All Sunsynk calls are coroutines; don't wrap them in threads.
- `gspread` + `google-auth` for Google Sheets, authenticated with a **service account JSON key**. The sheet must be shared with the service account's email or writes will 403.
- `pandas` for analysis (only pull it in once analysis code exists — don't add it preemptively).

## Running

- Run anything with `uv run python -m <module>` so it uses the project's venv.
- The entry point is intended to run as a one-shot per invocation (fetch → append → exit), driven by **cron on an always-on Ubuntu server** (GitHub Actions schedule triggers proved unreliable on free public repos), not as a long-lived daemon. Don't add scheduling logic inside the script itself. The Actions workflow keeps `workflow_dispatch` for manual one-off triggers.

## Secrets

Secrets live in **GitHub Actions secrets** in production; the workflow writes them into env vars for the run. Locally, mirror them in a gitignored `.env` loaded with `python-dotenv`. Expected names:

- `SUNSYNK_USERNAME`, `SUNSYNK_PASSWORD`
- `GOOGLE_SERVICE_ACCOUNT_JSON` (the full JSON key contents, not a path — Actions secrets can't store files)
- `GOOGLE_SHEET_ID`

Never log secret values, never commit `.env` or any `*.json` key file, and never hardcode the spreadsheet ID in a way that hides it from review.

## Data model

**Tab-per-metric layout.** The sheet has one tab per metric category: `battery`, `grid`, `pv`, `load`, `inverter`. Each row is one snapshot. Common first columns on every tab: `timestamp_utc` (ISO 8601, UTC), `inverter_sn`. Append-only — never rewrite or reorder historical rows. Adding new columns at the right is safe; reordering or renaming existing columns breaks every chart and analysis built on the sheet.

Timestamps are UTC at the source. Do any local-time conversion (SAST, UTC+02:00) at read time, not at write time.

One scheduled run = one append per tab (so ~5 Sheets writes per run). Batch writes per tab; don't call `append_row` in a loop.

## Analysis goal

When asked to analyse, frame findings around **inverter settings the user can change**: battery SOC floor, charge/discharge power caps, grid-charge windows, time-of-use schedules, export limits. A correlation or anomaly that doesn't map to an actionable setting is less useful than a smaller finding that does.

## Repo etiquette

- This is a personal repo; no PR review process. Commit directly to `main` unless asked otherwise.
- Keep the Actions workflow file minimal — `workflow_dispatch` trigger, checkout, `uv sync`, `uv run` the entry point. Don't add matrix builds or multi-Python testing.
