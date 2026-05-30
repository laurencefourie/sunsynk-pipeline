from datetime import UTC, datetime
from typing import Any

from sunsynk.client import SunsynkClient

# Tab order is locked. Adding tabs at the end is safe; reordering breaks
# every chart and analysis built on top of the sheet — see CLAUDE.md.
TABS = ("battery", "grid", "pv", "load", "inverter")


def _now_utc_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _battery_row(b) -> dict[str, Any]:
    return {
        "soc_pct": b.soc,
        "power_w": b.power,
        "voltage_v": b.voltage,
        "current_a": b.current,
        "temp_c": b.temp,
        "charge_today_kwh": b.charge_today,
        "discharge_today_kwh": b.discharge_today,
        "status": b.status,
        "capacity_ah": b.capacity,
    }


def _grid_row(g) -> dict[str, Any]:
    return {
        "power_w": g.pac,
        "voltage_v": g.get_voltage(),
        "current_a": g.get_current(),
        "freq_hz": g.fac,
        "power_factor": g.pf,
        "status": g.status,
        "import_today_kwh": g.today_import,
        "export_today_kwh": g.today_export,
    }


def _pv_row(p) -> dict[str, Any]:
    return {
        "power_w": p.pac,
        "generated_today_kwh": p.generated_today,
        "generated_total_kwh": p.generated_total,
        "string_count": len(p.pv_iv),
    }


def _load_row(o) -> dict[str, Any]:
    vip = o.vip[0] if o.vip else None
    return {
        "power_w": o.pac,
        "freq_hz": o.fac,
        "voltage_v": vip.voltage if vip else None,
        "current_a": vip.current if vip else None,
    }


def _inverter_row(inv) -> dict[str, Any]:
    ver = inv.version
    return {
        "status": inv.status,
        "model": inv.model,
        "pac_w": inv.pac,
        "generated_today_kwh": inv.generated_today,
        "generated_total_kwh": inv.generated_total,
        "sw_ver": ver.soft_ver if ver else None,
        "hw_ver": ver.hard_ver if ver else None,
        "hmi_ver": ver.hmi_ver if ver else None,
        "updated_at": inv.updated_at.isoformat() + "Z" if inv.updated_at else None,
    }


async def fetch_snapshots(username: str, password: str) -> list[dict[str, Any]]:
    """Returns one snapshot dict per inverter. Each snapshot has shape:
        {"timestamp_utc": ..., "inverter_sn": ..., "rows": {tab: {col: val}}}
    Timestamp is set once at the top of the fetch so all tabs for a given run share it.
    """
    timestamp = _now_utc_iso()
    snapshots: list[dict[str, Any]] = []

    async with SunsynkClient(username, password) as client:
        inverters = await client.get_inverters()
        for inv in inverters:
            sn = inv.sn
            battery = await client.get_inverter_realtime_battery(sn)
            grid = await client.get_inverter_realtime_grid(sn)
            pv = await client.get_inverter_realtime_input(sn)
            load = await client.get_inverter_realtime_output(sn)
            snapshots.append({
                "timestamp_utc": timestamp,
                "inverter_sn": sn,
                "rows": {
                    "battery": _battery_row(battery),
                    "grid": _grid_row(grid),
                    "pv": _pv_row(pv),
                    "load": _load_row(load),
                    "inverter": _inverter_row(inv),
                },
            })
    return snapshots
