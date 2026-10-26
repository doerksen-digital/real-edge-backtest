# Hypotheses for ema_vwap, phase 4a

Written after [diagnosis.md](diagnosis.md) and before any variant was run. Approved on 2026-10-26 with changes: the H7 mechanism was replaced, the combination rule was added, and H6 waits for a separate approval. H1 to H5, H7 and H8 ran in this round. Results: [results-4a.md](results-4a.md).

## Rules for every hypothesis

- **Base:** `configs/ema_vwap_full.toml` on BTCUSDT 1h, 2018-01-01 to 2026-01-01. That means fees 0.05% per side, 2 ticks of slippage, pessimistic fills, and percent_equity sizing unless the hypothesis is about sizing.
- **Change:** each hypothesis changes exactly what its rule says. Everything else stays at the base values.
- **Sweep:** each hypothesis gets a sweep spec `configs/sweeps/<ID>.toml`, written before it runs, with its base value and the neighbor values below. The rule's fixed changes go in the spec's `[set]`, the 1 or 2 varied parameters in `[grid]`. H5 has two specs (`H5-T`, `H5-K`) for its five points. Every point is a logged run.
- **New plug-ins:** a plug-in a hypothesis needs is implemented exactly as written here, with tests, before its sweep runs.
- **Comparison:** every point is compared with the base run using `report --compare`. Of interest are the trades that disappeared, appeared or changed, and what happened to the base run's top 1% winners.
- **Success (on top of each hypothesis's own criterion):**
  - the base value passes the run's `[criteria]`: PF ≥ 1.3, at least 100 trades, net PnL positive without the top 5 trades and without the top 1% (return method), and positive in both halves;
  - every neighbor value has PF ≥ 1.2 and positive net PnL in both halves (a plateau, not a peak).
- **Combinations:** none in the single runs. After them, at most ONE combination is built, and only from hypotheses that each passed their own success criteria.
  - It is defined in writing in this file before it runs.
  - It uses only parameter values that were already run here, with no new values.
  - Its runs count toward the variant total like any other.
- **Candidate for ETH:** only that combination, or the single best hypothesis if no combination makes sense, is the candidate for ETHUSDT, and it goes unchanged. If no hypothesis passes, nothing goes to ETHUSDT.
- **Multiple testing:** this list has 24 runs, 21 in this round (H6 waits). Each one raises the chance that a pass is luck, which is why the plateau rule and the single-candidate rule apply.

## Ranked list

Ranked by expected impact and strength of mechanism. Impact is the size of the problem the hypothesis targets in the diagnosis. Mechanism strength is how directly the rule acts on a cause rather than on a pattern found by looking.

| Rank | ID | Hypothesis | Targets | Params | Runs |
|---|---|---|---|---|---|
| 1 | H1 | Same logic on 4h, lengths in bars | fee drag, second-half decay | timeframe | 3 |
| 2 | H2 | fixed_risk sizing | outlier dependence (bottom tail) | risk_pct | 3 |
| 3 | H3 | Entry confirmation after N bars | low PF and fee drag | N | 3 |
| 4 | H4 | Breakeven stop after K ATR | outlier dependence, low PF | K | 3 |
| 5 | H5 | ATR trailing stop after a strong move | outlier dependence, low PF | K, T | 5 |
| 6 | H6 | Skip the first cross after a one-sided stretch (waits for approval) | low PF | L | 3 |
| 7 | H7 | Long only (spot-executable) | unmodeled short costs | none | 1 |
| 8 | H8 | 4h with a 24-hour VWAP | fee drag, second-half decay | VWAP bars | 3 |

H5 runs the base point and its four direct neighbors, not the full 3 by 3 grid.

---

### H1: Same logic on 4h, lengths in bars

- **Mechanism.** Round-trip costs are a fixed 0.10% of notional plus slippage, whatever the move. The diagnosis shows the trade profile in ATR units is unchanged between halves. As 1h ATR fell from about 1.2% to about 0.6% of price, the same profile meant smaller percent moves against the same costs. Cost per mean absolute move went from 4% (2018) to about 10% (2025), and the fee share of gross profit from 7.8% to 14.3%. On longer bars the ATR in percent is larger, so moves per trade are larger against unchanged costs, and there are fewer round trips.
- **Rule.** `[data] timeframe = T`, with bars built from the 1h dataset (4h bars are checked against Binance's own 4h candles).
  - **Indicator lengths stay in bars, not in time.** EMA 9, VWAP 24, ATR 14 and the 2 ATR stop are unchanged in bars. On 4h, EMA 9 bars = 36 hours, VWAP 24 bars = 4 days, ATR 14 bars = 56 hours.
  - The daily EMA 21 trend filter is unchanged (it is daily).
  - `min_gap_bars = 3` stays in bars, which is 12 hours on 4h.
  - The volume feature windows in the enriched output follow the bars (7 days = 42 bars on 4h).
- **Parameter.**

  | timeframe | 2h | 4h (base) | 8h |
  |---|---|---|---|
  | EMA 9 bars | 18 h | 36 h | 72 h |
  | VWAP 24 bars | 2 days | 4 days | 8 days |

- **Expected effect.**
  - Fewer trades: roughly a quarter on 4h (more than 100 is still expected) and larger moves per trade. The fee share of gross profit should fall well below 10%.
  - The effect on gross PF is unknown. Slower crosses could also give back more.
- **Success.**
  - Base 4h passes the criteria, with at least 100 trades.
  - The fee share of gross profit is below the 1h run's in both halves.
  - 2h and 8h form a plateau as defined above.

### H2: fixed_risk sizing

- **Mechanism.**
  - At 100% of equity with a 2 ATR stop, the equity at risk per trade is twice the ATR in percent: a median 1.5%, but 4 to 9% in the volatile bars where 14 of the 17 bottom-1% trades were stopped out (median ATR 2.47% vs 0.73%).
  - Sizing so that a stop-out loses a fixed share of equity removes that dependence on volatility, without touching the signal.
  - The top 1% had a median ATR of 0.80%, close to the rest, so they are much less affected than the bottom tail.
- **Rule.**
  - `[sizing] mode = "fixed_risk"` with `risk_pct = r`: lots such that the stop at entry ± 2 ATR loses r% of equity. This is the existing mode.
  - It is capped at 100% of equity, as now. The cap applies when 2 × ATR% < r, so in quiet bars the size equals today's.
- **Parameter.**

  | risk_pct | 0.75 | 1.0 (base) | 1.5 |
  |---|---|---|---|
  | capped when ATR % below | 0.375% | 0.5% | 0.75% |
  | share of trades capped (ATR quintiles of the diagnosis) | about 10% | about 25% | about 50% |

- **Expected effect.**
  - The bottom tail and max drawdown shrink.
  - PF on percent returns rises because the large losses become smaller.
  - Trade count, entries and exits are unchanged (same signals). Total return is lower in volatile years.
  - Fee drag and the second-half decay are not addressed.
- **Success.**
  - The return-method "without top 5" and "without top 1%" values are higher than the base run's.
  - Max drawdown is lower.
  - PF net is at least the base's in both halves.
  - The plateau holds.
  - It does not make the strategy pass on its own if the other criteria still fail. In that case H2 is kept as a sizing rule for later runs, not as a candidate.

### H3: Entry confirmation after N bars

- **Mechanism.**
  - Failing trades fail at once. The bottom 1% reached their MFE at a median of bar 1. 39% of all trades never reached 1 ATR in profit, and they summed to -802%.
  - A cross that reverts within a bar or two is noise around the VWAP. Requiring the cross to still hold N bars later skips those round trips and their fees.
  - The price is a later entry on the trades that do run, which the top 1% (MFE at a median bar 46) can afford.
- **Rule.** A new entry filter `confirm` (uses the deferral mechanism):
  - A cross that the trend filter allows is deferred N bars.
  - At the close of bar i+N: enter if the EMA is still on the cross side of the VWAP (EMA > VWAP for a long, EMA < VWAP for a short). Otherwise cancel. An opposite cross in between cancels it.
  - The trend filter is evaluated at the cross bar.
  - An opposite position is closed at the cross bar, as with a blocked cross (accepted on 2026-10-26).
  - The entry is sized and stopped at the confirming bar.
- **Parameter.**

  | N bars | 1 | 2 (base) | 3 |
  |---|---|---|---|

- **Expected effect.**
  - Fewer trades, mainly among those with an MFE under 1 ATR. A lower fee share, and a higher win rate and PF.
  - Winners lose about N bars of their move.
- **Success.**
  - PF net above the base in both halves.
  - The fee share of gross profit is lower than the base's.
  - The criteria pass with at least 100 trades, and the plateau holds.
  - In `report --compare`, at least 15 of the base's 17 top-1% winners are still taken (same entry or a later entry on the same move).

### H4: Breakeven stop after K ATR

- **Mechanism.**
  - The exit is the opposite EMA/VWAP cross, which comes late.
  - 68% of trades that reached 2 to 3 ATR in profit ended as losers (median realized -0.37 ATR). 44% of all losers had been at least 1 ATR in profit.
  - Moving the stop to the entry price once a trade is clearly in profit turns many of these into near-zero trades. A trade that keeps running is untouched, because a stop at entry is far below the price.
- **Rule.** A new exit plug-in `breakeven`:
  - At the close of each bar with an open trade, check whether (highest close since entry − entry fill price) × side ≥ K × ATR at entry.
  - If so, tighten the stop to the entry fill price (`move_stop`, only tightens). It is active from the next bar.
  - The level does not cover fees, so a breakeven exit loses about 0.10% plus slippage.
  - The ATR stop and the cross exit are unchanged.
- **Parameter.**

  | K (ATR at entry) | 1.5 | 2 (base) | 3 |
  |---|---|---|---|

- **Expected effect.**
  - Fewer losers among trades that reached 1.5 to 3 ATR, and a higher PF.
  - Risk: a trade pulls back to the entry before a 5+ ATR run and is stopped out. The diagnosis has no measure of pullbacks inside winning trades, so this risk is unknown.
- **Success.**
  - PF net above the base in both halves, and the criteria pass.
  - In `report --compare`, at least 15 of the base's 17 top-1% winners keep the same exit or a better one.
  - The plateau holds.

### H5: ATR trailing stop after a strong move

- **Mechanism.** Trades that reached 3 to 5 ATR realized a median of only 0.63 ATR, and winners gave back a median 57% of their MFE. A trailing stop that starts only after a strong move keeps more of the 3 to 5 ATR moves. A wide trail keeps the 5+ ATR runs mostly intact.
- **Rule.** A new exit plug-in `atr_trail`:
  - Once (highest close since entry − entry fill price) × side ≥ K × ATR at entry, at each close set the stop to the highest close since entry − T × ATR at entry for a long (lowest close + T × ATR for a short).
  - It only tightens and is active from the next bar. The ATR stop and the cross exit stay.
- **Parameters.** K = activation in ATR at entry, T = trail distance in ATR at entry.

  | | T 2 | T 3 (base) | T 4 |
  |---|---|---|---|
  | K 2 | | run | |
  | K 3 (base) | run | run | run |
  | K 4 | | run | |

  That is the base and its four direct neighbors: 5 runs.
- **Expected effect.**
  - More realized profit on 3 to 5 ATR moves and less giveback.
  - Some 5+ ATR runs are cut short, which is the main risk to the outlier-driven result.
- **Success.** As in H4, plus the median giveback of winners is lower than the base's.

### H6: Skip the first cross after a one-sided stretch

**Status: not run.** H6 waits for a separate approval after it has been shown in full.

- **Mechanism.**
  - When the EMA has stayed on one side of the VWAP for a long stretch, the 1h move is mature, and the first cross back is often a short bounce.
  - With the daily trend filter on, this is mostly a pullback inside the daily trend, and the cross then signals its end too early.
  - Diagnosis:
    - No cross in the previous 24 bars: PF 0.98 and 0.75 in the two halves.
    - Exactly one cross in the previous 48 bars: PF 0.64 and 0.84.
    - These are the only cross-count bins with PF below 1 in both halves.
- **Caveat.** This pattern was found by inspecting about 20 feature splits, so it may be chance. It overlaps with H3, so both may act on the same trades.
- **Rule.** A new entry filter `require_recent_cross`: cancel a cross if no other EMA/VWAP cross happened in the L bars before it (the cross bar itself excluded). An opposite position is still closed, as with a blocked cross.
- **Parameter.**

  | L bars | 18 | 24 (base) | 36 |
  |---|---|---|---|

- **Expected effect.** About 300 fewer trades (the crosses_24 = 0 group has 299), and a higher PF.
- **Success.** As in the general rules. The result must hold in both halves for all three values. If H3 passes too, H6's additional effect on top of H3 could only be tested as the one combination allowed above.

### H7: Long only, the spot-executable variant

- **Mechanism.**
  - A spot account cannot short. A short needs either margin, which means borrowed coins and borrowing interest, or futures, which pay or receive funding.
  - Neither cost is modeled in this backtester, so the backtested shorts are cheaper than they would be in reality.
  - H7 is the variant a spot account can execute with only the costs that are modeled: fees and slippage.
  - For reference, not as the mechanism: shorts had PF 1.26 in the first half and 0.84 in the second (-49% sum of returns), longs 1.53 and 1.23.
- **Rule.** `direction = "Long only"` (an existing parameter). A down cross only closes a long.
- **Parameter.** None. One run.
- **Expected effect.**
  - About 890 trades instead of 1,695. A higher PF and a lower fee total.
  - Time in market drops.
- **Success.**
  - The criteria pass with PF ≥ 1.3 and both halves positive.
  - 6 of the base's 17 top-1% winners were shorts. They disappear by construction, so the result has to come from the 11 long top-1% winners and the other longs. The top-1% check in `report --compare` counts the 11 longs.
  - Without neighbor values, the plateau rule does not apply.

### H8: 4h with a 24-hour VWAP

- **Mechanism.** The 1h rule compares a fast EMA with a rolling 24-hour VWAP, a one-day volume-weighted fair price. Moving to 4h while keeping that one-day reference tests whether the day-long VWAP is what matters. H1 instead keeps all lengths in bars.
- **Rule.** `timeframe = "4h"`, and only the VWAP is converted to the same time span.
  - VWAP = 6 four-hour bars = 24 hours.
  - EMA 9 and ATR 14 stay in bars (36 and 56 hours), because 9 and 14 hours are not whole numbers of 4h bars (2.25 and 3.5).
  - Stop 2 ATR, daily EMA 21 and `min_gap_bars` 3 bars as in H1.
- **Parameter.**

  | VWAP bars on 4h | 4 (16 h) | 6 (24 h, base) | 9 (36 h) |
  |---|---|---|---|

  With EMA 9 bars, VWAP 6 is shorter than the EMA. The rule then compares an EMA with a faster VWAP, which reverses the roles of the 1h rule.
- **Expected effect.** Unclear, which is why it ranks last. It is included because it is the only way to test a time-span version of the 1h logic on 4h without breaking EMA or ATR into fractional bars.
- **Success.** As in the general rules, compared both with the base and with H1.

---

## Not proposed

- **Chop filter on many recent crosses.** The diagnosis shows the opposite of the expected effect. Trades after 4 or more crosses in 48 bars had PF 2.92 and 1.29 in the two halves, above the average. Skipping them would remove some of the better trades.
- **EMA/VWAP separation filter.** There is no monotonic pattern. Q4 is weak in both halves, Q5 is not, and there is no mechanism for excluding a middle band.
- **Volume filters.** Volume vs its 24-bar average is flat, and vs its 7-day average the pattern reverses between halves.
- **ATR % filter.** High ATR was better in the first half (PF 1.32) and worse in the second (0.50). It is not stable, and H2 deals with volatility through sizing instead.
- **Hour and weekday rules.** The differences exist, for example Saturday PF 0.86 and 0.71, but the protocol excludes calendar rules without a clear mechanism. Weekend liquidity is a possible mechanism, but the pattern is not consistent across sides and halves.
- **Trend-distance filter for longs.** Longs 5 to 11 ATR above the daily EMA did best, but the pattern is not monotonic and was not checked per side across the halves.
