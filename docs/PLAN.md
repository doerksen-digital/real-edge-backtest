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
| Lockbox | No hard lockbox. Any window can be run at any time. The experiment log records every tested window and the report shows how much of its window was seen before. |
| Dependencies | Current releases, bumped deliberately. A lockfile for reproducibility follows in phase 3 part B. |

## What gets reused

| Source | License | How it is used |
|---|---|---|
| [binance/binance-public-data](https://github.com/binance/binance-public-data) | MIT | Download logic and checksum verification for historical candles |
| [QuantStats](https://github.com/ranaroussi/quantstats) | Apache 2.0 | Optional extra `report`: period-based metrics section of the report. Trade metrics are always our own. |
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
  analysis/     trade metrics from run folders
  experiments/  append-only run log, variant count and seen-window check
  report/       HTML report, optional QuantStats section
  cli.py        data download, data check, run, report
```

Two fill models exist in the engine:

- **TradingView-compatible**, used for the parity test. It follows TradingView's documented bar path: if the open is nearer the high, the path is open, high, low, close, otherwise open, low, high, close.
- **Pessimistic**, the default for real research. If a stop and a target are both inside one candle, the stop is assumed to fill first.

## Phases

| Phase | Result | Done when |
|---|---|---|
| 0. Setup | Repository, license, README, project config, CI | The empty project installs and the tests run on GitHub |
| 1. Data | BTCUSDT 1h spot from 2018 to today | Checksums pass, no duplicates, all gaps listed and never filled, all times in UTC |
| 2. Engine and parity | EMA 9 / rolling VWAP strategy in Python | Same trade list as the TradingView run for 2026 (entry times and sides), profit factor and trade count within a small tolerance, lookahead test passes |
| 3. Report and log | Part A (built): trade metrics, HTML report, experiment log with seen-window check, readiness rule, gap rules, sizing modes. Part B: lockfile. | Every run can be reproduced from its log entry |
| 4. Robustness | Parameter grid, walk-forward, cost stress, Monte Carlo, ETH and SOL | EMA/VWAP goes through the full test on 2018 to 2026 |
| 5. Futures | Real funding history, leverage, liquidation, fees on notional | The same strategy runs on perpetuals with honest costs |
| 6. Later | UI, live signals, paper trading | Only after phase 4 shows an edge |

The exchange research happens between phase 2 and phase 3.

## Phase 3 part A as built

- **Trade metrics** (`analysis/metrics.py`) read only the run files. Every equity-based number uses the equity curve cut to the run window.
- **HTML report** (`real-edge-backtest report --run <dir>`): one self-contained file with header, pass criteria, trade metrics, buy and hold, charts, per-year and halves tables, gap sensitivity, the trade list and an optional QuantStats section.
- **Experiment log** (`experiments/log.jsonl`): append-only, one line per run, variant count per strategy family, seen-window check before each run.
- **Readiness:** indicators use all history before Start. No trade until every indicator, including the previous day's daily values, exists. A warning appears if Start is less than 30 days after the first candle.
- **Gaps:** positions survive gaps, a stop gapped past fills at the open, entries wait after gaps of 3 or more missing candles until the indicators have enough contiguous candles, and trades across gaps are marked.
- **Sizing:** `percent_equity` (default, parity), `fixed_risk`, `fixed_notional`, capped at 100% of equity.

Part B adds a lockfile so a run can be reproduced with the exact package versions. Its purpose is reproducibility.

## Phase 4a: diagnosis and hypotheses

Built on `feat/phase-4a-research`: ETH and SOL holdout data behind `--holdout`, cost, side, tail and rolling sections in the report, `trades_enriched.csv` (entry features and excursions), `report --compare`, `sweep`, entry filter and exit plug-ins (with deferred entries), higher timeframes built from 1h, and `analysis/diagnosis.py`. The BTC diagnosis is in [research/diagnosis.md](research/diagnosis.md), the hypotheses in [research/hypotheses.md](research/hypotheses.md). Hypotheses run only after the list is approved.

## Seen and unseen data

EMA 21 for the daily trend filter was chosen on TradingView on January to October 2026. For `ema_vwap` that window is seen. 2018 to 2025 is unseen. The experiment log starts with those TradingView runs, so every report on 2026 shows the window as seen.

## Test scope at the start

Covered by unit tests:

- fill price, fees and slippage
- intrabar stops in both fill models
- stop-and-reverse
- PnL and equity accounting
- indicator values against reference values
- the lookahead test: cutting the data at a random point must not change any earlier signal

Added in phase 3: trade metrics, the report, the experiment log, readiness, gap rules and sizing modes. Not covered yet: data download.

## Research protocol

Applies from phase 4a on. Every hypothesis run follows it.

- **Development data:** BTCUSDT 1h, 2018-01-01 to the latest data. Exploration is allowed here.
- **Validation data:** ETHUSDT 1h. **Final test:** SOLUSDT 1h, then paper trading.
- No strategy runs on ETH or SOL during development. Only a short list of the best candidates is ever run on ETH, later and unchanged. The engine refuses a run on ETHUSDT or SOLUSDT without `--holdout`; with it, the run is marked as a holdout run in `run.json`, the experiment log and the report.
- Every hypothesis needs a market mechanism (why it should work), a precise rule, at most 2 free parameters, and its neighbor values, all written down before it is run.
- No rules that filter trades by their outcome. No calendar rules (hour, weekday) unless there is a clear mechanism.
- Fees stay 0.05% per side, slippage 2 ticks, fill model pessimistic, sizing percent_equity unless the hypothesis is about sizing.

## Pass criteria for a strategy

Fixed before a test runs. Net of fees and slippage:

- profit factor of at least 1.3
- enough trades to mean something
- still positive without the best trades
- positive in both halves of the test period
- compared against buy and hold on return, drawdown and time in the market

The thresholds sit in the run config's `[criteria]` section, so they are fixed before the run and recorded with it. Robustness tests (neighbor parameters, walk-forward, unseen windows) are judged against criteria written down before each run.

## Out of scope for now

Tick data, order book simulation, machine learning, automatic order execution.

## Data license

The Binance Vision dataset terms (v1.0, 2026-08-26) license data.binance.vision under CC BY-NC-SA 4.0 and allow only personal, non-production backtesting research. Live signals and paper trading in phase 6 cannot use this data under these terms. They need a different data source or a license review first.
