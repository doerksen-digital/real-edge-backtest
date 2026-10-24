# real-edge-backtest

An honest backtesting tool for short-term crypto strategies.

Most backtests look better than reality because they peek at future candles, ignore costs, or test so many variants that one wins by luck. This project is built to make all three hard to do by accident.

> **Status:** Phase 0 (project setup). Nothing is usable yet. See the [plan](docs/PLAN.md) for what comes next.

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

## Credits

The design borrows ideas from [backtesting.py](https://github.com/kernc/backtesting.py), [Freqtrade](https://github.com/freqtrade/freqtrade) and [NautilusTrader](https://github.com/nautechsystems/nautilus_trader). No code is copied from them. Code taken from permissively licensed projects is credited where it is used.

## Disclaimer

This is a research tool, not financial advice. A strategy that passes every test here can still lose money.

## License

[MIT](LICENSE)
