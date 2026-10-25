"""Command line entry point: real-edge-backtest."""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from real_edge_backtest.data.check import check_dataset, format_report
from real_edge_backtest.data.download import ArchiveError, download_klines
from real_edge_backtest.data.intervals import INTERVAL_SECONDS
from real_edge_backtest.data.store import DataError, build_dataset


def _month(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM, got {value!r}") from None


def _add_dataset_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--symbol", required=True, help="trading pair, e.g. BTCUSDT")
    parser.add_argument(
        "--interval", required=True, choices=list(INTERVAL_SECONDS), help="kline interval"
    )
    parser.add_argument(
        "--data-dir", type=Path, default=Path("data"), help="data folder (default: ./data)"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="real-edge-backtest")
    commands = parser.add_subparsers(dest="command", required=True)

    data = commands.add_parser("data", help="download and check market data")
    data_commands = data.add_subparsers(dest="data_command", required=True)

    download = data_commands.add_parser(
        "download", help="download and verify spot klines, then rebuild and check the dataset"
    )
    _add_dataset_args(download)
    download.add_argument("--start", type=_month, required=True, help="first month, YYYY-MM")
    download.add_argument(
        "--refresh",
        action="store_true",
        help="re-fetch remote CHECKSUM files and re-download zips that Binance replaced",
    )

    check = data_commands.add_parser("check", help="validate a stored dataset")
    _add_dataset_args(check)
    return parser


def _download(args: argparse.Namespace) -> int:
    print(f"Downloading {args.symbol.upper()} {args.interval} from {args.start:%Y-%m} ...")
    try:
        result = download_klines(
            args.data_dir, args.symbol, args.interval, args.start, refresh=args.refresh
        )
    except ArchiveError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"  downloaded        {len(result.downloaded)}")
    print(f"  replaced          {len(result.replaced)}")
    print(f"  verified locally  {len(result.verified_local)}")
    print(f"  not in archive    {len(result.not_available)}")
    for name in result.not_available:
        print(f"    {name}")
    print(f"  corrupt locally   {len(result.corrupt_local)} (deleted, fetched again)")
    for message in result.corrupt_local:
        print(f"    {message}")
    print(f"  failed            {len(result.failed)}")
    for message in result.failed:
        print(f"    {message}")
    if result.failed:
        print("ERROR: some files failed verification and were not used", file=sys.stderr)
        return 1

    try:
        built = build_dataset(args.data_dir, args.symbol, args.interval)
    except DataError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        f"Built {built.path} from {built.files_used} files, {built.rows} rows, "
        f"{built.exact_duplicates_dropped} exact duplicates dropped"
    )
    _print_excluded("off-grid candles excluded", built.off_grid)
    _print_excluded("zero-trade partial candles excluded", built.placeholders)
    print()
    return _check(args)


def _print_excluded(label: str, times: list) -> None:
    print(f"  {label}: {len(times)}")
    if times:
        print(f"    {times[0]:%Y-%m-%d %H:%M:%S.%f} .. {times[-1]:%Y-%m-%d %H:%M:%S.%f} UTC")


def _check(args: argparse.Namespace) -> int:
    try:
        report = check_dataset(args.data_dir, args.symbol, args.interval)
    except FileNotFoundError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(format_report(report))
    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "data" and args.data_command == "download":
        return _download(args)
    return _check(args)


if __name__ == "__main__":
    sys.exit(main())
