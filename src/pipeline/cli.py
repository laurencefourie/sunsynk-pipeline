import argparse
import asyncio
import json
import sys

from . import config, fetch, sheets


def _print_json(obj) -> None:
    json.dump(obj, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def _cmd_pull(args: argparse.Namespace) -> int:
    cfg = config.load(require_sheets=args.write)
    snapshots = asyncio.run(fetch.fetch_snapshots(cfg.sunsynk_username, cfg.sunsynk_password))

    if not snapshots:
        print("No inverters found on this account.", file=sys.stderr)
        return 1

    if args.json:
        _print_json(snapshots)
    else:
        for snap in snapshots:
            print(f"\n=== {snap['inverter_sn']} @ {snap['timestamp_utc']} ===", file=sys.stderr)
            for tab, row in snap["rows"].items():
                joined = ", ".join(f"{k}={v}" for k, v in row.items())
                print(f"  [{tab}] {joined}", file=sys.stderr)

    if args.write:
        ss = sheets.open_sheet(cfg.google_service_account_info, cfg.google_sheet_id)
        counts = sheets.append_snapshots(ss, snapshots)
        print(
            "\nAppended: " + ", ".join(f"{tab}={n}" for tab, n in counts.items()),
            file=sys.stderr,
        )
    return 0


def _cmd_read(args: argparse.Namespace) -> int:
    cfg = config.load(require_sheets=True)
    ss = sheets.open_sheet(cfg.google_service_account_info, cfg.google_sheet_id)
    tabs = [args.tab] if args.tab else list(fetch.TABS)
    result = {tab: sheets.read_recent(ss, tab, args.last) for tab in tabs}
    if args.json or args.tab is None:
        _print_json(result)
    else:
        for row in result[args.tab]:
            print(", ".join(f"{k}={v}" for k, v in row.items()))
    return 0


def _cmd_sheet_tail(args: argparse.Namespace) -> int:
    cfg = config.load(require_sheets=True)
    ss = sheets.open_sheet(cfg.google_service_account_info, cfg.google_sheet_id)
    tails = sheets.read_tails(ss)
    if args.json:
        _print_json(tails)
    else:
        for tab, row in tails.items():
            if row is None:
                print(f"[{tab}] (empty or missing)")
            else:
                print(f"[{tab}] " + ", ".join(f"{k}={v}" for k, v in row.items()))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sunsynk", description="Sunsynk -> Google Sheets pipeline"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_pull = sub.add_parser("pull", help="Fetch one snapshot per inverter")
    mode = p_pull.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Fetch only, do not write (default)")
    mode.add_argument("--write", action="store_true", help="Fetch and append to the sheet")
    p_pull.add_argument("--json", action="store_true", help="Emit snapshots as JSON on stdout")
    p_pull.set_defaults(func=_cmd_pull)

    p_tail = sub.add_parser("sheet-tail", help="Show the last row of each tab")
    p_tail.add_argument("--json", action="store_true", help="Emit tails as JSON on stdout")
    p_tail.set_defaults(func=_cmd_sheet_tail)

    p_read = sub.add_parser("read", help="Read the last N rows of one or all tabs")
    p_read.add_argument(
        "--tab",
        choices=list(fetch.TABS),
        help="Limit to a single tab; if omitted, returns all tabs as JSON",
    )
    p_read.add_argument(
        "--last",
        type=int,
        default=96,
        help="Number of recent rows to return (default 96 = 1 day @ 15min)",
    )
    p_read.add_argument("--json", action="store_true", help="Force JSON output")
    p_read.set_defaults(func=_cmd_read)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except config.MissingEnvError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
