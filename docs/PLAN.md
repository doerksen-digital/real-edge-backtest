# Project plan

This document records what real-edge-backtest is for, the decisions behind it, and the order in which it gets built. It changes only when a decision changes.

## Goal

Find out honestly whether a trading strategy has a real edge before any money goes into it.

The first target is short-term crypto strategies on 1h to 1d candles, starting with BTCUSDT. ETH, SOL and other coins come later. Futures with leverage come only after a strategy has survived the full spot test.

## Principles

1. **Honest before fast or pretty.** The engine may only see closed candles, every cost is modeled, and every run is logged.
2. **Reuse before rebuild.** Permissively licensed code is used as a dependency or copied with attribution. Copyleft projects are studied for their design only.
3. **Rules are fixed before results are seen.** Pass criteria are written down before a test runs.
4. **The engine knows nothing about reports or UIs.** It writes result files. Everything else only reads them.

## Decisions

| Topic | Decision |
|---|---|
| Language | Python |
| License | MIT |
| Repository | `doerksen-digital/real-edge-backtest`, public |
| Where it runs | Locally (ThinkPad), built with Claude Code |
| Engine | Own bar-by-bar loop. Design borrowed, no code copied from copyleft projects. |
| Market data | Binance public data archive, starting with BTCUSDT spot 1h from 2018 |
| Fees | One fee profile per exchange, chosen in the run config |
| Exchange choice | Researched after phase 2: cheapest exchange that is still safe for a Swiss resident, for spot and perpetuals |
| Interface | CLI and HTML report first, UI later on top of the same result files |
| Tests | Unit tests for the core engine only in the beginning |

## What gets reused

| Source | License | How it is used |
|---|---|---|
| [binance/binance-public-data](https://github.com/binance/binance-public-data) | MIT | Download logic and checksum verification for historical candles |
| [QuantStats](https://github.com/ranaroussi/quantstats) | Apache 2.0 | Dependency for return-based metrics and the tearsheet part of the report |
| [backtesting.py](https://github.com/kernc/backtesting.py) | AGPL-3.0 | Design only: strategy class with `init()` and `next()`, `Backtest(data).run()` |
| [Freqtrade](https://github.com/freqtrade/freqtrade) | GPL-3.0 | Design only: lookahead and recursive-formula analysis. Later a second reference engine for cross-checks. |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | LGPL-3.0 | Design only: the same strategy code runs in backtest and live |
| [vectorbt](https://github.com/polakowo/vectorbt) | Apache 2.0 with Commons Clause | Not used for now. Possible later for fast parameter sweeps. |

## Architecture

```
src/real_edge_backtest/
  data/         download, checksum check, Parquet store, gap and duplicate check
  indicators/   EMA, ATR, rolling VWAP and others, defined the same way as TradingView
  engine/       bar loop, broker (orders, fills, fees, slippage, stops), positions
  strategies/   one module per strategy, starting with ema_vwap
  analysis/     trade metrics plus QuantStats metrics
  experiments/  append-only run log and lockbox
  report/       HTML report
  cli.py        download, run, report, robustness
```

Two fill models exist in the engine:

- **TradingView-compatible**, used for the parity test. It follows TradingView's documented bar path: if the open is nearer the high, the path is open, high, low, close, otherwise open, low, high, close.
- **Pessimistic**, the default for real research. If a stop and a target are both inside one candle, the stop is assumed to fill first.

## Phases

| Phase | Result | Done when |
|---|---|---|
| 0. Setup | Repository, license, README, project config, CI | The empty project installs and the tests run on GitHub |
| 1. Data | BTCUSDT 1h spot from 2018 to today | Checksums pass, no gaps or duplicates, all times in UTC |
| 2. Engine and parity | EMA 9 / rolling VWAP strategy in Python | Same trade list as the TradingView run for 2026 (entry times and sides), profit factor and trade count within a small tolerance, lookahead test passes |
| 3. Report and log | One command produces the HTML report and a log entry | Every run can be reproduced from its log entry |
| 4. Robustness | Parameter grid, walk-forward, lockbox, cost stress, Monte Carlo, ETH and SOL | EMA/VWAP goes through the full test on 2018 to 2026 |
| 5. Futures | Real funding history, leverage, liquidation, fees on notional | The same strategy runs on perpetuals with honest costs |
| 6. Later | UI, live signals, paper trading | Only after phase 4 shows an edge |

The exchange research happens between phase 2 and phase 3.

## Test scope at the start

Covered by unit tests:

- fill price, fees and slippage
- intrabar stops in both fill models
- stop-and-reverse
- PnL and equity accounting
- indicator values against reference values
- the lookahead test: cutting the data at a random point must not change any earlier signal

Not covered yet: reports, CLI, data download.

## Pass criteria for a strategy

Fixed before a test runs. Net of fees and slippage:

- profit factor of at least 1.3
- enough trades to mean something
- still positive without the best trades
- positive in both halves of the test period
- compared against buy and hold on return, drawdown and time in the market

Robustness tests (neighbor parameters, walk-forward, lockbox) are judged against criteria written down before each run.

## Out of scope for now

Tick data, order book simulation, machine learning, automatic order execution.
