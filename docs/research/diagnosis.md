# Diagnosis: ema_vwap_full on BTCUSDT 1h, 2018 to 2025

Descriptive only. No variant was run for this document.

- Run: `configs/ema_vwap_full.toml` (EMA 9 / VWAP 24, ATR 14 stop at 2 ATR, daily EMA 21 trend filter, pessimistic fills, 0.05% fees per side, 2 ticks slippage, 3,000 USD, percent_equity 100%), window 2018-01-01 to 2026-01-01 UTC, run folder `runs/20261025T215500Z-ema_vwap_full`, commit 0eb2f1a, clean tree. The trade list is identical to the earlier ema_vwap_full runs.
- Tables generated with `python -m real_edge_backtest.analysis.diagnosis runs/20261025T215500Z-ema_vwap_full` (`src/real_edge_backtest/analysis/diagnosis.py`) and copied below the findings.
- **Unit of account.** All aggregates are computed on percent returns on equity at entry, so every trade weighs the same. The run compounds at 100% of equity, so USD sums would be dominated by the later and larger trades. "Net" is the sum of percent returns. The profit factors here are on percent returns, so they differ from the USD profit factor in the report (1.087 net, 1.237 gross).
- **Groups.** Top 1% = the 17 best trades by net return, bottom 1% = the 17 worst, rest = the other 1,661. With 17 trades the top and bottom groups are too small for per-year or per-side conclusions. Cells under 30 trades are marked "few".
- **Halves.** The window is split at 2022-01-01 by exit time.

## Findings

### 1. The result is the top 1%

- The 17 best trades sum to +295% of the +303% total. The other 1,678 trades sum to about +7%, and the 1,661 "rest" trades have a PF of 1.08 net.
- The top 1% are slow trend trades. They were held a median of 66 bars, reached their MFE after a median of 46 bars, and had a median MFE of 22% and a median MAE of 0.7 ATR. All 17 exited on the opposite cross; none was stopped out.
- They spread over the years: 2, 3, 5, 3, 2, 1, 1, 0 from 2018 to 2025. There are none in 2025 and only one each in 2023 and 2024.
- At entry, the top 1% are not separable from the rest by any recorded feature. Median ATR %, separation, volume ratios and recent crosses overlap the rest (see the distribution tables). The top-1% longs are further above the daily EMA (median 8.3 ATR vs 6.5) and on a steeper daily slope (0.75%/day vs 0.44%). With 11 trades that is not evidence.

### 2. Giveback is large, and most of the payoff sits in trades that run beyond 5 ATR

- Winners (526) reached a median MFE of 4.4% but realized 1.6%: a median giveback of 2.3%, 57% of their MFE. 61% of winners realized less than half of their MFE.
- The top 1% gave back a median 5.0% (23% of their MFE).
- By the MFE a trade reached (in ATR at entry):

  | MFE reached | share of trades | ended as loser | sum of % returns |
  |---|---|---|---|
  | under 1 ATR | 39% | 99% | -802% |
  | 1 to 2 ATR | 18% | 89% | -273% |
  | 2 to 3 ATR | 12% | 68% | -97% |
  | 3 to 5 ATR | 13% | 35% | +122% |
  | 5 ATR or more | 18% | 9% | +1,352% |

  Trades that reached 2 to 3 ATR in profit still ended as losers 68% of the time (median realized -0.37 ATR). Trades that reached 3 to 5 ATR realized a median 0.63 ATR. The exit is the opposite EMA/VWAP cross, which comes late.
- The MFE profile in ATR units is the same in both halves: 18% of trades reach 5 ATR and 39 to 40% never reach 1 ATR in each half.
- 44% of losers had been at least 1 ATR in profit.

### 3. Losses come mainly from stop-outs, not from the mass of small losers

- Among losers (1,169), measured as share of the total loss in percent returns:
  - stopped out at the 2 ATR stop: 37% of losers, 57% of the loss
  - cross exits losing less than 0.5 ATR: 22% of losers, 7% of the loss
  - cross exits losing 0.5 to 1 ATR: 21% of losers, 14% of the loss
  - cross exits losing 1 ATR or more: 20% of losers, 22% of the loss
- The smallest half of all losers (each loss at most 0.87% of equity) makes 21% of the total loss.
- The many small losers are mainly a fee problem: for losers under 0.5 ATR, fees are 30% of their loss.
- The bottom 1% are high-volatility stop-outs: 14 of 17 hit the ATR stop, and their median ATR is 2.47% of price vs 0.73% for the rest. Seven of them are in 2018 and five in 2021.
- At 100% of equity and a 2 ATR stop, the money at risk per trade is twice the ATR %. That is a median 1.5% of equity, but 4 to 9% in the volatile bars where the bottom 1% happened. Sizing, not the signal, decides how large these losses are.

### 4. "Chop" in the sense of many recent crosses is not where the strategy loses

- Grouped by EMA/VWAP crosses in the 48 bars before entry:

  | crosses in 48 bars | trades | PF net |
  |---|---|---|
  | 0 to 1 | 449 | 0.77 |
  | 2 to 3 | 904 | 1.24 |
  | 4 to 5 | 282 | 2.28 |
  | 6 or more | 60 | 1.11 |

- Trades after many recent crosses do not do worse. They do better, with slightly lower ATR % (median 0.69% vs 0.83%) and a higher median MFE (2.0 vs 1.4 ATR).
- The weak spot is the opposite: the first cross after a long one-sided stretch.
  - No cross in the previous 24 bars: PF 0.98 in the first half and 0.75 in the second, 299 trades.
  - Exactly one cross in the previous 48 bars: PF 0.64 and 0.84, 423 trades.
  - These are the only cross-count bins with PF below 1 in both halves.
- The share of trades after 4 or more crosses rose from 14 to 17% (2018 to 2019) to 22 to 24% (2022 to 2025).
- A chop filter that skips trades after many recent crosses is therefore not supported by this data.
- **No consistent difference:**
  - EMA/VWAP separation at entry: Q4 is weak in both halves (0.93 and 0.66), but Q5 is not. There is no monotonic pattern and no mechanism for a middle band.
  - Volume vs its 24-bar average: flat.
  - Volume vs its 7-day average: the pattern reverses between halves.

### 5. Fees grow relative to the moves; the second half decays in both gross and net terms

- Average ATR at entry fell from 1.21% of price (2018) and 1.34% (2021) to 0.52 to 0.72% (2023 to 2025). Round-trip costs stay at 0.10% of notional.
- The mean round-trip cost as a share of the mean absolute gross move rose from 4.1% (2018) to 9.0% (2023) and 9.9% (2025). The fee share of gross profit doubled from 7.8% in the first half to 14.3% in the second.
- PF on percent returns, first half vs second half: net 1.40 vs 1.02, gross 1.55 vs 1.20. The decay is not only fees: gross PF fell too. Fees are what pushes 2022 (gross 0.94, net 0.83) and 2025 (gross 1.07, net 0.88) below 1.
- In ATR units the trade profile did not change between halves (see 2). The same pattern in a quieter market makes smaller percent moves against fixed percent costs.
- By side: longs PF 1.53 then 1.23, shorts 1.26 then 0.84. Shorts lost in the second half (-49% sum of returns); longs stayed positive.

### 6. Other entry features

- **Trend context of longs:** longs further above the daily EMA (Q3 and Q4 within longs, 5.3 to 11.4 ATR) did best. The extremes did not, and there is no monotonic pattern. For shorts, no pattern.
- **Daily EMA slope:** within longs, PF is 1.23 to 1.56 across the slope quintiles, with no monotonic pattern. Within shorts it is 0.82 to 1.44, also without a pattern. Across all trades the steepest down slopes are worst, which is the short side.
- **ATR %:** high-ATR trades were better in the first half (Q5 PF 1.32) and much worse in the second (0.50). Not stable.
- **Hour and weekday:** there are differences, for example Saturday entries with PF 0.86 and 0.71 in the two halves. The research protocol excludes calendar rules without a clear mechanism, so they are recorded but not used.
- **Reversals are rare:** with the trend filter almost every exit is "exit only" (1,254 cross exits, 437 stop-outs, 4 reversals). Between trades the strategy is flat.

## What this suggests, for the hypothesis list

- Outlier dependence follows from the payoff profile: 18% of trades reach 5 ATR and carry everything, and the exit gives a lot back. Exits that keep more of the 2 to 5 ATR moves are a candidate. They must not cut the 5+ ATR runs, which is where the edge, if any, sits.
- The large losers come from sizing at 100% of equity in volatile bars. Risk-based sizing addresses that without touching the signal.
- Fee drag grows as volatility falls. A higher timeframe has larger moves per trade against the same costs.
- The first cross after a long one-sided stretch is the one consistently weak entry type. That points to confirmation, not to a chop filter.
- Shorts decayed more than longs.

Caveat: about 20 feature splits were inspected here. Some patterns will be chance. Only patterns that hold in both halves, and have a mechanism, are used in docs/research/hypotheses.md.

## Tables (generated)

Run folder: `runs/20261025T215500Z-ema_vwap_full`. 1695 closed trades; top and bottom 1% = 17 trades each by net return on equity at entry. Cells with fewer than 30 trades are marked (few).

### Overview

| Group | Trades | PF net | PF gross | Net (sum of % returns) | Fee share of gross profit | Avg bars held | Win rate |
|---|---|---|---|---|---|---|---|
| all | 1695 | 1.232 | 1.398 | 302.6% | 10% | 17.9 | 31% |
| long | 892 | 1.402 | 1.596 | 258.9% | 10% | 18.9 | 32% |
| short | 803 | 1.066 | 1.205 | 43.8% | 11% | 16.9 | 30% |
| top 1% | 17 (few) | inf | inf | 295.3% | 1% | 69.9 | 100% |
| bottom 1% | 17 (few) | 0.000 | 0.000 | -94.1% |  | 10.4 | 0% |
| rest | 1661 | 1.084 | 1.244 | 101.5% | 12% | 17.5 | 31% |

### Giveback

| Trades | n | median MFE | median realized | median giveback | median giveback / MFE | realized < half of MFE | MFE >= 1 ATR |
|---|---|---|---|---|---|---|---|
| winners (net > 0) | 526 | 4.39% | 1.60% | 2.30% | 57% | 61% | 99% |
| top 1% | 17 (few) | 22.48% | 16.32% | 5.02% | 23% | 0% | 100% |
| losers (net <= 0) | 1169 | 0.60% | -0.77% | 1.55% | 230% | 100% | 44% |

By the MFE a trade reached:

| MFE reached | n | share of trades | median MFE (ATR) | median realized (ATR) | ended as loser | sum of % returns | exited by stop |
|---|---|---|---|---|---|---|---|
| 0 to 1 ATR | 663 | 39% | 0.361 | -1.289 | 99% | -801.7% | 39% |
| 1 to 2 ATR | 297 | 18% | 1.414 | -1.006 | 89% | -272.5% | 31% |
| 2 to 3 ATR | 211 | 12% | 2.459 | -0.370 | 68% | -97.2% | 24% |
| 3 to 5 ATR | 214 | 13% | 3.861 | 0.626 | 35% | 122.0% | 12% |
| >= 5 ATR | 310 | 18% | 8.269 | 4.406 | 9% | 1352.1% | 4% |

### Where the losses come from

| Losers | n | share of losers | sum of % returns | share of total loss | fees as share of their loss |
|---|---|---|---|---|---|
| stopped out (ATR stop) | 437 | 37% | -743.9% | 57% | 6% |
| cross exit, gross move against < 0.5 ATR | 261 | 22% | -86.0% | 7% | 30% |
| cross exit, 0.5 to 1 ATR | 243 | 21% | -188.7% | 14% | 13% |
| cross exit, >= 1 ATR | 228 | 20% | -284.6% | 22% | 8% |

Cumulative loss, losers sorted from the smallest loss:

| Losers, smallest first | n | largest loss in this set | share of total loss |
|---|---|---|---|
| smallest 10% | 117 | 0.24% | 1% |
| smallest 20% | 234 | 0.38% | 4% |
| smallest 30% | 351 | 0.54% | 8% |
| smallest 40% | 468 | 0.69% | 14% |
| smallest 50% | 585 | 0.87% | 21% |
| smallest 60% | 702 | 1.09% | 30% |
| smallest 70% | 819 | 1.35% | 41% |
| smallest 80% | 936 | 1.71% | 54% |
| smallest 90% | 1053 | 2.16% | 72% |
| smallest 100% | 1169 | 9.51% | 100% |

### Recent crosses (chop)

| Recent crosses | Trades | PF net | PF gross | Net (sum of % returns) | Fee share of gross profit | Avg bars held | Win rate | median ATR % | median separation (ATR) | median MFE (ATR) | median abs gross move |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0-1 crosses in 48 bars | 449 | 0.770 | 0.876 | -88.6% | 14% | 17.3 | 30% | 0.83% | 0.084 | 1.399 | 0.96% |
| 2-3 | 904 | 1.239 | 1.405 | 167.5% | 10% | 17.9 | 30% | 0.73% | 0.071 | 1.485 | 0.90% |
| 4-5 | 282 | 2.276 | 2.604 | 218.4% | 7% | 19.5 | 38% | 0.69% | 0.067 | 2.031 | 0.90% |
| 6+ | 60 | 1.114 | 1.268 | 5.3% | 11% | 16.1 | 27% | 0.65% | 0.079 | 1.134 | 0.96% |

| Year | trades | share with >= 4 crosses in 48 bars | mean crosses_48 |
|---|---|---|---|
| 2018 | 185 | 14% | 2.205 |
| 2019 | 214 | 17% | 2.533 |
| 2020 | 202 | 21% | 2.554 |
| 2021 | 214 | 16% | 2.397 |
| 2022 | 210 | 24% | 2.586 |
| 2023 | 226 | 24% | 2.752 |
| 2024 | 229 | 23% | 2.664 |
| 2025 | 215 | 22% | 2.614 |

### Fees and move size per year (by exit)

| Year | trades | mean ATR % at entry | mean abs gross move | median abs gross move | mean round-trip cost | cost / mean abs move | moves smaller than cost | PF gross | PF net |
|---|---|---|---|---|---|---|---|---|---|
| 2018 | 185 | 1.21% | 2.47% | 1.47% | 0.10% | 4.1% | 4% | 1.477 | 1.354 |
| 2019 | 214 | 0.85% | 1.71% | 0.87% | 0.10% | 5.9% | 7% | 1.908 | 1.659 |
| 2020 | 202 | 0.90% | 1.91% | 0.87% | 0.10% | 5.3% | 5% | 1.922 | 1.697 |
| 2021 | 214 | 1.34% | 2.37% | 1.78% | 0.10% | 4.2% | 2% | 1.207 | 1.107 |
| 2022 | 210 | 0.89% | 1.66% | 1.12% | 0.10% | 6.0% | 4% | 0.937 | 0.834 |
| 2023 | 226 | 0.52% | 1.12% | 0.54% | 0.10% | 9.0% | 8% | 1.474 | 1.217 |
| 2024 | 229 | 0.72% | 1.38% | 0.80% | 0.10% | 7.3% | 5% | 1.438 | 1.233 |
| 2025 | 215 | 0.60% | 1.01% | 0.68% | 0.10% | 9.9% | 6% | 1.067 | 0.878 |

### Entry features by quintile

Quintiles over all trades, then within the long and within the short trades; discrete features by value. PF and net from percent returns.

#### ATR % of price (`atr_pct`)

| Side | Bin | Trades | PF net | PF gross | Net (sum of % returns) | Fee share of gross profit | Avg bars held | Win rate |
|---|---|---|---|---|---|---|---|---|
| all | Q1 0.10% to 0.47% | 339 | 1.466 | 1.882 | 62.6% | 16% | 14.9 | 25% |
| all | Q2 0.47% to 0.64% | 339 | 1.837 | 2.177 | 149.9% | 10% | 18.3 | 31% |
| all | Q3 0.64% to 0.84% | 339 | 1.173 | 1.352 | 40.8% | 12% | 17.9 | 29% |
| all | Q4 0.84% to 1.18% | 339 | 0.970 | 1.085 | -9.2% | 11% | 19.4 | 33% |
| all | Q5 1.18% to 6.38% | 339 | 1.133 | 1.221 | 58.6% | 7% | 19.1 | 37% |
| long | Q1 0.11% to 0.47% | 179 | 1.729 | 2.185 | 52.5% | 14% | 15.4 | 28% |
| long | Q2 0.47% to 0.63% | 178 | 1.673 | 1.968 | 67.1% | 10% | 19.2 | 31% |
| long | Q3 0.63% to 0.80% | 178 | 1.313 | 1.520 | 36.6% | 11% | 17.1 | 30% |
| long | Q4 0.80% to 1.07% | 178 | 1.203 | 1.337 | 33.2% | 9% | 21.7 | 33% |
| long | Q5 1.08% to 4.46% | 179 | 1.363 | 1.485 | 69.4% | 7% | 21.1 | 38% |
| short | Q1 0.10% to 0.46% | 161 | 1.150 | 1.501 | 9.6% | 21% | 14.6 | 20% |
| short | Q2 0.46% to 0.65% | 160 | 2.186 | 2.624 | 88.6% | 9% | 17.6 | 34% |
| short | Q3 0.65% to 0.91% | 161 | 0.785 | 0.904 | -26.9% | 16% | 16.4 | 24% |
| short | Q4 0.91% to 1.29% | 160 | 0.936 | 1.054 | -9.0% | 12% | 18.9 | 35% |
| short | Q5 1.29% to 6.38% | 161 | 0.927 | 0.990 | -18.6% | 7% | 16.8 | 35% |

#### close - daily EMA, in ATR (`dist_daily_ema_atr`)

| Side | Bin | Trades | PF net | PF gross | Net (sum of % returns) | Fee share of gross profit | Avg bars held | Win rate |
|---|---|---|---|---|---|---|---|---|
| all | Q1 -30.364 to -6.740 | 339 | 1.050 | 1.172 | 15.6% | 10% | 16.0 | 27% |
| all | Q2 -6.718 to -2.444 | 339 | 1.123 | 1.278 | 31.9% | 11% | 17.9 | 32% |
| all | Q3 -2.434 to 3.560 | 339 | 1.081 | 1.242 | 20.0% | 12% | 17.9 | 31% |
| all | Q4 3.608 to 8.043 | 339 | 1.535 | 1.738 | 132.2% | 9% | 19.7 | 35% |
| all | Q5 8.066 to 31.491 | 339 | 1.432 | 1.636 | 102.8% | 10% | 18.1 | 31% |
| long | Q1 -3.742 to 3.111 | 179 | 1.165 | 1.328 | 22.2% | 11% | 18.4 | 30% |
| long | Q2 3.132 to 5.279 | 178 | 1.153 | 1.310 | 20.7% | 11% | 19.7 | 34% |
| long | Q3 5.294 to 7.810 | 178 | 1.921 | 2.186 | 109.4% | 8% | 20.0 | 35% |
| long | Q4 7.813 to 11.418 | 178 | 1.538 | 1.748 | 67.5% | 9% | 20.2 | 35% |
| long | Q5 11.451 to 31.491 | 179 | 1.303 | 1.491 | 39.1% | 10% | 16.2 | 27% |
| short | Q1 -30.364 to -9.696 | 161 | 1.304 | 1.450 | 44.3% | 8% | 16.7 | 29% |
| short | Q2 -9.689 to -6.952 | 160 | 0.946 | 1.062 | -7.8% | 11% | 15.9 | 27% |
| short | Q3 -6.943 to -5.009 | 161 | 0.556 | 0.628 | -70.1% | 18% | 15.2 | 23% |
| short | Q4 -5.002 to -2.828 | 160 | 1.718 | 1.985 | 69.0% | 9% | 18.9 | 38% |
| short | Q5 -2.825 to 3.688 | 161 | 1.071 | 1.230 | 8.3% | 12% | 17.6 | 33% |

#### daily EMA slope, % per day (`daily_ema_slope_pct`)

| Side | Bin | Trades | PF net | PF gross | Net (sum of % returns) | Fee share of gross profit | Avg bars held | Win rate |
|---|---|---|---|---|---|---|---|---|
| all | Q1 -3.31% to -0.40% | 339 | 0.986 | 1.083 | -5.1% | 9% | 16.6 | 29% |
| all | Q2 -0.39% to -0.10% | 339 | 1.202 | 1.392 | 46.0% | 12% | 17.0 | 30% |
| all | Q3 -0.10% to 0.18% | 339 | 1.294 | 1.540 | 55.3% | 13% | 18.0 | 31% |
| all | Q4 0.18% to 0.59% | 339 | 1.376 | 1.574 | 89.2% | 10% | 18.8 | 32% |
| all | Q5 0.59% to 3.56% | 339 | 1.419 | 1.587 | 117.3% | 8% | 19.2 | 32% |
| long | Q1 0.00% to 0.15% | 179 | 1.417 | 1.661 | 44.4% | 11% | 18.9 | 29% |
| long | Q2 0.15% to 0.33% | 178 | 1.387 | 1.592 | 46.6% | 10% | 19.1 | 35% |
| long | Q3 0.33% to 0.57% | 178 | 1.478 | 1.690 | 58.4% | 10% | 18.6 | 34% |
| long | Q4 0.57% to 0.94% | 178 | 1.556 | 1.767 | 70.5% | 9% | 20.0 | 33% |
| long | Q5 0.95% to 3.56% | 179 | 1.232 | 1.366 | 38.9% | 8% | 17.8 | 30% |
| short | Q1 -3.31% to -0.75% | 161 | 0.990 | 1.068 | -2.2% | 7% | 18.0 | 33% |
| short | Q2 -0.74% to -0.42% | 160 | 1.085 | 1.217 | 11.9% | 10% | 15.8 | 28% |
| short | Q3 -0.42% to -0.26% | 161 | 0.819 | 0.951 | -21.2% | 16% | 15.0 | 24% |
| short | Q4 -0.25% to -0.12% | 160 | 1.441 | 1.666 | 45.5% | 10% | 18.5 | 32% |
| short | Q5 -0.12% to -0.00% | 161 | 1.116 | 1.351 | 9.8% | 16% | 17.0 | 31% |

#### EMA - VWAP in ATR, in trade direction (`sep_atr_side`)

| Side | Bin | Trades | PF net | PF gross | Net (sum of % returns) | Fee share of gross profit | Avg bars held | Win rate |
|---|---|---|---|---|---|---|---|---|
| all | Q1 0.000 to 0.026 | 339 | 1.117 | 1.301 | 26.0% | 13% | 14.7 | 27% |
| all | Q2 0.026 to 0.054 | 339 | 1.390 | 1.588 | 94.0% | 10% | 17.3 | 31% |
| all | Q3 0.054 to 0.093 | 339 | 1.698 | 1.918 | 170.6% | 8% | 19.9 | 35% |
| all | Q4 0.093 to 0.150 | 339 | 0.810 | 0.920 | -55.1% | 14% | 17.3 | 27% |
| all | Q5 0.150 to 1.028 | 339 | 1.220 | 1.358 | 67.1% | 9% | 20.4 | 35% |
| long | Q1 0.000 to 0.026 | 179 | 1.127 | 1.328 | 14.1% | 14% | 14.0 | 27% |
| long | Q2 0.026 to 0.054 | 178 | 1.552 | 1.783 | 64.9% | 9% | 18.1 | 33% |
| long | Q3 0.054 to 0.092 | 178 | 2.341 | 2.652 | 154.9% | 6% | 22.6 | 37% |
| long | Q4 0.092 to 0.150 | 178 | 0.800 | 0.912 | -29.7% | 14% | 18.4 | 27% |
| long | Q5 0.150 to 1.028 | 179 | 1.362 | 1.518 | 54.7% | 8% | 21.3 | 37% |
| short | Q1 0.000 to 0.024 | 161 | 1.082 | 1.247 | 9.4% | 13% | 15.3 | 27% |
| short | Q2 0.025 to 0.054 | 160 | 1.222 | 1.388 | 27.1% | 10% | 16.5 | 30% |
| short | Q3 0.054 to 0.093 | 161 | 1.114 | 1.260 | 14.8% | 11% | 16.6 | 32% |
| short | Q4 0.094 to 0.148 | 160 | 0.821 | 0.925 | -26.1% | 13% | 16.5 | 29% |
| short | Q5 0.148 to 0.458 | 161 | 1.126 | 1.255 | 18.6% | 9% | 19.4 | 31% |

#### crosses in previous 24 bars (`crosses_24`)

| Side | Bin | Trades | PF net | PF gross | Net (sum of % returns) | Fee share of gross profit | Avg bars held | Win rate |
|---|---|---|---|---|---|---|---|---|
| all | 0 | 299 | 0.880 | 0.989 | -32.6% | 12% | 18.6 | 32% |
| all | 1 | 911 | 1.259 | 1.428 | 180.4% | 10% | 18.2 | 31% |
| all | 2 | 263 | 1.184 | 1.347 | 36.7% | 11% | 17.2 | 29% |
| all | 3 | 158 | 1.755 | 2.019 | 77.4% | 9% | 15.9 | 28% |
| all | 4+ | 64 | 2.288 | 2.668 | 40.8% | 8% | 18.7 | 47% |
| long | 0 | 136 | 0.697 | 0.784 | -39.9% | 14% | 18.8 | 28% |
| long | 1 | 502 | 1.568 | 1.786 | 198.5% | 9% | 19.7 | 33% |
| long | 2 | 129 | 1.615 | 1.831 | 57.7% | 8% | 18.4 | 29% |
| long | 3 | 91 | 1.332 | 1.578 | 17.2% | 13% | 15.0 | 29% |
| long | 4+ | 34 | 2.516 | 2.914 | 25.3% | 8% | 19.6 | 50% |
| short | 0 | 163 | 1.052 | 1.181 | 7.3% | 11% | 18.4 | 35% |
| short | 1 | 409 | 0.948 | 1.072 | -18.1% | 12% | 16.4 | 28% |
| short | 2 | 134 | 0.802 | 0.922 | -21.0% | 15% | 16.1 | 28% |
| short | 3 | 67 | 2.189 | 2.458 | 60.2% | 6% | 17.2 | 27% |
| short | 4+ | 30 | 2.033 | 2.389 | 15.5% | 9% | 17.7 | 43% |

#### crosses in previous 48 bars (`crosses_48`)

| Side | Bin | Trades | PF net | PF gross | Net (sum of % returns) | Fee share of gross profit | Avg bars held | Win rate |
|---|---|---|---|---|---|---|---|---|
| all | 0 | 26 (few) | 1.729 | 1.932 | 14.0% | 8% | 24.7 | 46% |
| all | 1 | 423 | 0.720 | 0.821 | -102.6% | 15% | 16.9 | 29% |
| all | 2 | 457 | 1.322 | 1.494 | 114.2% | 9% | 18.8 | 31% |
| all | 3 | 447 | 1.154 | 1.312 | 53.2% | 11% | 16.9 | 28% |
| all | 4+ | 342 | 2.027 | 2.315 | 223.8% | 8% | 18.9 | 36% |
| long | 0 | 6 (few) | 1.686 | 1.845 | 4.0% | 6% | 28.7 | 33% |
| long | 1 | 224 | 0.662 | 0.759 | -65.0% | 17% | 17.4 | 30% |
| long | 2 | 238 | 1.611 | 1.831 | 103.4% | 9% | 20.4 | 32% |
| long | 3 | 244 | 1.645 | 1.875 | 108.8% | 9% | 18.5 | 31% |
| long | 4+ | 180 | 1.999 | 2.304 | 107.7% | 8% | 18.9 | 36% |
| short | 0 | 20 (few) | 1.748 | 1.971 | 9.9% | 8% | 23.5 | 50% |
| short | 1 | 199 | 0.784 | 0.889 | -37.6% | 14% | 16.3 | 28% |
| short | 2 | 219 | 1.059 | 1.192 | 10.9% | 11% | 17.1 | 29% |
| short | 3 | 203 | 0.686 | 0.782 | -55.5% | 16% | 14.9 | 25% |
| short | 4+ | 162 | 2.055 | 2.326 | 116.1% | 7% | 18.8 | 36% |

#### volume / 24-bar average (`vol_ratio_24`)

| Side | Bin | Trades | PF net | PF gross | Net (sum of % returns) | Fee share of gross profit | Avg bars held | Win rate |
|---|---|---|---|---|---|---|---|---|
| all | Q1 0.166 to 0.619 | 339 | 1.110 | 1.290 | 25.2% | 13% | 16.6 | 28% |
| all | Q2 0.620 to 0.834 | 339 | 1.266 | 1.461 | 61.1% | 11% | 17.5 | 29% |
| all | Q3 0.835 to 1.112 | 339 | 1.382 | 1.565 | 97.6% | 9% | 18.4 | 33% |
| all | Q4 1.113 to 1.622 | 339 | 1.162 | 1.305 | 46.4% | 10% | 18.7 | 35% |
| all | Q5 1.622 to 19.307 | 339 | 1.238 | 1.379 | 72.3% | 9% | 18.5 | 31% |
| long | Q1 0.166 to 0.596 | 179 | 1.289 | 1.488 | 34.8% | 11% | 17.7 | 29% |
| long | Q2 0.596 to 0.793 | 178 | 1.179 | 1.360 | 22.2% | 12% | 17.8 | 28% |
| long | Q3 0.794 to 1.037 | 178 | 1.126 | 1.280 | 17.4% | 11% | 18.8 | 31% |
| long | Q4 1.040 to 1.466 | 178 | 1.953 | 2.214 | 112.0% | 8% | 20.2 | 40% |
| long | Q5 1.469 to 19.307 | 179 | 1.503 | 1.684 | 72.5% | 8% | 19.8 | 32% |
| short | Q1 0.197 to 0.646 | 161 | 0.900 | 1.057 | -10.7% | 16% | 15.0 | 27% |
| short | Q2 0.647 to 0.880 | 160 | 1.379 | 1.587 | 41.1% | 10% | 17.9 | 29% |
| short | Q3 0.881 to 1.176 | 161 | 1.104 | 1.239 | 14.4% | 10% | 16.0 | 30% |
| short | Q4 1.179 to 1.676 | 160 | 0.934 | 1.041 | -10.1% | 11% | 17.5 | 30% |
| short | Q5 1.680 to 12.383 | 161 | 1.060 | 1.178 | 9.1% | 10% | 17.9 | 32% |

#### volume / 7-day average (`vol_ratio_7d`)

| Side | Bin | Trades | PF net | PF gross | Net (sum of % returns) | Fee share of gross profit | Avg bars held | Win rate |
|---|---|---|---|---|---|---|---|---|
| all | Q1 0.119 to 0.488 | 338 | 1.284 | 1.560 | 49.0% | 15% | 14.9 | 26% |
| all | Q2 0.490 to 0.703 | 338 | 1.174 | 1.362 | 39.3% | 12% | 17.1 | 29% |
| all | Q3 0.703 to 0.950 | 338 | 1.000 | 1.124 | 0.0% | 11% | 17.6 | 27% |
| all | Q4 0.950 to 1.454 | 338 | 1.614 | 1.800 | 166.9% | 7% | 20.3 | 38% |
| all | Q5 1.458 to 27.968 | 338 | 1.143 | 1.263 | 46.8% | 9% | 19.7 | 35% |
| all | na | 5 (few) | 1.076 | 1.145 | 0.6% | 6% | 13.4 | 20% |
| long | Q1 0.121 to 0.492 | 178 | 1.130 | 1.366 | 12.4% | 16% | 15.2 | 25% |
| long | Q2 0.492 to 0.678 | 177 | 1.415 | 1.642 | 46.8% | 11% | 18.0 | 31% |
| long | Q3 0.682 to 0.901 | 177 | 1.271 | 1.427 | 39.8% | 9% | 18.6 | 31% |
| long | Q4 0.906 to 1.324 | 177 | 1.567 | 1.760 | 77.0% | 8% | 20.9 | 36% |
| long | Q5 1.330 to 27.968 | 178 | 1.570 | 1.749 | 82.3% | 8% | 21.9 | 39% |
| long | na | 5 (few) | 1.076 | 1.145 | 0.6% | 6% | 13.4 | 20% |
| short | Q1 0.119 to 0.488 | 161 | 1.412 | 1.715 | 33.0% | 14% | 14.6 | 27% |
| short | Q2 0.488 to 0.734 | 160 | 1.045 | 1.212 | 5.0% | 13% | 16.6 | 28% |
| short | Q3 0.735 to 0.999 | 161 | 0.961 | 1.077 | -5.8% | 11% | 17.5 | 28% |
| short | Q4 1.003 to 1.577 | 160 | 1.101 | 1.226 | 14.9% | 10% | 16.8 | 32% |
| short | Q5 1.578 to 7.458 | 161 | 0.981 | 1.077 | -3.4% | 9% | 18.7 | 34% |

#### entry hour UTC (`hour_utc`)

| Side | Bin | Trades | PF net | PF gross | Net (sum of % returns) | Fee share of gross profit | Avg bars held | Win rate |
|---|---|---|---|---|---|---|---|---|
| all | 00-03 | 282 | 1.006 | 1.131 | 1.4% | 11% | 18.2 | 30% |
| all | 04-07 | 223 | 1.207 | 1.383 | 33.3% | 11% | 16.7 | 30% |
| all | 08-11 | 247 | 1.253 | 1.424 | 46.9% | 10% | 18.1 | 32% |
| all | 12-15 | 300 | 1.133 | 1.281 | 32.4% | 11% | 16.6 | 28% |
| all | 16-19 | 352 | 1.390 | 1.589 | 96.7% | 10% | 18.9 | 32% |
| all | 20-23 | 291 | 1.419 | 1.603 | 92.0% | 9% | 18.7 | 34% |
| long | 00-03 | 164 | 0.998 | 1.124 | -0.2% | 11% | 19.1 | 29% |
| long | 04-07 | 109 | 1.398 | 1.616 | 28.4% | 11% | 17.7 | 29% |
| long | 08-11 | 137 | 1.100 | 1.257 | 10.2% | 12% | 18.5 | 33% |
| long | 12-15 | 149 | 1.209 | 1.371 | 24.1% | 10% | 16.7 | 29% |
| long | 16-19 | 157 | 2.482 | 2.869 | 126.6% | 7% | 21.4 | 40% |
| long | 20-23 | 176 | 1.550 | 1.760 | 69.8% | 9% | 19.4 | 32% |
| short | 00-03 | 118 | 1.015 | 1.140 | 1.6% | 11% | 16.9 | 31% |
| short | 04-07 | 114 | 1.055 | 1.200 | 4.9% | 12% | 15.9 | 30% |
| short | 08-11 | 110 | 1.441 | 1.630 | 36.7% | 9% | 17.6 | 32% |
| short | 12-15 | 151 | 1.065 | 1.199 | 8.3% | 11% | 16.5 | 28% |
| short | 16-19 | 195 | 0.815 | 0.929 | -29.9% | 14% | 16.9 | 25% |
| short | 20-23 | 115 | 1.239 | 1.393 | 22.2% | 10% | 17.6 | 37% |

#### entry weekday UTC (0 = Monday) (`weekday_utc`)

| Side | Bin | Trades | PF net | PF gross | Net (sum of % returns) | Fee share of gross profit | Avg bars held | Win rate |
|---|---|---|---|---|---|---|---|---|
| all | Mon | 245 | 1.593 | 1.780 | 116.6% | 8% | 18.8 | 34% |
| all | Tue | 225 | 1.426 | 1.593 | 81.0% | 8% | 20.0 | 31% |
| all | Wed | 220 | 1.171 | 1.301 | 34.7% | 9% | 18.4 | 34% |
| all | Thu | 221 | 1.611 | 1.807 | 102.6% | 8% | 19.6 | 38% |
| all | Fri | 218 | 0.914 | 1.053 | -14.0% | 14% | 18.6 | 36% |
| all | Sat | 251 | 0.803 | 0.947 | -32.8% | 18% | 16.4 | 21% |
| all | Sun | 315 | 1.067 | 1.237 | 14.4% | 13% | 15.0 | 26% |
| long | Mon | 132 | 1.854 | 2.072 | 87.9% | 7% | 18.1 | 33% |
| long | Tue | 123 | 1.655 | 1.840 | 67.4% | 7% | 22.0 | 33% |
| long | Wed | 116 | 2.102 | 2.346 | 94.4% | 6% | 21.6 | 40% |
| long | Thu | 98 | 1.103 | 1.239 | 8.7% | 10% | 19.6 | 32% |
| long | Fri | 114 | 1.432 | 1.658 | 29.8% | 11% | 20.3 | 43% |
| long | Sat | 134 | 0.754 | 0.895 | -21.4% | 19% | 17.6 | 22% |
| long | Sun | 175 | 0.930 | 1.097 | -7.9% | 16% | 15.1 | 27% |
| short | Mon | 113 | 1.306 | 1.462 | 28.7% | 9% | 19.6 | 35% |
| short | Tue | 102 | 1.156 | 1.298 | 13.6% | 10% | 17.7 | 28% |
| short | Wed | 104 | 0.491 | 0.550 | -59.7% | 17% | 14.8 | 27% |
| short | Thu | 123 | 2.119 | 2.379 | 94.0% | 7% | 19.6 | 44% |
| short | Fri | 104 | 0.534 | 0.615 | -43.7% | 20% | 16.8 | 29% |
| short | Sat | 117 | 0.856 | 1.005 | -11.3% | 17% | 14.9 | 20% |
| short | Sun | 140 | 1.212 | 1.384 | 22.3% | 11% | 14.8 | 25% |

### Bin patterns in both halves (split at 2022-01-01 00:00 UTC, by exit)

| Feature | Bin | n 1st half | PF net 1st half | n 2nd half | PF net 2nd half |
|---|---|---|---|---|---|
| ATR % of price | Q1 0.10% to 0.47% | 80 | 1.054 | 259 | 1.599 |
| ATR % of price | Q2 0.47% to 0.64% | 121 | 2.618 | 218 | 1.433 |
| ATR % of price | Q3 0.64% to 0.84% | 153 | 1.445 | 186 | 0.953 |
| ATR % of price | Q4 0.84% to 1.18% | 196 | 1.186 | 143 | 0.656 |
| ATR % of price | Q5 1.18% to 6.38% | 265 | 1.316 | 74 | 0.504 |
| close - daily EMA, in ATR | Q1 -30.364 to -6.740 | 161 | 1.364 | 178 | 0.691 |
| close - daily EMA, in ATR | Q2 -6.718 to -2.444 | 146 | 1.349 | 193 | 0.875 |
| close - daily EMA, in ATR | Q3 -2.434 to 3.560 | 181 | 0.961 | 158 | 1.267 |
| close - daily EMA, in ATR | Q4 3.608 to 8.043 | 171 | 1.761 | 168 | 1.200 |
| close - daily EMA, in ATR | Q5 8.066 to 31.491 | 156 | 1.593 | 183 | 1.246 |
| daily EMA slope, % per day | Q1 -3.31% to -0.40% | 187 | 1.144 | 152 | 0.733 |
| daily EMA slope, % per day | Q2 -0.39% to -0.10% | 135 | 1.554 | 204 | 0.924 |
| daily EMA slope, % per day | Q3 -0.10% to 0.18% | 144 | 1.342 | 195 | 1.251 |
| daily EMA slope, % per day | Q4 0.18% to 0.59% | 141 | 1.468 | 198 | 1.285 |
| daily EMA slope, % per day | Q5 0.59% to 3.56% | 208 | 1.609 | 131 | 1.017 |
| EMA - VWAP in ATR, in trade direction | Q1 0.000 to 0.026 | 177 | 1.061 | 162 | 1.217 |
| EMA - VWAP in ATR, in trade direction | Q2 0.026 to 0.054 | 175 | 1.799 | 164 | 0.935 |
| EMA - VWAP in ATR, in trade direction | Q3 0.054 to 0.093 | 161 | 1.936 | 178 | 1.372 |
| EMA - VWAP in ATR, in trade direction | Q4 0.093 to 0.150 | 167 | 0.926 | 172 | 0.661 |
| EMA - VWAP in ATR, in trade direction | Q5 0.150 to 1.028 | 135 | 1.394 | 204 | 1.048 |
| crosses in previous 24 bars | 0 | 137 | 0.981 | 162 | 0.750 |
| crosses in previous 24 bars | 1 | 472 | 1.399 | 439 | 1.062 |
| crosses in previous 24 bars | 2 | 112 | 1.451 | 151 | 0.921 |
| crosses in previous 24 bars | 3 | 67 | 2.234 | 91 | 1.319 |
| crosses in previous 24 bars | 4+ | 27 (few) | 2.391 | 37 | 2.145 |
| crosses in previous 48 bars | 0 | 13 (few) | 2.107 | 13 (few) | 0.925 |
| crosses in previous 48 bars | 1 | 208 | 0.636 | 215 | 0.843 |
| crosses in previous 48 bars | 2 | 243 | 1.775 | 214 | 0.720 |
| crosses in previous 48 bars | 3 | 213 | 1.047 | 234 | 1.292 |
| crosses in previous 48 bars | 4+ | 138 | 2.923 | 204 | 1.292 |
| volume / 24-bar average | Q1 0.166 to 0.619 | 150 | 1.317 | 189 | 0.850 |
| volume / 24-bar average | Q2 0.620 to 0.834 | 176 | 1.501 | 163 | 0.950 |
| volume / 24-bar average | Q3 0.835 to 1.112 | 182 | 1.552 | 157 | 1.106 |
| volume / 24-bar average | Q4 1.113 to 1.622 | 167 | 1.234 | 172 | 1.061 |
| volume / 24-bar average | Q5 1.622 to 19.307 | 140 | 1.403 | 199 | 1.094 |
| volume / 7-day average | Q1 0.119 to 0.488 | 116 | 2.000 | 222 | 0.741 |
| volume / 7-day average | Q2 0.490 to 0.703 | 177 | 1.400 | 161 | 0.876 |
| volume / 7-day average | Q3 0.703 to 0.950 | 197 | 0.978 | 141 | 1.045 |
| volume / 7-day average | Q4 0.950 to 1.454 | 175 | 1.897 | 163 | 1.280 |
| volume / 7-day average | Q5 1.458 to 27.968 | 145 | 1.214 | 193 | 1.068 |
| volume / 7-day average | na | 5 (few) | 1.076 | 0 (few) |  |
| entry hour UTC | 00-03 | 168 | 0.859 | 114 | 1.413 |
| entry hour UTC | 04-07 | 101 | 2.016 | 122 | 0.396 |
| entry hour UTC | 08-11 | 125 | 1.653 | 122 | 0.774 |
| entry hour UTC | 12-15 | 134 | 1.380 | 166 | 0.828 |
| entry hour UTC | 16-19 | 149 | 1.712 | 203 | 1.116 |
| entry hour UTC | 20-23 | 138 | 1.306 | 153 | 1.543 |
| entry weekday UTC (0 = Monday) | Mon | 121 | 2.423 | 124 | 0.838 |
| entry weekday UTC (0 = Monday) | Tue | 101 | 2.019 | 124 | 0.845 |
| entry weekday UTC (0 = Monday) | Wed | 110 | 1.150 | 110 | 1.198 |
| entry weekday UTC (0 = Monday) | Thu | 111 | 1.753 | 110 | 1.417 |
| entry weekday UTC (0 = Monday) | Fri | 108 | 0.933 | 110 | 0.878 |
| entry weekday UTC (0 = Monday) | Sat | 132 | 0.858 | 119 | 0.710 |
| entry weekday UTC (0 = Monday) | Sun | 132 | 0.935 | 183 | 1.219 |

### Distributions per group

#### ATR % of price (`atr_pct`)

| Group | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| top 1%, all | 17 (few) | 0.48% | 0.57% | 0.80% | 1.30% | 1.87% |
| bottom 1%, all | 17 (few) | 2.11% | 2.16% | 2.47% | 3.47% | 4.27% |
| rest, all | 1661 | 0.35% | 0.51% | 0.73% | 1.04% | 1.45% |
| top 1%, long | 11 (few) | 0.44% | 0.56% | 0.71% | 1.07% | 1.43% |
| bottom 1%, long | 4 (few) | 2.11% | 2.14% | 2.43% | 2.96% | 3.43% |
| rest, long | 877 | 0.37% | 0.51% | 0.72% | 0.98% | 1.34% |
| top 1%, short | 6 (few) | 0.56% | 0.70% | 1.18% | 1.41% | 1.97% |
| bottom 1%, short | 13 (few) | 2.13% | 2.16% | 2.47% | 3.47% | 4.75% |
| rest, short | 784 | 0.33% | 0.51% | 0.77% | 1.13% | 1.56% |

Median per exit year:

| Year | median top 1% (n) | median bottom 1% (n) | median rest | n rest |
|---|---|---|---|---|
| 2018 | 1.51% (2 (few)) | 3.47% (7 (few)) | 0.97% | 176 |
| 2019 | 0.80% (3 (few)) | 2.16% (1 (few)) | 0.72% | 210 |
| 2020 | 0.69% (5 (few)) | 2.24% (2 (few)) | 0.77% | 195 |
| 2021 | 1.43% (3 (few)) | 2.47% (5 (few)) | 1.12% | 206 |
| 2022 | 1.18% (2 (few)) | 2.51% (2 (few)) | 0.83% | 206 |
| 2023 | 0.38% (1 (few)) |  (0 (few)) | 0.49% | 225 |
| 2024 | 0.63% (1 (few)) |  (0 (few)) | 0.65% | 228 |
| 2025 |  (0 (few)) |  (0 (few)) | 0.52% | 215 |

#### close - daily EMA, in ATR (`dist_daily_ema_atr`)

| Group | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| top 1%, all | 17 (few) | -10.045 | -6.238 | 6.572 | 9.456 | 11.199 |
| bottom 1%, all | 17 (few) | -10.369 | -7.351 | -6.148 | -2.179 | 3.422 |
| rest, all | 1661 | -9.366 | -5.570 | 0.943 | 6.759 | 11.790 |
| top 1%, long | 11 (few) | 6.189 | 6.621 | 8.270 | 10.617 | 11.692 |
| bottom 1%, long | 4 (few) | 1.198 | 1.237 | 3.962 | 8.065 | 10.585 |
| rest, long | 877 | 1.730 | 3.715 | 6.546 | 10.438 | 13.992 |
| top 1%, short | 6 (few) | -14.929 | -10.258 | -8.865 | -6.661 | -5.181 |
| bottom 1%, short | 13 (few) | -10.762 | -9.289 | -6.889 | -5.520 | -5.286 |
| rest, short | 784 | -12.509 | -8.667 | -5.926 | -3.215 | -1.979 |

Median per exit year:

| Year | median top 1% (n) | median bottom 1% (n) | median rest | n rest |
|---|---|---|---|---|
| 2018 | -14.929 (2 (few)) | -6.889 (7 (few)) | -3.233 | 176 |
| 2019 | 8.270 (3 (few)) | -7.139 (1 (few)) | -0.142 | 210 |
| 2020 | 6.189 (5 (few)) | -2.058 (2 (few)) | 3.963 | 195 |
| 2021 | 6.879 (3 (few)) | -2.179 (5 (few)) | 1.996 | 206 |
| 2022 | -7.084 (2 (few)) | -10.124 (2 (few)) | -5.119 | 206 |
| 2023 | 9.456 (1 (few)) |  (0 (few)) | 3.963 | 225 |
| 2024 | 11.692 (1 (few)) |  (0 (few)) | 3.194 | 228 |
| 2025 |  (0 (few)) |  (0 (few)) | -1.976 | 215 |

#### daily EMA slope, % per day (`daily_ema_slope_pct`)

| Group | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| top 1%, all | 17 (few) | -0.94% | -0.51% | 0.33% | 0.80% | 1.38% |
| bottom 1%, all | 17 (few) | -2.09% | -1.79% | -1.07% | -0.18% | 0.98% |
| rest, all | 1661 | -0.68% | -0.30% | 0.04% | 0.47% | 0.96% |
| top 1%, long | 11 (few) | 0.31% | 0.38% | 0.75% | 0.94% | 1.98% |
| bottom 1%, long | 4 (few) | 0.21% | 0.24% | 1.16% | 2.44% | 3.11% |
| rest, long | 877 | 0.07% | 0.18% | 0.44% | 0.82% | 1.23% |
| top 1%, short | 6 (few) | -1.33% | -0.96% | -0.76% | -0.53% | -0.35% |
| bottom 1%, short | 13 (few) | -2.10% | -1.96% | -1.14% | -0.98% | -0.93% |
| rest, short | 784 | -1.00% | -0.59% | -0.31% | -0.15% | -0.07% |

Median per exit year:

| Year | median top 1% (n) | median bottom 1% (n) | median rest | n rest |
|---|---|---|---|---|
| 2018 | -1.33% (2 (few)) | -1.14% (7 (few)) | -0.19% | 176 |
| 2019 | 0.75% (3 (few)) | -1.07% (1 (few)) | 0.00% | 210 |
| 2020 | 0.33% (5 (few)) | -0.37% (2 (few)) | 0.24% | 195 |
| 2021 | 1.98% (3 (few)) | -0.18% (5 (few)) | 0.15% | 206 |
| 2022 | -0.55% (2 (few)) | -1.77% (2 (few)) | -0.28% | 206 |
| 2023 | 0.31% (1 (few)) |  (0 (few)) | 0.15% | 225 |
| 2024 | 0.43% (1 (few)) |  (0 (few)) | 0.18% | 228 |
| 2025 |  (0 (few)) |  (0 (few)) | -0.02% | 215 |

#### EMA - VWAP in ATR, in trade direction (`sep_atr_side`)

| Group | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| top 1%, all | 17 (few) | 0.027 | 0.055 | 0.073 | 0.161 | 0.218 |
| bottom 1%, all | 17 (few) | 0.027 | 0.051 | 0.094 | 0.150 | 0.188 |
| rest, all | 1661 | 0.013 | 0.032 | 0.073 | 0.132 | 0.202 |
| top 1%, long | 11 (few) | 0.018 | 0.053 | 0.066 | 0.075 | 0.163 |
| bottom 1%, long | 4 (few) | 0.121 | 0.139 | 0.165 | 0.208 | 0.256 |
| rest, long | 877 | 0.014 | 0.032 | 0.072 | 0.132 | 0.205 |
| top 1%, short | 6 (few) | 0.044 | 0.065 | 0.128 | 0.202 | 0.219 |
| bottom 1%, short | 13 (few) | 0.015 | 0.044 | 0.062 | 0.127 | 0.171 |
| rest, short | 784 | 0.012 | 0.031 | 0.074 | 0.130 | 0.198 |

Median per exit year:

| Year | median top 1% (n) | median bottom 1% (n) | median rest | n rest |
|---|---|---|---|---|
| 2018 | 0.125 (2 (few)) | 0.053 (7 (few)) | 0.064 | 176 |
| 2019 | 0.075 (3 (few)) | 0.044 (1 (few)) | 0.067 | 210 |
| 2020 | 0.063 (5 (few)) | 0.208 (2 (few)) | 0.064 | 195 |
| 2021 | 0.066 (3 (few)) | 0.150 (5 (few)) | 0.072 | 206 |
| 2022 | 0.138 (2 (few)) | 0.124 (2 (few)) | 0.072 | 206 |
| 2023 | 0.073 (1 (few)) |  (0 (few)) | 0.077 | 225 |
| 2024 | 0.395 (1 (few)) |  (0 (few)) | 0.073 | 228 |
| 2025 |  (0 (few)) |  (0 (few)) | 0.103 | 215 |

#### crosses in previous 24 bars (`crosses_24`)

| Group | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| top 1%, all | 17 (few) | 0.6 | 1.0 | 1.0 | 2.0 | 2.4 |
| bottom 1%, all | 17 (few) | 0.0 | 0.0 | 1.0 | 1.0 | 2.0 |
| rest, all | 1661 | 0.0 | 1.0 | 1.0 | 2.0 | 3.0 |
| top 1%, long | 11 (few) | 1.0 | 1.0 | 1.0 | 2.0 | 2.0 |
| bottom 1%, long | 4 (few) | 0.0 | 0.0 | 0.5 | 1.2 | 1.7 |
| rest, long | 877 | 0.0 | 1.0 | 1.0 | 2.0 | 3.0 |
| top 1%, short | 6 (few) | 0.0 | 0.2 | 1.0 | 1.0 | 2.0 |
| bottom 1%, short | 13 (few) | 0.0 | 1.0 | 1.0 | 1.0 | 2.0 |
| rest, short | 784 | 0.0 | 1.0 | 1.0 | 2.0 | 3.0 |

Median per exit year:

| Year | median top 1% (n) | median bottom 1% (n) | median rest | n rest |
|---|---|---|---|---|
| 2018 | 0.0 (2 (few)) | 1.0 (7 (few)) | 1.0 | 176 |
| 2019 | 1.0 (3 (few)) | 1.0 (1 (few)) | 1.0 | 210 |
| 2020 | 1.0 (5 (few)) | 1.5 (2 (few)) | 1.0 | 195 |
| 2021 | 2.0 (3 (few)) | 1.0 (5 (few)) | 1.0 | 206 |
| 2022 | 2.0 (2 (few)) | 1.5 (2 (few)) | 1.0 | 206 |
| 2023 | 1.0 (1 (few)) |  (0 (few)) | 1.0 | 225 |
| 2024 | 2.0 (1 (few)) |  (0 (few)) | 1.0 | 228 |
| 2025 |  (0 (few)) |  (0 (few)) | 1.0 | 215 |

#### crosses in previous 48 bars (`crosses_48`)

| Group | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| top 1%, all | 17 (few) | 1.0 | 2.0 | 3.0 | 4.0 | 5.0 |
| bottom 1%, all | 17 (few) | 1.0 | 1.0 | 2.0 | 3.0 | 3.0 |
| rest, all | 1661 | 1.0 | 1.0 | 2.0 | 3.0 | 5.0 |
| top 1%, long | 11 (few) | 2.0 | 2.0 | 3.0 | 3.0 | 4.0 |
| bottom 1%, long | 4 (few) | 1.0 | 1.0 | 1.0 | 1.5 | 2.4 |
| rest, long | 877 | 1.0 | 1.0 | 2.0 | 3.0 | 5.0 |
| top 1%, short | 6 (few) | 1.0 | 1.0 | 2.5 | 4.8 | 6.0 |
| bottom 1%, short | 13 (few) | 1.0 | 2.0 | 2.0 | 3.0 | 3.0 |
| rest, short | 784 | 1.0 | 1.0 | 2.0 | 3.0 | 4.0 |

Median per exit year:

| Year | median top 1% (n) | median bottom 1% (n) | median rest | n rest |
|---|---|---|---|---|
| 2018 | 3.0 (2 (few)) | 2.0 (7 (few)) | 2.0 | 176 |
| 2019 | 2.0 (3 (few)) | 2.0 (1 (few)) | 2.0 | 210 |
| 2020 | 3.0 (5 (few)) | 2.5 (2 (few)) | 2.0 | 195 |
| 2021 | 3.0 (3 (few)) | 3.0 (5 (few)) | 2.0 | 206 |
| 2022 | 4.0 (2 (few)) | 2.0 (2 (few)) | 2.0 | 206 |
| 2023 | 3.0 (1 (few)) |  (0 (few)) | 3.0 | 225 |
| 2024 | 3.0 (1 (few)) |  (0 (few)) | 2.5 | 228 |
| 2025 |  (0 (few)) |  (0 (few)) | 2.0 | 215 |

#### volume / 24-bar average (`vol_ratio_24`)

| Group | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| top 1%, all | 17 (few) | 0.435 | 0.593 | 0.938 | 1.316 | 2.131 |
| bottom 1%, all | 17 (few) | 0.602 | 0.851 | 1.191 | 1.373 | 3.319 |
| rest, all | 1661 | 0.515 | 0.670 | 0.963 | 1.405 | 2.300 |
| top 1%, long | 11 (few) | 0.357 | 0.540 | 0.889 | 1.136 | 1.700 |
| bottom 1%, long | 4 (few) | 0.519 | 0.551 | 0.710 | 0.966 | 1.174 |
| rest, long | 877 | 0.508 | 0.655 | 0.914 | 1.291 | 2.123 |
| top 1%, short | 6 (few) | 0.700 | 0.884 | 1.059 | 2.031 | 2.601 |
| bottom 1%, short | 13 (few) | 0.737 | 0.968 | 1.219 | 2.155 | 3.946 |
| rest, short | 784 | 0.524 | 0.699 | 1.033 | 1.524 | 2.429 |

Median per exit year:

| Year | median top 1% (n) | median bottom 1% (n) | median rest | n rest |
|---|---|---|---|---|
| 2018 | 1.590 (2 (few)) | 1.219 (7 (few)) | 0.907 | 176 |
| 2019 | 0.570 (3 (few)) | 2.155 (1 (few)) | 0.952 | 210 |
| 2020 | 0.938 (5 (few)) | 0.845 (2 (few)) | 0.907 | 195 |
| 2021 | 0.889 (3 (few)) | 0.926 (5 (few)) | 1.016 | 206 |
| 2022 | 1.963 (2 (few)) | 2.804 (2 (few)) | 1.055 | 206 |
| 2023 | 1.700 (1 (few)) |  (0 (few)) | 0.979 | 225 |
| 2024 | 1.985 (1 (few)) |  (0 (few)) | 0.914 | 228 |
| 2025 |  (0 (few)) |  (0 (few)) | 0.981 | 215 |

#### volume / 7-day average (`vol_ratio_7d`)

| Group | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| top 1%, all | 17 (few) | 0.367 | 0.595 | 0.958 | 1.404 | 2.167 |
| bottom 1%, all | 17 (few) | 0.746 | 0.766 | 1.310 | 2.103 | 2.999 |
| rest, all | 1656 | 0.379 | 0.543 | 0.798 | 1.262 | 1.992 |
| top 1%, long | 11 (few) | 0.325 | 0.495 | 0.822 | 1.219 | 2.012 |
| bottom 1%, long | 4 (few) | 0.721 | 0.749 | 0.792 | 1.087 | 1.567 |
| rest, long | 872 | 0.389 | 0.541 | 0.755 | 1.177 | 1.827 |
| top 1%, short | 6 (few) | 0.564 | 0.802 | 1.230 | 1.911 | 2.812 |
| bottom 1%, short | 13 (few) | 0.761 | 1.019 | 1.822 | 2.298 | 3.161 |
| rest, short | 784 | 0.372 | 0.545 | 0.837 | 1.396 | 2.155 |

Median per exit year:

| Year | median top 1% (n) | median bottom 1% (n) | median rest | n rest |
|---|---|---|---|---|
| 2018 | 1.398 (2 (few)) | 1.822 (7 (few)) | 0.804 | 176 |
| 2019 | 0.455 (3 (few)) | 2.103 (1 (few)) | 0.788 | 210 |
| 2020 | 0.958 (5 (few)) | 0.793 (2 (few)) | 0.758 | 195 |
| 2021 | 0.822 (3 (few)) | 1.019 (5 (few)) | 0.879 | 206 |
| 2022 | 2.345 (2 (few)) | 3.802 (2 (few)) | 0.920 | 206 |
| 2023 | 2.012 (1 (few)) |  (0 (few)) | 0.761 | 225 |
| 2024 | 2.231 (1 (few)) |  (0 (few)) | 0.698 | 228 |
| 2025 |  (0 (few)) |  (0 (few)) | 0.809 | 215 |

#### entry hour UTC (`hour_utc`)

| Group | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| top 1%, all | 17 (few) | 4.0 | 7.0 | 15.0 | 20.0 | 23.0 |
| bottom 1%, all | 17 (few) | 1.0 | 3.0 | 13.0 | 14.0 | 20.8 |
| rest, all | 1661 | 2.0 | 6.0 | 13.0 | 18.0 | 21.0 |
| top 1%, long | 11 (few) | 4.0 | 9.5 | 15.0 | 19.0 | 22.0 |
| bottom 1%, long | 4 (few) | 1.0 | 1.0 | 1.0 | 4.2 | 10.1 |
| rest, long | 877 | 1.0 | 6.0 | 12.0 | 18.0 | 21.0 |
| top 1%, short | 6 (few) | 4.5 | 6.2 | 15.0 | 22.2 | 23.0 |
| bottom 1%, short | 13 (few) | 3.2 | 10.0 | 13.0 | 14.0 | 21.6 |
| rest, short | 784 | 2.0 | 6.0 | 13.0 | 17.0 | 20.0 |

Median per exit year:

| Year | median top 1% (n) | median bottom 1% (n) | median rest | n rest |
|---|---|---|---|---|
| 2018 | 16.5 (2 (few)) | 10.0 (7 (few)) | 12.0 | 176 |
| 2019 | 5.0 (3 (few)) | 13.0 (1 (few)) | 12.0 | 210 |
| 2020 | 14.0 (5 (few)) | 7.5 (2 (few)) | 12.0 | 195 |
| 2021 | 15.0 (3 (few)) | 14.0 (5 (few)) | 12.0 | 206 |
| 2022 | 21.5 (2 (few)) | 17.5 (2 (few)) | 14.0 | 206 |
| 2023 | 20.0 (1 (few)) |  (0 (few)) | 13.0 | 225 |
| 2024 | 18.0 (1 (few)) |  (0 (few)) | 14.0 | 228 |
| 2025 |  (0 (few)) |  (0 (few)) | 14.0 | 215 |

#### entry weekday UTC (0 = Monday) (`weekday_utc`)

| Group | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| top 1%, all | 17 (few) | 0.0 | 1.0 | 2.0 | 4.0 | 6.0 |
| bottom 1%, all | 17 (few) | 0.6 | 1.0 | 3.0 | 4.0 | 5.0 |
| rest, all | 1661 | 0.0 | 1.0 | 3.0 | 5.0 | 6.0 |
| top 1%, long | 11 (few) | 0.0 | 0.5 | 2.0 | 3.0 | 4.0 |
| bottom 1%, long | 4 (few) | 0.3 | 0.8 | 1.0 | 2.0 | 3.8 |
| rest, long | 877 | 0.0 | 1.0 | 3.0 | 5.0 | 6.0 |
| top 1%, short | 6 (few) | 1.5 | 3.0 | 4.5 | 6.0 | 6.0 |
| bottom 1%, short | 13 (few) | 1.2 | 2.0 | 3.0 | 4.0 | 5.0 |
| rest, short | 784 | 0.0 | 1.0 | 3.0 | 5.0 | 6.0 |

Median per exit year:

| Year | median top 1% (n) | median bottom 1% (n) | median rest | n rest |
|---|---|---|---|---|
| 2018 | 6.0 (2 (few)) | 4.0 (7 (few)) | 3.0 | 176 |
| 2019 | 2.0 (3 (few)) | 3.0 (1 (few)) | 3.0 | 210 |
| 2020 | 3.0 (5 (few)) | 3.0 (2 (few)) | 3.0 | 195 |
| 2021 | 1.0 (3 (few)) | 3.0 (5 (few)) | 3.0 | 206 |
| 2022 | 4.5 (2 (few)) | 1.5 (2 (few)) | 3.0 | 206 |
| 2023 | 2.0 (1 (few)) |  (0 (few)) | 3.0 | 225 |
| 2024 | 0.0 (1 (few)) |  (0 (few)) | 4.0 | 228 |
| 2025 |  (0 (few)) |  (0 (few)) | 3.0 | 215 |

#### MFE % (`mfe_pct`)

| Group | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| top 1%, all | 17 (few) | 18.27% | 19.62% | 22.48% | 23.99% | 30.64% |
| bottom 1%, all | 17 (few) | 0.28% | 0.80% | 1.29% | 1.80% | 5.08% |
| rest, all | 1661 | 0.10% | 0.35% | 1.13% | 2.97% | 6.26% |
| top 1%, long | 11 (few) | 18.85% | 19.42% | 22.11% | 23.20% | 26.71% |
| bottom 1%, long | 4 (few) | 0.93% | 1.12% | 1.45% | 2.38% | 3.68% |
| rest, long | 877 | 0.09% | 0.35% | 1.11% | 2.73% | 5.85% |
| top 1%, short | 6 (few) | 19.61% | 22.22% | 23.68% | 30.03% | 41.35% |
| bottom 1%, short | 13 (few) | 0.25% | 0.51% | 1.29% | 1.80% | 5.12% |
| rest, short | 784 | 0.10% | 0.35% | 1.18% | 3.20% | 6.56% |

Median per exit year:

| Year | median top 1% (n) | median bottom 1% (n) | median rest | n rest |
|---|---|---|---|---|
| 2018 | 27.71% (2 (few)) | 1.39% (7 (few)) | 1.44% | 176 |
| 2019 | 22.11% (3 (few)) | 0.51% (1 (few)) | 1.05% | 210 |
| 2020 | 22.48% (5 (few)) | 5.37% (2 (few)) | 1.24% | 195 |
| 2021 | 23.40% (3 (few)) | 0.83% (5 (few)) | 2.16% | 206 |
| 2022 | 20.69% (2 (few)) | 0.15% (2 (few)) | 1.30% | 206 |
| 2023 | 21.13% (1 (few)) |  (0 (few)) | 0.71% | 225 |
| 2024 | 19.62% (1 (few)) |  (0 (few)) | 1.10% | 228 |
| 2025 |  (0 (few)) |  (0 (few)) | 0.84% | 215 |

#### MAE % (`mae_pct`)

| Group | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| top 1%, all | 17 (few) | 0.02% | 0.32% | 0.48% | 0.84% | 1.84% |
| bottom 1%, all | 17 (few) | 4.22% | 4.31% | 4.80% | 6.93% | 7.26% |
| rest, all | 1661 | 0.21% | 0.45% | 0.83% | 1.40% | 2.00% |
| top 1%, long | 11 (few) | 0.39% | 0.45% | 0.67% | 0.96% | 1.79% |
| bottom 1%, long | 4 (few) | 4.21% | 4.28% | 4.85% | 5.92% | 6.86% |
| rest, long | 877 | 0.21% | 0.47% | 0.86% | 1.35% | 1.92% |
| top 1%, short | 6 (few) | 0.01% | 0.02% | 0.17% | 0.44% | 1.20% |
| bottom 1%, short | 13 (few) | 4.25% | 4.32% | 4.80% | 6.93% | 7.07% |
| rest, short | 784 | 0.22% | 0.44% | 0.78% | 1.47% | 2.14% |

Median per exit year:

| Year | median top 1% (n) | median bottom 1% (n) | median rest | n rest |
|---|---|---|---|---|
| 2018 | 1.12% (2 (few)) | 6.94% (7 (few)) | 1.13% | 176 |
| 2019 | 0.67% (3 (few)) | 4.32% (1 (few)) | 0.86% | 210 |
| 2020 | 0.48% (5 (few)) | 4.49% (2 (few)) | 0.90% | 195 |
| 2021 | 1.08% (3 (few)) | 4.60% (5 (few)) | 1.42% | 206 |
| 2022 | 0.25% (2 (few)) | 5.03% (2 (few)) | 1.01% | 206 |
| 2023 | 0.24% (1 (few)) |  (0 (few)) | 0.53% | 225 |
| 2024 | 0.39% (1 (few)) |  (0 (few)) | 0.71% | 228 |
| 2025 |  (0 (few)) |  (0 (few)) | 0.70% | 215 |

#### MFE in ATR (`mfe_atr`)

| Group | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| top 1%, all | 17 (few) | 14.971 | 17.266 | 31.750 | 34.832 | 43.432 |
| bottom 1%, all | 17 (few) | 0.116 | 0.234 | 0.445 | 0.638 | 1.889 |
| rest, all | 1661 | 0.161 | 0.504 | 1.544 | 3.742 | 7.571 |
| top 1%, long | 11 (few) | 16.376 | 19.175 | 31.750 | 33.332 | 43.420 |
| bottom 1%, long | 4 (few) | 0.393 | 0.426 | 0.450 | 0.885 | 1.659 |
| rest, long | 877 | 0.163 | 0.534 | 1.539 | 3.650 | 7.778 |
| top 1%, short | 6 (few) | 14.628 | 16.881 | 26.660 | 37.201 | 40.719 |
| bottom 1%, short | 13 (few) | 0.103 | 0.136 | 0.403 | 0.638 | 1.531 |
| rest, short | 784 | 0.156 | 0.476 | 1.562 | 3.790 | 7.208 |

Median per exit year:

| Year | median top 1% (n) | median bottom 1% (n) | median rest | n rest |
|---|---|---|---|---|
| 2018 | 28.180 (2 (few)) | 0.483 (7 (few)) | 1.596 | 176 |
| 2019 | 33.224 (3 (few)) | 0.234 (1 (few)) | 1.416 | 210 |
| 2020 | 33.441 (5 (few)) | 2.380 (2 (few)) | 1.534 | 195 |
| 2021 | 16.376 (3 (few)) | 0.371 (5 (few)) | 1.776 | 206 |
| 2022 | 17.416 (2 (few)) | 0.068 (2 (few)) | 1.567 | 206 |
| 2023 | 55.875 (1 (few)) |  (0 (few)) | 1.528 | 225 |
| 2024 | 31.303 (1 (few)) |  (0 (few)) | 1.387 | 228 |
| 2025 |  (0 (few)) |  (0 (few)) | 1.495 | 215 |

#### MAE in ATR (`mae_atr`)

| Group | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| top 1%, all | 17 (few) | 0.023 | 0.372 | 0.693 | 0.989 | 1.338 |
| bottom 1%, all | 17 (few) | 1.886 | 2.000 | 2.000 | 2.000 | 2.000 |
| rest, all | 1661 | 0.316 | 0.719 | 1.259 | 1.999 | 2.000 |
| top 1%, long | 11 (few) | 0.621 | 0.659 | 0.838 | 1.117 | 1.569 |
| bottom 1%, long | 4 (few) | 2.000 | 2.000 | 2.000 | 2.000 | 2.000 |
| rest, long | 877 | 0.300 | 0.736 | 1.297 | 1.999 | 2.000 |
| top 1%, short | 6 (few) | 0.011 | 0.022 | 0.197 | 0.536 | 0.681 |
| bottom 1%, short | 13 (few) | 1.872 | 2.000 | 2.000 | 2.000 | 2.000 |
| rest, short | 784 | 0.348 | 0.701 | 1.212 | 1.968 | 2.000 |

Median per exit year:

| Year | median top 1% (n) | median bottom 1% (n) | median rest | n rest |
|---|---|---|---|---|
| 2018 | 0.681 (2 (few)) | 2.000 (7 (few)) | 1.194 | 176 |
| 2019 | 0.838 (3 (few)) | 2.000 (1 (few)) | 1.238 | 210 |
| 2020 | 1.050 (5 (few)) | 2.000 (2 (few)) | 1.283 | 195 |
| 2021 | 0.693 (3 (few)) | 2.000 (5 (few)) | 1.176 | 206 |
| 2022 | 0.197 (2 (few)) | 2.000 (2 (few)) | 1.391 | 206 |
| 2023 | 0.624 (1 (few)) |  (0 (few)) | 1.325 | 225 |
| 2024 | 0.621 (1 (few)) |  (0 (few)) | 1.152 | 228 |
| 2025 |  (0 (few)) |  (0 (few)) | 1.447 | 215 |

#### realized gross move % (`realized_pct`)

| Group | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| top 1%, all | 17 (few) | 13.98% | 14.68% | 16.32% | 18.58% | 21.25% |
| bottom 1%, all | 17 (few) | -7.26% | -6.24% | -4.80% | -4.31% | -4.22% |
| rest, all | 1661 | -1.80% | -1.06% | -0.40% | 0.39% | 2.92% |
| top 1%, long | 11 (few) | 13.63% | 14.44% | 15.23% | 18.43% | 19.20% |
| bottom 1%, long | 4 (few) | -6.86% | -5.92% | -4.85% | -4.28% | -4.21% |
| rest, long | 877 | -1.70% | -1.05% | -0.44% | 0.44% | 3.00% |
| top 1%, short | 6 (few) | 15.22% | 16.19% | 16.81% | 18.51% | 24.20% |
| bottom 1%, short | 13 (few) | -7.07% | -6.24% | -4.80% | -4.32% | -4.25% |
| rest, short | 784 | -1.89% | -1.07% | -0.37% | 0.34% | 2.82% |

Median per exit year:

| Year | median top 1% (n) | median bottom 1% (n) | median rest | n rest |
|---|---|---|---|---|
| 2018 | 17.61% (2 (few)) | -6.94% (7 (few)) | -0.39% | 176 |
| 2019 | 16.15% (3 (few)) | -4.32% (1 (few)) | -0.37% | 210 |
| 2020 | 14.21% (5 (few)) | -4.49% (2 (few)) | -0.40% | 195 |
| 2021 | 18.58% (3 (few)) | -4.51% (5 (few)) | -0.81% | 206 |
| 2022 | 15.80% (2 (few)) | -5.03% (2 (few)) | -0.57% | 206 |
| 2023 | 17.94% (1 (few)) |  (0 (few)) | -0.28% | 225 |
| 2024 | 15.13% (1 (few)) |  (0 (few)) | -0.38% | 228 |
| 2025 |  (0 (few)) |  (0 (few)) | -0.33% | 215 |

#### giveback % (MFE - realized) (`giveback_pct`)

| Group | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| top 1%, all | 17 (few) | 3.05% | 4.17% | 5.02% | 7.06% | 12.15% |
| bottom 1%, all | 17 (few) | 4.80% | 5.33% | 6.25% | 8.71% | 11.18% |
| rest, all | 1661 | 0.59% | 1.04% | 1.80% | 2.87% | 4.17% |
| top 1%, long | 11 (few) | 3.00% | 3.68% | 4.72% | 5.20% | 8.84% |
| bottom 1%, long | 4 (few) | 5.57% | 6.25% | 7.67% | 8.82% | 9.02% |
| rest, long | 877 | 0.62% | 1.04% | 1.74% | 2.63% | 3.71% |
| top 1%, short | 6 (few) | 4.39% | 5.94% | 6.88% | 11.62% | 17.15% |
| bottom 1%, short | 13 (few) | 4.76% | 5.33% | 5.99% | 8.50% | 11.35% |
| rest, short | 784 | 0.59% | 1.02% | 1.85% | 3.18% | 4.65% |

Median per exit year:

| Year | median top 1% (n) | median bottom 1% (n) | median rest | n rest |
|---|---|---|---|---|
| 2018 | 10.10% (2 (few)) | 8.50% (7 (few)) | 2.33% | 176 |
| 2019 | 5.69% (3 (few)) | 4.83% (1 (few)) | 1.63% | 210 |
| 2020 | 5.02% (5 (few)) | 9.86% (2 (few)) | 1.87% | 195 |
| 2021 | 4.82% (3 (few)) | 5.99% (5 (few)) | 2.89% | 206 |
| 2022 | 4.89% (2 (few)) | 5.18% (2 (few)) | 2.09% | 206 |
| 2023 | 3.19% (1 (few)) |  (0 (few)) | 1.17% | 225 |
| 2024 | 4.49% (1 (few)) |  (0 (few)) | 1.56% | 228 |
| 2025 |  (0 (few)) |  (0 (few)) | 1.30% | 215 |

#### bars held (`bars_held`)

| Group | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| top 1%, all | 17 (few) | 41.4 | 47.0 | 66.0 | 86.0 | 98.2 |
| bottom 1%, all | 17 (few) | 2.0 | 4.0 | 8.0 | 16.0 | 22.4 |
| rest, all | 1661 | 2.0 | 5.0 | 15.0 | 24.0 | 37.0 |
| top 1%, long | 11 (few) | 47.0 | 68.0 | 81.0 | 95.5 | 100.0 |
| bottom 1%, long | 4 (few) | 6.7 | 10.8 | 14.5 | 17.5 | 20.2 |
| rest, long | 877 | 2.0 | 5.0 | 15.0 | 25.0 | 39.0 |
| top 1%, short | 6 (few) | 35.5 | 40.2 | 48.5 | 55.2 | 57.5 |
| bottom 1%, short | 13 (few) | 2.0 | 2.0 | 6.0 | 14.0 | 21.8 |
| rest, short | 784 | 2.0 | 5.0 | 14.0 | 24.0 | 33.0 |

Median per exit year:

| Year | median top 1% (n) | median bottom 1% (n) | median rest | n rest |
|---|---|---|---|---|
| 2018 | 56.0 (2 (few)) | 9.0 (7 (few)) | 18.0 | 176 |
| 2019 | 94.0 (3 (few)) | 2.0 (1 (few)) | 16.0 | 210 |
| 2020 | 70.0 (5 (few)) | 19.5 (2 (few)) | 16.0 | 195 |
| 2021 | 47.0 (3 (few)) | 4.0 (5 (few)) | 17.0 | 206 |
| 2022 | 50.0 (2 (few)) | 3.5 (2 (few)) | 13.0 | 206 |
| 2023 | 81.0 (1 (few)) |  (0 (few)) | 12.0 | 225 |
| 2024 | 74.0 (1 (few)) |  (0 (few)) | 12.0 | 228 |
| 2025 |  (0 (few)) |  (0 (few)) | 13.0 | 215 |

#### bar of MFE (`mfe_bar`)

| Group | n | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|---|
| top 1%, all | 17 (few) | 28.6 | 36.0 | 46.0 | 73.0 | 85.8 |
| bottom 1%, all | 17 (few) | 1.0 | 1.0 | 1.0 | 8.0 | 9.8 |
| rest, all | 1661 | 1.0 | 1.0 | 4.0 | 14.0 | 26.0 |
| top 1%, long | 11 (few) | 33.0 | 46.0 | 57.0 | 79.0 | 93.0 |
| bottom 1%, long | 4 (few) | 1.3 | 1.8 | 2.5 | 5.2 | 9.3 |
| rest, long | 877 | 1.0 | 1.0 | 5.0 | 16.0 | 28.0 |
| top 1%, short | 6 (few) | 27.0 | 32.2 | 37.5 | 44.2 | 46.0 |
| bottom 1%, short | 13 (few) | 1.0 | 1.0 | 1.0 | 8.0 | 8.8 |
| rest, short | 784 | 1.0 | 1.0 | 4.0 | 13.0 | 23.0 |

Median per exit year:

| Year | median top 1% (n) | median bottom 1% (n) | median rest | n rest |
|---|---|---|---|---|
| 2018 | 46.0 (2 (few)) | 3.0 (7 (few)) | 5.0 | 176 |
| 2019 | 81.0 (3 (few)) | 1.0 (1 (few)) | 5.0 | 210 |
| 2020 | 57.0 (5 (few)) | 11.5 (2 (few)) | 6.0 | 195 |
| 2021 | 33.0 (3 (few)) | 1.0 (5 (few)) | 5.0 | 206 |
| 2022 | 33.5 (2 (few)) | 0.5 (2 (few)) | 4.0 | 206 |
| 2023 | 53.0 (1 (few)) |  (0 (few)) | 3.0 | 225 |
| 2024 | 48.0 (1 (few)) |  (0 (few)) | 4.0 | 228 |
| 2025 |  (0 (few)) |  (0 (few)) | 4.0 | 215 |
