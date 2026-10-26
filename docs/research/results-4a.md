# Phase 4a results: H1 to H5, H7 and H8 on BTCUSDT 1h

The single runs of the approved hypotheses in [hypotheses.md](hypotheses.md). H6 was not run. Nothing was combined and nothing ran on ETHUSDT or SOLUSDT.

## Result

**No hypothesis passes its success criteria.** Under the combination rule in hypotheses.md, no combination can be built and nothing is a candidate for ETHUSDT.

| ID | Verdict | What decided it |
|---|---|---|
| H1 4h, lengths in bars | fail | Fee share halved, but gross PF fell too (1.13 vs 1.24). Second half negative. 2h and 8h no plateau. |
| H2 fixed_risk | fail | Every own criterion holds except the plateau: risk 1.5% has PF 1.15 (needs 1.2). The run criteria fail on PF 1.21 < 1.3. |
| H3 confirm N bars | fail | PF not above the base in either half, and the fee share is not lower. Later entries cost the top-1% winners 42 points of move. |
| H4 breakeven at K ATR | fail | Better than the base at all three K in both halves, and the top 1% are untouched. Too small: PF 1.11 to 1.13, no plateau at 1.2. |
| H5 ATR trail | fail | Cuts all 17 top-1% winners (sum of their moves 297% to 206%). PF below the base in both halves. |
| H7 long only | fail | Only on PF: 1.27 < 1.3. Both halves positive, without top 5 and without top 1% positive, max DD 31.9%. |
| H8 4h, 24-hour VWAP | fail | Net negative at all three VWAP lengths. |

H2, H4 and H7 each improve both halves over the base, but none of them passes alone. The rule allows a combination only of hypotheses that passed individually, so they cannot be combined without a change to the rule.

## Setup

- Base: `configs/ema_vwap_full.toml`, BTCUSDT 1h, 2018-01-01 to 2026-01-01, fees 0.05% per side, 2 ticks slippage, pessimistic fills, percent_equity 100% except H2.
- Reference: run `runs/20261025T215500Z-ema_vwap_full` (the diagnosis run). A rerun on commit 3623b75 (`runs/20261025T235625Z-ema_vwap_full`) produced a trades.csv byte-identical to the reference run, with the same config hash.
- Specs: `configs/sweeps/*.toml`, one per hypothesis (H5 in two files). Every point is a logged run: 21 runs, all on commit 3623b75. The tree was dirty only because each run appends to `experiments/log.jsonl`.
- Plug-ins: `confirm` (H3), `breakeven` (H4) and `atr_trail` (H5) in `strategies/plugins.py`, as written in hypotheses.md.
- Compare reports for each base point are in `reports/compare-20261025T215500Z-ema_vwap_full-vs-*.html` (local, not committed).

## How to read the tables

- **PF net, PF gross, Net PnL, halves:** in USD as in the run report. Halves are split at 2022-01-01 by exit time. The criteria use these values.
- **Fee share:** fees as a share of gross profit, on percent returns per trade, as in diagnosis.md.
- **w/o top 5 / top 1%:** net PnL without the 5 best trades and without the best 1% (return method), as in the criteria.
- **Criteria:** the run's `[criteria]`: PF ≥ 1.3, at least 100 trades, positive without the top 5 and without the top 1%, positive in both halves.
- **Plateau:** every neighbor value has PF ≥ 1.2 and positive net PnL in both halves.
- **Compare columns:** trades are matched to the reference by side and entry time:
  - Disappeared: a reference trade has no match in the variant.
  - Appeared: a variant trade has no match in the reference.
  - Exit changed: matched, but a different exit.
  - Same exit: matched, with the same exit.
- **Top 1% (17):** the reference run's 17 best trades by percent return, and what the variant did on the same move:
  - same entry
  - later entry: a variant trade on the same side entered while the reference trade was open
  - earlier entry: a variant trade on the same side was already open at the reference entry
  - missing
- **Moves:** price moves (exit / entry − 1, by side), so sizing does not affect them. "Move same or better" counts winners whose variant move is at least the reference move. The reference top-1% moves sum to 297.2%.
- **Timeframe variants (H1, H8):** entry times are bar opens of the timeframe, so on 2h, 4h and 8h an exact entry match is rare. "Earlier entry" often only means the bucket opened before the 1h bar.

## H1: same logic on 4h, lengths in bars

| Point | Trades | PF net | PF gross | Net PnL | PF 1st / 2nd half | Net 1st / 2nd half | Fee share 1st / 2nd | w/o top 5 / top 1% | Max DD | Criteria |
|---|---|---|---|---|---|---|---|---|---|---|
| ema_vwap_full (reference) | 1695 | 1.09 | 1.24 | 26,769 | 1.21 / 0.98 | 29,501 / -2,732 | 7.8% / 14.3% | 8,055 / -1,025 | 57.4% | fail |
| timeframe 2h | 789 | 1.05 | 1.14 | 3,882 | 1.16 / 0.92 | 6,864 / -2,982 | 5.7% / 9.9% | -640 / -1,571 | 53.2% | fail |
| **timeframe 4h (base)** | 356 | 1.07 | 1.13 | 3,200 | 1.25 / 0.82 | 6,846 / -3,646 | 3.4% / 7.6% | -1,667 / -1,285 | 72.7% | fail |
| timeframe 8h | 184 | 1.27 | 1.32 | 13,814 | 1.63 / 0.96 | 14,901 / -1,087 | 2.0% / 4.4% | -818 / 3,175 | 67.7% | fail |

| Point | Disappeared | Appeared | Exit changed | Same exit | Top 1% (17) | Same exit | Move same or better | Top 1% moves, sum | Median giveback of winners | PF on % returns 1st / 2nd |
|---|---|---|---|---|---|---|---|---|---|---|
| timeframe 2h | 1633 | 727 | 62 | 0 | earlier entry 6, later entry 6, missing 3, same entry 2 | 0 | 6 | 232.0% | 3.3% | 1.31 / 0.96 |
| timeframe 4h | 1681 | 342 | 14 | 0 | earlier entry 9, later entry 2, missing 6 | 0 | 8 | 257.8% | 5.2% | 1.52 / 0.90 |
| timeframe 8h | 1692 | 181 | 3 | 0 | earlier entry 13, missing 4 | 0 | 10 | 494.6% | 7.6% | 2.12 / 1.08 |

Own criteria:
- Base 4h passes the criteria with at least 100 trades: **no**. It has 356 trades, but PF 1.07, a negative second half, and is negative without the top 5 and without the top 1%.
- Fee share below the 1h run's in both halves: **yes**, 3.4% vs 7.8% and 7.6% vs 14.3%.
- Plateau: **no**. 2h has PF 1.05 and a negative second half. 8h has PF 1.27 but a negative second half.

The cost side of the mechanism worked: fewer round trips and a much lower fee share. The gross edge did not carry over. PF before fees fell from 1.24 to 1.13 on 4h, and the second half stays negative at every timeframe. Max drawdown on 4h rose to 72.7%. 8h is the best point, but it is a neighbor, not the base, and it fails too.

## H2: fixed_risk sizing

| Point | Trades | PF net | PF gross | Net PnL | PF 1st / 2nd half | Net 1st / 2nd half | Fee share 1st / 2nd | w/o top 5 / top 1% | Max DD | Criteria |
|---|---|---|---|---|---|---|---|---|---|---|
| ema_vwap_full (reference) | 1695 | 1.09 | 1.24 | 26,769 | 1.21 / 0.98 | 29,501 / -2,732 | 7.8% / 14.3% | 8,055 / -1,025 | 57.4% | fail |
| risk_pct 0.75 | 1695 | 1.23 | 1.46 | 15,870 | 1.44 / 1.16 | 8,207 / 7,664 | 8.9% / 14.4% | 7,411 / 735 | 14.1% | fail |
| **risk_pct 1.0 (base)** | 1695 | 1.21 | 1.42 | 26,065 | 1.42 / 1.13 | 13,920 / 12,145 | 8.7% / 14.2% | 11,538 / 1,048 | 16.2% | fail |
| risk_pct 1.5 | 1695 | 1.15 | 1.34 | 32,322 | 1.34 / 1.07 | 22,396 / 9,926 | 8.5% / 14.2% | 13,336 / 780 | 30.5% | fail |

| Point | Disappeared | Appeared | Exit changed | Same exit | Top 1% (17) | Same exit | Move same or better | Top 1% moves, sum | Median giveback of winners | PF on % returns 1st / 2nd |
|---|---|---|---|---|---|---|---|---|---|---|
| risk_pct 0.75 | 0 | 0 | 0 | 1695 | same entry 17 | 17 | 17 | 297.2% | 2.3% | 1.53 / 1.19 |
| risk_pct 1.0 | 0 | 0 | 0 | 1695 | same entry 17 | 17 | 17 | 297.2% | 2.3% | 1.55 / 1.17 |
| risk_pct 1.5 | 0 | 0 | 0 | 1695 | same entry 17 | 17 | 17 | 297.2% | 2.3% | 1.50 / 1.10 |

Trades capped at 100% of equity: 12.0% (0.75), 23.5% (1.0), 51.6% (1.5), close to the expected 10%, 25% and 50%.

Own criteria:
- Without top 5 and without top 1% higher than the base: **yes** (11,538 vs 8,055; 1,048 vs -1,025).
- Max drawdown lower: **yes** (16.2% vs 57.4%).
- PF net at least the base's in both halves: **yes** (1.42 vs 1.21; 1.13 vs 0.98).
- Plateau: **no**. risk 0.75 holds (PF 1.23, both halves positive). risk 1.5 has PF 1.15, below 1.2, with both halves positive.
- The run criteria fail on PF only (1.21 < 1.3).

Same trades and exits as the base, so the change is purely in sizing. PF falls as risk rises: at 1.5% half the trades are capped at 100% of equity, so the sizing is close to the base's. Under the written rule H2 fails, by the plateau, on the 1.5 neighbor.

## H3: entry confirmation after N bars

| Point | Trades | PF net | PF gross | Net PnL | PF 1st / 2nd half | Net 1st / 2nd half | Fee share 1st / 2nd | w/o top 5 / top 1% | Max DD | Criteria |
|---|---|---|---|---|---|---|---|---|---|---|
| ema_vwap_full (reference) | 1695 | 1.09 | 1.24 | 26,769 | 1.21 / 0.98 | 29,501 / -2,732 | 7.8% / 14.3% | 8,055 / -1,025 | 57.4% | fail |
| bars 1 | 1577 | 1.07 | 1.21 | 17,801 | 1.23 / 0.94 | 27,237 / -9,435 | 7.7% / 14.8% | 4,773 / -1,326 | 56.7% | fail |
| **bars 2 (base)** | 1514 | 1.06 | 1.21 | 12,586 | 1.21 / 0.93 | 19,956 / -7,370 | 7.9% / 15.0% | 2,956 / -1,699 | 56.1% | fail |
| bars 3 | 1440 | 1.07 | 1.21 | 12,066 | 1.21 / 0.95 | 16,584 / -4,518 | 7.9% / 14.5% | 2,813 / -1,545 | 59.6% | fail |

| Point | Disappeared | Appeared | Exit changed | Same exit | Top 1% (17) | Same exit | Move same or better | Top 1% moves, sum | Median giveback of winners | PF on % returns 1st / 2nd |
|---|---|---|---|---|---|---|---|---|---|---|
| bars 1 | 1695 | 1577 | 0 | 0 | later entry 17 | 16 | 5 | 273.5% | 2.3% | 1.42 / 0.97 |
| bars 2 | 1695 | 1514 | 0 | 0 | later entry 17 | 15 | 2 | 254.7% | 2.3% | 1.38 / 0.96 |
| bars 3 | 1695 | 1440 | 0 | 0 | later entry 17 | 15 | 2 | 249.0% | 2.2% | 1.36 / 0.98 |

Every entry moves to a later bar, so no trade matches the reference by entry time ("disappeared" and "appeared" are the same moves, shifted).

Own criteria:
- PF net above the base in both halves: **no** (1.21 vs 1.21, 0.93 vs 0.98).
- Fee share lower than the base's: **no** (7.9% / 15.0% vs 7.8% / 14.3%).
- Criteria and plateau: **no**.
- At least 15 of the 17 top-1% winners still taken: **yes**, all 17, with a later entry.

The filter removes only 7 to 15% of the trades, far fewer than the noise crosses it was meant to skip, and the later entry costs the winners more than it saves. The top-1% moves fall from 297% to 255% at N 2.

## H4: breakeven stop after K ATR

| Point | Trades | PF net | PF gross | Net PnL | PF 1st / 2nd half | Net 1st / 2nd half | Fee share 1st / 2nd | w/o top 5 / top 1% | Max DD | Criteria |
|---|---|---|---|---|---|---|---|---|---|---|
| ema_vwap_full (reference) | 1695 | 1.09 | 1.24 | 26,769 | 1.21 / 0.98 | 29,501 / -2,732 | 7.8% / 14.3% | 8,055 / -1,025 | 57.4% | fail |
| k 1.5 | 1696 | 1.13 | 1.31 | 43,332 | 1.30 / 1.01 | 40,300 / 3,032 | 8.3% / 15.8% | 14,205 / 73 | 45.7% | fail |
| **k 2.0 (base)** | 1696 | 1.11 | 1.28 | 41,404 | 1.25 / 1.01 | 39,179 / 2,224 | 8.1% / 15.0% | 13,489 / -55 | 51.4% | fail |
| k 3.0 | 1696 | 1.10 | 1.26 | 31,962 | 1.22 / 1.00 | 31,490 / 471 | 8.0% / 14.5% | 9,983 / -681 | 52.6% | fail |

| Point | Disappeared | Appeared | Exit changed | Same exit | Top 1% (17) | Same exit | Move same or better | Top 1% moves, sum | Median giveback of winners | PF on % returns 1st / 2nd |
|---|---|---|---|---|---|---|---|---|---|---|
| k 1.5 | 0 | 1 | 337 | 1358 | same entry 17 | 17 | 17 | 297.2% | 2.3% | 1.49 / 1.05 |
| k 2.0 | 0 | 1 | 212 | 1483 | same entry 17 | 17 | 17 | 297.2% | 2.3% | 1.47 / 1.05 |
| k 3.0 | 0 | 1 | 95 | 1600 | same entry 17 | 17 | 17 | 297.2% | 2.3% | 1.42 / 1.04 |

Own criteria:
- PF net above the base in both halves: **yes** (1.25 vs 1.21, 1.01 vs 0.98).
- Criteria: **no**. PF is 1.11, and without the top 1% it is -55. Both halves are positive.
- At least 15 of 17 top-1% winners keep the same or a better exit: **yes**, 17 of 17 keep the same exit.
- Plateau: **no**. All three K have positive halves, but PF 1.13 and 1.10 are below 1.2.

The mechanism works as described. A breakeven exit replaces a later loss in 95 to 337 trades, and the outlier winners are untouched. The effect is too small to reach the thresholds. The one appeared trade (short, 2020-06-29 08:00) is a cross the base could not act on because it was still in the short that the breakeven stop had closed.

## H5: ATR trailing stop after a strong move

| Point | Trades | PF net | PF gross | Net PnL | PF 1st / 2nd half | Net 1st / 2nd half | Fee share 1st / 2nd | w/o top 5 / top 1% | Max DD | Criteria |
|---|---|---|---|---|---|---|---|---|---|---|
| ema_vwap_full (reference) | 1695 | 1.09 | 1.24 | 26,769 | 1.21 / 0.98 | 29,501 / -2,732 | 7.8% / 14.3% | 8,055 / -1,025 | 57.4% | fail |
| **k 3, t 3.0 (base)** | 1696 | 1.06 | 1.22 | 13,622 | 1.20 / 0.93 | 20,704 / -7,082 | 8.4% / 15.6% | 4,233 / -1,448 | 56.2% | fail |
| k 3, t 2.0 | 1696 | 1.04 | 1.19 | 6,649 | 1.17 / 0.89 | 14,063 / -7,414 | 8.7% / 16.4% | 1,581 / -1,625 | 57.1% | fail |
| k 3, t 4.0 | 1696 | 1.08 | 1.23 | 20,866 | 1.21 / 0.97 | 24,706 / -3,840 | 8.1% / 14.9% | 6,387 / -1,213 | 53.0% | fail |
| k 2.0, t 3 | 1696 | 1.07 | 1.22 | 15,346 | 1.21 / 0.94 | 22,163 / -6,816 | 8.4% / 15.7% | 4,983 / -1,287 | 54.7% | fail |
| k 4.0, t 3 | 1696 | 1.06 | 1.21 | 12,758 | 1.20 / 0.93 | 19,403 / -6,645 | 8.2% / 15.3% | 3,857 / -1,529 | 59.3% | fail |

| Point | Disappeared | Appeared | Exit changed | Same exit | Top 1% (17) | Same exit | Move same or better | Top 1% moves, sum | Median giveback of winners | PF on % returns 1st / 2nd |
|---|---|---|---|---|---|---|---|---|---|---|
| k 3, t 3.0 | 0 | 1 | 325 | 1370 | same entry 17 | 0 | 1 | 205.9% | 2.2% | 1.36 / 0.96 |
| k 3, t 2.0 | 0 | 1 | 405 | 1290 | same entry 17 | 0 | 1 | 135.6% | 1.8% | 1.30 / 0.92 |
| k 3, t 4.0 | 0 | 1 | 216 | 1479 | same entry 17 | 3 | 7 | 237.9% | 2.3% | 1.38 / 1.01 |
| k 2.0, t 3 | 0 | 1 | 399 | 1296 | same entry 17 | 0 | 1 | 205.9% | 2.2% | 1.37 / 0.97 |
| k 4.0, t 3 | 0 | 1 | 264 | 1431 | same entry 17 | 0 | 1 | 205.9% | 2.2% | 1.34 / 0.97 |

Own criteria:
- PF net above the base in both halves: **no** (1.20 vs 1.21, 0.93 vs 0.98).
- Criteria: **no**.
- At least 15 of 17 top-1% winners keep the same or a better exit: **no**, 1 of 17.
- Median giveback of winners lower: marginally, 2.2% vs 2.3%.
- Plateau: **no**.

The main risk in the hypothesis happened. The trail exits the outlier runs on a pullback, and the sum of their moves drops from 297% to 206% at T 3. Activation K does not change the top-1% result (205.9% at K 2, 3 and 4), presumably because those runs pass every activation level long before the trail stops them. A wider trail is less bad: T 4 is the best H5 point, and it is still below the base.

## H7: long only, the spot-executable variant

| Point | Trades | PF net | PF gross | Net PnL | PF 1st / 2nd half | Net 1st / 2nd half | Fee share 1st / 2nd | w/o top 5 / top 1% | Max DD | Criteria |
|---|---|---|---|---|---|---|---|---|---|---|
| ema_vwap_full (reference) | 1695 | 1.09 | 1.24 | 26,769 | 1.21 / 0.98 | 29,501 / -2,732 | 7.8% / 14.3% | 8,055 / -1,025 | 57.4% | fail |
| **direction Long only** | 892 | 1.27 | 1.46 | 23,879 | 1.41 / 1.18 | 13,184 / 10,695 | 7.6% / 13.0% | 8,021 / 3,368 | 31.9% | fail |

| Point | Disappeared | Appeared | Exit changed | Same exit | Top 1% (17) | Same exit | Move same or better | Top 1% moves, sum | Median giveback of winners | PF on % returns 1st / 2nd |
|---|---|---|---|---|---|---|---|---|---|---|
| direction Long only | 803 | 0 | 0 | 892 | missing 6, same entry 11 | 11 | 11 | 184.7% | 2.1% | 1.53 / 1.23 |

Own criteria:
- Criteria: **no**, on PF only: 1.27 < 1.3. Trades (892), without top 5 (8,021) and without top 1% (3,368) pass, and both halves are positive.
- Top-1% check on the 11 long winners: **yes**, all 11 have the same entry and exit. The 6 short winners are gone by construction.
- No plateau rule (no neighbors).

All 892 long trades are identical to the base's longs, and the 803 shorts disappeared. The 4 reversals in the base become plain exits on the same bar, so no long trade changes. With only the costs a spot account pays, the long side alone is positive in both halves and has a third of the base's drawdown. It misses the PF threshold by 0.03.

## H8: 4h with a 24-hour VWAP

| Point | Trades | PF net | PF gross | Net PnL | PF 1st / 2nd half | Net 1st / 2nd half | Fee share 1st / 2nd | w/o top 5 / top 1% | Max DD | Criteria |
|---|---|---|---|---|---|---|---|---|---|---|
| ema_vwap_full (reference) | 1695 | 1.09 | 1.24 | 26,769 | 1.21 / 0.98 | 29,501 / -2,732 | 7.8% / 14.3% | 8,055 / -1,025 | 57.4% | fail |
| vwap_bars 4 | 1067 | 0.83 | 0.91 | -2,494 | 0.86 / 0.78 | -1,473 / -1,021 | 8.2% / 12.1% | -2,705 / -2,813 | 85.7% | fail |
| **vwap_bars 6 (base)** | 1077 | 0.99 | 1.10 | -461 | 1.12 / 0.84 | 3,818 / -4,279 | 7.4% / 13.2% | -1,517 / -2,116 | 69.2% | fail |
| vwap_bars 9 | 1243 | 0.97 | 1.06 | -1,093 | 0.99 / 0.92 | -113 / -981 | 7.4% / 12.5% | -2,188 / -2,710 | 64.5% | fail |

| Point | Disappeared | Appeared | Exit changed | Same exit | Top 1% (17) | Same exit | Move same or better | Top 1% moves, sum | Median giveback of winners | PF on % returns 1st / 2nd |
|---|---|---|---|---|---|---|---|---|---|---|
| vwap_bars 4 | 1678 | 1050 | 17 | 0 | earlier entry 9, missing 8 | 0 | 0 | 45.0% | 0.7% | 0.94 / 0.81 |
| vwap_bars 6 | 1646 | 1028 | 49 | 0 | earlier entry 6, later entry 4, missing 6, same entry 1 | 0 | 0 | 54.2% | 0.9% | 1.19 / 0.82 |
| vwap_bars 9 | 1644 | 1192 | 51 | 0 | earlier entry 8, later entry 9 | 0 | 2 | 164.9% | 1.6% | 1.05 / 0.95 |

Own criteria (general rules, compared with the base and with H1): **fail** at every point. It is worse than the 1h base and worse than H1's 4h point (PF 1.07). With the VWAP shorter than or close to EMA 9 bars, the two lines cross about 3 times as often as on H1's 4h point (1,077 vs 356 trades). The outlier runs are cut early: the top-1% moves sum to 45% to 165%.

## Holdout data status

Downloaded on 2026-10-26, one after the other. No strategy ran on them.

- **ETHUSDT 1h**, 2018-01 to 2026-10-24: check OK.
  - 77,089 candles; 28 gaps with 167 missing candles, the largest 75 candles on 2018-02-08 to 02-11.
  - 43 off-grid candles excluded (2018-02-09 to 02-11, as with BTC); 4 zero-trade placeholder candles excluded; 8 partial candles kept.
- **SOLUSDT 1h**, 2020-08-11 to 2026-10-24: check **FAILED** on one candle.
  - 54,356 candles; 10 gaps with 22 missing candles, the largest 4.
  - The 2021-12-24 04:00 candle has a close time of 05:00:00.475 in Binance's own monthly file (`SOLUSDT-1h-2021-12.zip`, close_time 1640322000475). That is 475 ms after its hour ends, so the check rejects it as a wrong close time. BTC and ETH have a partial candle at the same hour that closes inside it.
  - Not changed. How to treat it is open.
