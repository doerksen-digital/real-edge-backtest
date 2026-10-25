# real-edge-backtest

An honest backtesting tool for short-term crypto strategies.

Most backtests look better than reality because they peek at future candles, ignore costs, or test so many variants that one wins by luck. This project is built to make all three hard to do by accident.

> **Status:** Phase 3 (report and log). Data download, the engine with TradingView parity, the HTML report and the experiment log work. See the [plan](docs/PLAN.md) for what comes next.

## What it will do

- Download and verify historical candles from the Binance public data archive
- Run strategies bar by bar so they can only see closed candles
- Model fees, slippage and intrabar stops, and later funding and liquidation for perpetuals
- Log every run, so it is visible how many variants were tried
- Produce an HTML report with trade metrics, per-year results and a buy-and-hold comparison
- Run robustness tests: parameter grids, walk-forward, cost stress and Monte Carlo, with every tested window recorded

## Development

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest
```

The optional extra `report` (`pip install -e ".[dev,report]"`) adds [QuantStats](https://github.com/ranaroussi/quantstats) for a period-based metrics section in the report. QuantStats requires yfinance, scipy and seaborn. The report never calls yfinance, and it works without the extra.

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

A run is defined by a TOML config: data, strategy and parameters, sizing, broker settings and fill model, gap threshold and pass criteria. Examples: [configs/ema_vwap_parity.toml](configs/ema_vwap_parity.toml) (TradingView parity, 2026) and [configs/ema_vwap_full.toml](configs/ema_vwap_full.toml) (2018 to 2025, pessimistic fills, 3,000 USD) and [configs/ema_vwap_full_fixed.toml](configs/ema_vwap_full_fixed.toml) (the same with a fixed notional of 3,000 USD per trade).

```bash
real-edge-backtest run --config configs/ema_vwap_full.toml
real-edge-backtest report --run runs/<UTC timestamp>-ema_vwap_full
```

`run` prints the window, the seen-window check, the number of logged variants, gap and sizing notes, trade count, win rate, profit factor, net PnL and max drawdown. It writes to `runs/<UTC timestamp>-<name>/` (gitignored):

- `trades.csv`: every trade, with `touches_gap` and `sizing_capped`
- `equity.csv`: every candle of the dataset with close time, open, close, position after the bar and equity at the close
- `run.json`: window, parameters, broker and sizing settings, pass criteria, git commit and dirty flag, SHA-256 of the config and of the dataset, seen window, gap counts, warnings
- `config.toml`: a copy of the config

`report` writes `report.html` into the run folder (or `--out <file>`). The file is self-contained: inline CSS and SVG charts made with matplotlib, no scripts, no external assets.

### Window

`start` and `end` in `[strategy.params]` are UTC times compared with each candle's **close time**. A candle can trade if `start <= close time < end`, so `end` is exclusive. A position still open is closed with "Test end" at the close of the first candle that closes at or after `end`. Metrics, buy and hold and time in market only use the candles of this window, never the whole dataset.

### Indicator history and readiness

Indicators are always computed on the full dataset, so all history before `start` serves as warm-up. A cross is only acted on once EMA 9, VWAP 24, ATR 14 and the previous completed day's close and daily EMA all exist. If `start` is less than 30 days after the first candle, `run` prints a warning with the number of candles available before `start`, and the report header shows it.

### Gaps

Gaps are exchange downtime. They are never filled.

- An open position and its stop live through a gap. If the first candle after a gap opens beyond the stop, the stop fills at that open (plus slippage), in both fill models.
- After a gap of at least `[gaps] min_gap_bars` missing candles (default 3), crosses are ignored until `max(vwap_bars, atr_length, ema_length)` contiguous candles exist again. No entry then uses a VWAP window that spans the gap. An ignored cross does not close an open trade either.
- Every trade open across a missing candle is marked `touches_gap`. The report shows the trade metrics with and without these trades.

### Sizing

`[sizing] mode`:

- `percent_equity` (default): `position_pct` of equity minus the fee reserve, as on TradingView. Used by the parity config.
- `fixed_risk`: `risk_pct` of current equity is lost if the stop fills at its level. Size = risk / stop distance. Needs the ATR stop.
- `fixed_notional`: `notional_usd` per trade.

`fixed_risk` and `fixed_notional` are capped at 100% of equity with the fee reserve (spot, no leverage). Capped entries are marked `sizing_capped` and counted in the run output. Quantities are always whole lots.

### Report

- Header: strategy, window, seen window, fill model, fees, slippage, sizing, starting equity, config hash, git commit, working tree state, data hash, warnings.
- Pass criteria from `[criteria]`: profit factor (`min_profit_factor`, default 1.3), closed trades (`min_trades`, default 100), net PnL still positive both without the `without_top_n` best trades (default 5) and without the best `without_top_pct` percent of trades (default 1, count rounded up), by the return method below, net PnL in both halves of the window. Return, max drawdown and time in market are shown next to buy and hold as comparisons.
- Trade metrics: profit factor, expectancy, win rate, average win and loss, PnL without the top 1, 3 and 5 trades and without the top 1% (return method and USD method), time in market, max drawdown on close equity and on closed trades.
- "Without the best trades", return method (used by the pass criterion): each closed trade's net PnL as a fraction of equity at its entry, the best trades by that return removed, the remaining returns compounded in entry order from the starting equity. The USD method subtracts the best trades' USD PnL and is shown as "USD method (distorted by compounding)": under `percent_equity` sizing later trades are larger in USD only because equity grew.
- Buy and hold: one buy at the first window candle's open, sold at the last window candle's close, same starting equity, commission and slippage.
- Charts: equity, drawdown, return per year, strategy vs buy and hold.
- Tables per calendar year (UTC) and per half of the window. A trade counts in the period of its exit.
- Gap sensitivity, the trade list and, with the `report` extra, a separate "period-based metrics (QuantStats)" section on daily window returns.

### Experiment log

Every `run` appends one line to [experiments/log.jsonl](experiments/log.jsonl), which is committed. The file is only ever appended to. A line holds the timestamp, git commit and dirty flag, config and data hashes, all parameters, window, fill model, sizing mode and key metrics.

- A **variant** is a distinct parameter set of a strategy family (the strategy name), ignoring the window. `run` prints how many variants have been logged.
- **Seen window:** before each run, the log is checked for earlier runs of the same family whose window overlaps. `run` prints how many there are, on how many days they overlap and with how many parameter sets, and the report shows it in the header. It never blocks a run: any window can be run at any time.

There is no hard lockbox. The log makes it visible when a window has already been looked at. The log starts with the nine TradingView runs that chose the daily EMA length on January to October 2026 (`source: tradingview`). That window therefore counts as seen for `ema_vwap`, and 2018 to 2025 is unseen.

How the engine works:

- Bar by bar. Inside each bar, stops that the bar reaches fill first. Then the strategy runs on the closed bar, and market orders fill at that close plus slippage.
- Prices are whole ticks, quantities whole lots and money is Decimal, so sizing and PnL have no float rounding errors.
- Two fill models. `tradingview` follows TradingView's bar path (open, high, low, close if the open is nearer the high, otherwise open, low, high, close). `pessimistic` fills a stop before a target whenever both are inside one bar. Both fill an order passed by a gap at the open. `pessimistic` is the default; the parity config uses `tradingview`.

Max drawdown is measured on the equity at every candle close, including open trades. It does not match TradingView's max drawdown, whose method is not documented. Parity run 2026: TradingView 1,697.05, ours 2,102.69 on close equity and 1,673.61 on closed trades only. Max drawdown is not a parity criterion.

The parity test compares a run with a TradingView reference in `tests/fixtures/`. The reference files are TradingView output and stay local (gitignored). Without them the test is skipped.

### Recreating the TradingView reference

1. Chart: BINANCE:BTCUSDT, 1 hour, standard candles, chart time zone Europe/Zurich.
2. Add the Pine script "EMA 9 / Rolling VWAP Cross v1". Inputs: daily trend filter on, daily EMA length 21, Start 2026-01-01 00:00, End 2026-10-24 00:00 (entered in chart time), all other inputs default. Properties as set by the script: capital 10,000, commission 0.05%, slippage 2 ticks, margin 0, bar detalization off.
3. From the Strategy Tester, write `tests/fixtures/tv_summary.csv` with columns `metric,value` and these rows: `trade_count`, `profit_factor`, `net_pnl`, `winning_trades`, `max_drawdown`, `chart_timezone` (`Europe/Zurich`), `first_loaded_candle` (optional).
4. From the list of trades, write `tests/fixtures/tv_trades.csv` with columns `number,side,entry_time,entry_price,exit_time,exit_price,exit_comment,net_pnl`. Times as shown in the chart time zone, format `YYYY-MM-DD HH:MM`. `side` is `long` or `short`. An empty `exit_comment` is not checked. Trades: #1 to #6, #44, #136 to #141, #153, #167 to #172 (#44 and #153 are reversals, which check position sizing).

`configs/ema_vwap_parity.toml` holds the same window in UTC: 2025-12-31 23:00 to 2026-10-23 22:00.

## Credits

The design borrows ideas from [backtesting.py](https://github.com/kernc/backtesting.py), [Freqtrade](https://github.com/freqtrade/freqtrade) and [NautilusTrader](https://github.com/nautechsystems/nautilus_trader). No code is copied from them. Code taken from permissively licensed projects is credited where it is used.

## Disclaimer

This is a research tool, not financial advice. A strategy that passes every test here can still lose money.

## License

[MIT](LICENSE)
