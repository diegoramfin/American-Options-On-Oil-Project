# Open review items

1. **Underlying.** We price options on the BNO ETF shares, not on Brent crude or
   Brent futures. The model treats BNO as a stock with no dividend (q = 0). Confirm
   BNO has made no distributions over the sample period.
2. **Historical options data.** Yahoo gives no past chains, and no free source has
   been verified. Decide how the team gets past chains, or accept snapshots only.
3. **Quote quality.** About a third of put-call pairs fail the American bounds
   (S − K < C − P < S − K·e^(−rT)), mostly on the shortest expiries. See the Validation
   sheet. Decide the cleaning rule before relying on the smile or the market comparison.
4. **Snapshot timing.** The 2026-11-06 snapshot was pulled at 12:19 ET with the
   market open, so S is an intraday price taken at the same moment as the quotes, and
   the last daily return is a partial day. Pulling after 4 pm ET gives a true close,
   but quotes may then be stale or zero. Agree on a pull time for the frozen date.
5. **Risk-free rate.** We use the 13-week T-bill from Yahoo (`^IRX`). Check whether
   the team prefers a different source, such as FRED.
6. **Tree settings.** One time step per business day, at least 100. The Tree sheet
   shows the convergence; decide whether that is enough for the comparison you need.
7. **Test tolerances.** The Hull checks allow 0.005 because Hull prints two or three
   decimals; our values match every printed digit. Confirm that tolerance is acceptable.
8. **LSM settings.** 20,000 paths per expiry and at most 50 exercise dates. Long
   expiries are therefore Bermudan approximations and LSM is slightly low-biased; check
   the LSM-confirmed-by-tree pass rate on the Validation sheet.
9. **Not built yet.** The hedging backtest and the final report.
