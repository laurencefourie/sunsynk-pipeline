---
name: analyse-inverter
description: Read recent Sunsynk telemetry from the Google Sheet and produce a focused report of inverter setting changes likely to improve battery longevity, grid-cost outcomes, or solar self-consumption. Use this skill whenever the user asks to "analyse the data", "optimise the inverter", "look at the numbers", "what should I change", "how is the battery doing", "are we exporting enough", "is load shedding hurting us", "what's the cheapest setup", "tune the system", or anything that hints at acting on the telemetry rather than just viewing it. Also use when the user mentions specific Sunsynk settings (SOC floor, time-of-use, grid charge, charge cap, sell mode) — they almost certainly want the data interrogated, not a generic explanation. This skill exists because raw rows in a spreadsheet don't tell you which knob to turn; turning the data into a small list of concrete, justified setting changes is the whole point of the pipeline.
---

# analyse-inverter

Turn rows in the Sunsynk Google Sheet into a small list of **specific inverter setting changes** with the evidence that justifies each one. The user is in South Africa (SAST = UTC+2), so all hour-of-day reasoning should be done in local time even though timestamps are stored UTC.

## When to use

Triggered when the user wants a decision, not just a view: "what should I change", "is the SOC floor right", "are we wasting solar", "should I turn on grid charge", "analyse last week". Also use proactively if the user shares the sheet and asks open-ended questions about how their system is doing — they want recommendations, not a chart.

## Pull the data

Use the project's CLI, not gspread or other libraries directly. The commands honour the env / Actions secrets the user already configured.

```
uv run sunsynk read --last 2016 --json
```

Default cadence is 5 min, so:
- `--last 12` = last hour
- `--last 288` = last day
- `--last 2016` = last week
- `--last 8640` = last month

Pick a window that matches what the user asked for. If they didn't specify, default to **one week** (`--last 2016`) — enough for diurnal patterns to be visible without overwhelming the analysis. If the sheet doesn't have that much yet, the command returns whatever exists; check the row count and note it in the report.

For deep dives on one tab:

```
uv run sunsynk read --tab battery --last 2016 --json
```

## What to look for

The five tabs map onto five questions the user can act on. Don't try to cover all five every time — focus on the one or two where the data has something to say.

### Battery — cycle health and headroom

- **Daily minimum SOC.** Group rows by SAST day, find the lowest `soc_pct` reached. If the daily minimum is **below 20%** on most days, the battery is being depleted too far — recommend raising the SOC floor in inverter settings. If it never drops **below 60%**, the battery is oversized for the load or the floor is too conservative — there's untapped headroom for off-grid hours.
- **Time at extreme SOC.** Count rows where SOC is < 25% or > 95%. Cycle life degrades fastest at extremes; consistent time in either zone is a setting issue.
- **Charge/discharge symmetry.** Compare daily `charge_today_kwh` and `discharge_today_kwh`. They should be close; a big gap suggests grid-charging is on (charge >> discharge) or the system is exporting solar at the expense of storing it.
- **Discharge power.** Look at the distribution of `power_w` while discharging (status indicates direction). If discharge is regularly hitting the inverter's nameplate output, the discharge cap is unset or too high — capping it preserves cycle life with little real-world cost.
- **Status code.** The Sunsynk `status` integer means: 1 = idle/standby, 2 = discharging, 3 = charging. Don't quote those mappings to the user as gospel — they're inferred from observed behaviour.

### Grid — when and how much

- **Hourly import pattern (SAST).** Bucket rows by local hour, sum positive `power_w` (import). Peaks at SAST 06:00–09:00 or 17:00–22:00 are when Eskom Homeflex/Megaflex tariffs are highest — if there's room in the battery before those windows, recommend a grid-charge window earlier (off-peak).
- **Export.** If `export_today_kwh` is always 0 but PV `power_w` is hitting high values mid-day on sunny days, the inverter isn't configured to export — either intentional (no feed-in tariff) or a missed opportunity. Ask the user which.
- **Frequency excursions.** Persistent `freq_hz` below 49.5 or above 50.5 indicates a weak grid or load shedding nearby — relevant for setting grid quality thresholds.

### PV — generation envelope

- **Daily peak.** Maximum `power_w` per SAST day. Compare to the inverter's PV input rating; if peak is always well below it, panels may be under-sized or shaded. If peak is *exactly at* the rating for hours on end, the inverter is clipping — there's no setting fix for that, but it's worth flagging.
- **Generation curve shape.** Sum power in 1-hour buckets across a sunny day. A symmetric bell curve = healthy. Asymmetry (e.g., morning dropoff) suggests east-vs-west string imbalance or shading.
- **`string_count` changes.** If this fluctuates between rows, the API is returning inconsistent data; don't trust per-string values.

### Load — what's actually being consumed

- **Average + peak.** Mean `power_w` over a week and the 95th percentile. Useful background context for sizing recommendations (e.g., "raising SOC floor to 40% still gives you 12 hours at average load").
- **Night-time floor.** Minimum load during SAST 02:00–04:00 — the always-on baseline. If high, the user may have a phantom load worth investigating outside the inverter settings.

### Inverter — health checks only

- `status` should be 1 across nearly all rows. Other values briefly are normal; sustained means the inverter is in a fault or maintenance state.
- `updated_at` should track within ~5 minutes of `timestamp_utc`. Big lags mean the inverter is offline and the cloud is serving stale data — flag prominently because every other analysis becomes unreliable.

## Low-data handling

If you have less than **24 hours** of rows:
- Don't produce SOC-floor or TOU recommendations — there's no diurnal pattern yet.
- Do report what the system looks like *right now* (snapshot summary) and say "come back in a few days for pattern analysis".

If you have **1–7 days**:
- Daily aggregates are OK; weekly trends aren't.

If you have **> 7 days**:
- Full report.

## Output format

Write a markdown report with this structure. Keep it tight — one or two strong recommendations beat a long list of weak ones.

```
# Sunsynk analysis — <window, e.g. "last 7 days, 2014 rows">

## Snapshot
- Battery: avg SOC X%, min Y%, daily charge/discharge A/B kWh
- PV: avg peak Z kW, total generated W kWh
- Grid: imported V kWh, exported U kWh
- Load: avg N W, peak M W

## Recommendations
### 1. <Setting name>: change from <current?> to <proposed>
**Evidence:** <2-3 sentences referencing specific patterns in the data>
**Expected impact:** <one sentence, honest about uncertainty>
**How to apply:** <which Sunsynk menu/screen — only if you know it; otherwise "set in the Sunsynk app under battery/system settings">

### 2. ...

## Things to watch
- <Anything anomalous but not actionable yet — e.g., "inverter `updated_at` lagging 12 minutes on three rows, may indicate connectivity flakes">
```

**Tone:** confident about what the data shows, honest about what it doesn't. "I can't tell from this data whether your grid tariff has time-of-use bands; if it does, the import pattern suggests…" is better than fabricating a tariff.

## What this skill does NOT do

- It does not change inverter settings remotely — the Sunsynk API client in this project is read-only, by design.
- It does not predict — it summarises observed patterns and suggests changes. Don't extrapolate to "you'll save X rand per month" unless the user provides their tariff.
- It does not modify the sheet. Read-only. If the schema is wrong, that's a fetcher fix, not an analyser fix.
