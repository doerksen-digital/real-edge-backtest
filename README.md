# real-edge-backtest

An honest backtesting tool for short-term crypto strategies.

Most backtests look better than reality because they peek at future candles, ignore costs, or test so many variants that one wins by luck. This project is built to make all three hard to do by accident.

> **Status:** Phase 1 (data). Market data can be downloaded and checked. No backtests yet. See the [plan](docs/PLAN.md) for what comes next.

## What it will do

- Download and verify historical candles from the Binance public data archive
- Run strategies bar by bar so they can only see closed candles
- Model fees, slippage and intrabar stops, and later funding and liquidation for perpetuals
- Log every run, so it is visible how many variants were tried
- Produce an HTML report with trade metrics, per-year results and a buy-and-hold comparison
- Run robustness tests: parameter grids, walk-forward, a one-shot lockbox period, cost stress and Monte Carlo

## Development

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest
```

## Data

Spot candles come from the [Binance public data archive](https://data.binance.vision/). Monthly files are used for complete months, daily files for the current month and for last month until its monthly file is published.

Download, verify and check:

```bash
real-edge-backtest data download --symbol BTCUSDT --interval 1h --start 2018-01
```

Check an existing dataset:

```bash
real-edge-backtest data check --symbol BTCUSDT --interval 1h
```

Add `--refresh` to `data download` to compare every local file with the remote `.CHECKSUM` and fetch files that Binance replaced. Supported intervals: `1s 1m 3m 5m 15m 30m 1h 2h 4h 6h 8h 12h 1d`.

What happens:

- Every zip is verified against its `.CHECKSUM` (SHA-256) on every run. A file that fails is deleted and reported, never used. Re-running only downloads what is missing.
- Downloads run one at a time with a pause. HTTP 429 and 5xx are retried with exponential backoff.
- Timestamps are milliseconds before 2025-01-01 and microseconds after. The unit is detected per row and all times are stored in UTC.
- Exact duplicate rows are dropped. Candles off the interval grid and zero-trade placeholder candles are excluded. Candles that closed early before an outage are kept and marked `partial`.
- Gaps are exchange downtime. They are listed, never filled.

Files, all under the gitignored `data/` folder:

- `data/raw/spot/{monthly,daily}/klines/{SYMBOL}/{interval}/`: verified zips and their checksums
- `data/spot/klines/{SYMBOL}/{interval}.parquet`: the cleaned dataset

The download logic follows the official downloader in [binance/binance-public-data](https://github.com/binance/binance-public-data) (MIT).

**Data license:** the Binance Vision dataset terms license the data under CC BY-NC-SA 4.0. They allow personal, non-production backtesting research. They forbid live trading execution, paid signals and other commercial use. The data is never committed to this repository.

## Running a backtest

A run is defined by a TOML config: data, strategy and parameters, broker settings and fill model. Example: [configs/ema_vwap_parity.toml](configs/ema_vwap_parity.toml).

```bash
real-edge-backtest run --config configs/ema_vwap_parity.toml
```

The command prints trade count, win rate, profit factor, net PnL and max drawdown. It writes `trades.csv`, `equity.csv` and a copy of the config to `runs/<UTC timestamp>-<name>/` (gitignored).

How the engine works:

- Bar by bar. Inside each bar, stops that the bar reaches fill first. Then the strategy runs on the closed bar, and market orders fill at that close plus slippage.
- Prices are whole ticks, quantities whole lots and money is Decimal, so sizing and PnL have no float rounding errors.
- Two fill models. `tradingview` follows TradingView's bar path (open, high, low, close if the open is nearer the high, otherwise open, low, high, close). `pessimistic` fills a stop before a target whenever both are inside one bar. Both fill an order passed by a gap at the open. `pessimistic` is the default; the parity config uses `tradingview`.

The parity test compares a run with a TradingView reference. Put `tv_summary.csv` and `tv_trades.csv` in `tests/fixtures/` (format in `tests/test_parity.py`). Without them the test is skipped.

## Credits

The design borrows ideas from [backtesting.py](https://github.com/kernc/backtesting.py), [Freqtrade](https://github.com/freqtrade/freqtrade) and [NautilusTrader](https://github.com/nautechsystems/nautilus_trader). No code is copied from them. Code taken from permissively licensed projects is credited where it is used.

## Disclaimer

This is a research tool, not financial advice. A strategy that passes every test here can still lose money.

## License

[MIT](LICENSE)
