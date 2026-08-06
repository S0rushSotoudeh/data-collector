# EasyTrader Strategy Mapping for Box and Parity Trades

## Purpose

EasyTrader currently recognizes these strategy types:

- Covered Call
- Bull Call Spread
- Bear Call Spread
- Bull Put Spread
- Bear Put Spread
- Short Straddle
- Short Strangle

This document maps our **long box**, **short box**, and **parity** trades onto
those supported types so the broker can treat the short options as hedged legs
instead of naked sells.

## Common notation and rules

Let:

- `K1` be the lower strike and `K2` the higher strike, with `K1 < K2`.
- `C(K)` be a call at strike `K`.
- `P(K)` be a put at strike `K`.
- `S` be the underlying stock.
- `q` be the option-contract quantity.
- `m` be the number of underlying shares represented by one option contract.

All option legs inside one strategy must have the same underlying, expiry,
contract multiplier, and settlement terms. Each paired option leg uses the
same normalized quantity. A covered call requires `q * m` underlying shares
for `q` short call contracts.

## Summary mapping

| Our strategy | Register in EasyTrader as | Legs |
|---|---|---|
| Long Box | Bull Call Spread | Buy `C(K1)` + sell `C(K2)` |
| Long Box | Bear Put Spread | Buy `P(K2)` + sell `P(K1)` |
| Short Box | Bear Call Spread | Sell `C(K1)` + buy `C(K2)` |
| Short Box | Bull Put Spread | Sell `P(K2)` + buy `P(K1)` |
| Parity | Covered Call | Buy/hold `S` + sell `C(K)` |
| Parity | Standalone long option | Buy `P(K)`; no naked-sale collateral is created |

The Short Straddle and Short Strangle types are **not needed** for these three
strategies. Using either would group two short options together without the
correct protective long legs.
