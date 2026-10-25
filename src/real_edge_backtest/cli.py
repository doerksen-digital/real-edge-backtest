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

    run = commands.add_parser("run", help="run a backtest from a TOML config")
    run.add_argument("--config", type=Path, required=True, help="path to the run config")
    run.add_argument(
        "--holdout",
        action="store_true",
        help="allow a run on holdout data (ETHUSDT, SOLUSDT); marked as a holdout run",
    )

    report = commands.add_parser("report", help="write the HTML report of a run folder")
    report.add_argument("--run", type=Path, required=True, help="run folder written by 'run'")
    report.add_argument(
        "--out", type=Path, help="HTML file to write (default: report.html in the run folder)"
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    # Imported here so data commands do not load the engine.
    from real_edge_backtest import experiments
    from real_edge_backtest.analysis.metrics import analyze, load_run
    from real_edge_backtest.engine import load_config
    from real_edge_backtest.engine.results import summarize, write_run
    from real_edge_backtest.holdout import check_holdout
    from real_edge_backtest.runner import (
        history_warnings,
        load_candles,
        run_backtest,
        run_metadata,
    )

    try:
        config = load_config(args.config)
        holdout = check_holdout(config.symbol, args.holdout)
        meta = run_metadata(config)
        meta["holdout"] = holdout
        entries = experiments.read_log(config.experiment_log)
        window = meta["window"]
        seen = experiments.seen_window(entries, config.strategy, window["start"], window["end"])
        meta["seen_window"] = seen
        candles = load_candles(config)
        meta["first_candle"] = candles["open_time"].iloc[0]
        meta["warnings"] = history_warnings(candles, window["start"])
        result = run_backtest(config, candles, holdout=args.holdout)
        meta["gaps"] = {
            **result.gap_summary(),
            "ignored_signals": result.counters.get("ignored_after_gap", 0),
        }
    except (FileNotFoundError, KeyError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    folder = write_run(result, config.runs_dir, config.name, config.source_text, meta)
    a = analyze(load_run(folder))
    entry = experiments.make_entry(
        meta,
        {
            "trades": a.stats["trades"],
            "net_pnl": a.stats["net_pnl"],
            "return": a.total_return,
            "profit_factor": a.stats["profit_factor"],
            "max_drawdown_pct": a.max_drawdown[1],
            "time_in_market": a.time_in_market,
            "passed": a.passed,
        },
        folder.as_posix(),
    )
    experiments.append(config.experiment_log, entry)
    variants = experiments.variant_count([*entries, entry], config.strategy)

    s = summarize(result)
    open_trades = len(result.trades) - s.trades
    if holdout:
        print(f"HOLDOUT RUN: {config.symbol} is holdout data (research protocol, docs/PLAN.md)")
    for warning in meta["warnings"]:
        print(f"WARNING: {warning}")
    print(f"Run {config.name}: {config.symbol} {config.interval}, {config.strategy}")
    print(f"  window          {window['start']} to {window['end']} (candle close, end exclusive)")
    print(f"  seen window     {experiments.describe_seen(seen)}")
    print(f"  variants        {variants} parameter sets of {config.strategy} logged so far")
    print(f"  fill model      {config.broker.fill_model}")
    capped = result.counters.get("sizing_capped", 0)
    print(
        f"  sizing          {config.sizing.mode}"
        + (f", {capped} entries capped at 100% of equity" if capped else "")
    )
    g = meta["gaps"]
    print(
        f"  gaps            {g['count']} ({g['above_threshold']} with >= {g['min_gap_bars']} "
        f"missing), {g['ignored_signals']} crosses ignored after gaps"
    )
    print(f"  trades          {s.trades}" + (f" (+{open_trades} open)" if open_trades else ""))
    print(f"  win rate        {s.win_rate:.2%} ({s.winners} winners)")
    print(f"  profit factor   {s.profit_factor:.3f}")
    print(f"  net PnL         {s.net_pnl:,.2f}")
    print(f"  max drawdown    {s.max_drawdown:,.2f}")
    print(f"  output          {folder}")
    print(f"  logged to       {config.experiment_log}")
    return 0


def _report(args: argparse.Namespace) -> int:
    from real_edge_backtest.report.html import write_report

    try:
        path = write_report(args.run, args.out)
    except (FileNotFoundError, KeyError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Report written to {path}")
    return 0


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
    if args.command == "run":
        return _run(args)
    if args.command == "report":
        return _report(args)
    if args.command == "data" and args.data_command == "download":
        return _download(args)
    return _check(args)


if __name__ == "__main__":
    sys.exit(main())
