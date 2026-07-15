# Long and Short Box Spreads

## 1. Purpose

A box spread combines four European options on the same underlying and with the
same expiry. When constructed correctly, its expiry payoff does not depend on
the underlying price.

This document covers:

- Long and short box construction
- Payoff and fair-value logic
- Executable bid/ask pricing
- Our execution model: **make one leg, then take the other three after the
  maker leg fills**
- Partial fills, fees, slippage, and operational risk

The box is a financing trade, not a volatility or directional trade. Before
costs, a long box resembles lending money and a short box resembles borrowing
money.

---

## 2. Contracts and Notation

Choose two strikes:

$$
K_1 < K_2
$$

All four options must have:

- The same underlying
- The same expiry
- Compatible exercise and settlement rules
- The same contract multiplier, or quantities adjusted to equal payoff units

Notation:

- $C_1$: call at the lower strike $K_1$
- $C_2$: call at the higher strike $K_2$
- $P_1$: put at the lower strike $K_1$
- $P_2$: put at the higher strike $K_2$
- $W=K_2-K_1$: box width per underlying unit
- $m$: contract multiplier
- $q$: number of normalized boxes

The fixed expiry value of the position is:

$$
V_T=q\,m\,(K_2-K_1)=q\,m\,W
$$

Premiums and the strike width must use the same currency and price scale.

---

## 3. Long Box Spread

A long box is a long bull call spread plus a long bear put spread.

| Leg | Action | Strike |
|---|---|---:|
| $C_1$ | Buy call | $K_1$ |
| $C_2$ | Sell call | $K_2$ |
| $P_1$ | Sell put | $K_1$ |
| $P_2$ | Buy put | $K_2$ |

In position notation:

$$
\boxed{+C_1-C_2-P_1+P_2}
$$

Its entry debit per underlying unit is:

$$
D_{long}=C_1-C_2-P_1+P_2
$$

At expiry it receives exactly the strike width:

$$
Payoff_{long}=W
$$

The long box is attractive when its all-in executable debit is sufficiently
below the present value of $W$:

$$
D_{long}+Costs < PV(W)
$$

The simple undiscounted profit held through expiry is:

$$
Profit_{long}=W-D_{long}-Costs
$$

For a real trading decision, use the desk's funding curve and compare the debit
with $PV(W)$ rather than treating money today and money at expiry as equal.

---

## 4. Short Box Spread

A short box reverses every long-box leg.

| Leg | Action | Strike |
|---|---|---:|
| $C_1$ | Sell call | $K_1$ |
| $C_2$ | Buy call | $K_2$ |
| $P_1$ | Buy put | $K_1$ |
| $P_2$ | Sell put | $K_2$ |

In position notation:

$$
\boxed{-C_1+C_2+P_1-P_2}
$$

The entry credit per underlying unit is:

$$
R_{short}=C_1-C_2-P_1+P_2
$$

At expiry the short box pays exactly the strike width:

$$
Payoff_{short}=-W
$$

The short box is attractive when the all-in executable credit is sufficiently
above the present value of its fixed liability:

$$
R_{short}-Costs > PV(W)
$$

The simple undiscounted profit held through expiry is:

$$
Profit_{short}=R_{short}-W-Costs
$$

Economically, the trader receives cash now and repays $W$ at expiry. Margin,
collateral, and the applicable borrowing or opportunity-cost rate therefore
matter even though the terminal option payoff is fixed.

---

## 5. Why the Payoff Is Fixed

Let $S_T$ be the underlying price at expiry.

| Expiry region | Long-box payoff |
|---|---:|
| $S_T \le K_1$ | $-(K_1-S_T)+(K_2-S_T)=W$ |
| $K_1<S_T<K_2$ | $(S_T-K_1)+(K_2-S_T)=W$ |
| $S_T \ge K_2$ | $(S_T-K_1)-(S_T-K_2)=W$ |

More explicitly, the long-box payoff is:

$$
\max(S_T-K_1,0)-\max(S_T-K_2,0)
-\max(K_1-S_T,0)+\max(K_2-S_T,0)=W
$$

The short box has the exact opposite payoff, $-W$.

---

## 6. Executable Long and Short Box Prices

Mid-prices are useful for monitoring but cannot determine whether the trade is
executable. A leg that we buy immediately must use its ask; a leg that we sell
immediately must use its bid.

If all four long-box legs were taken immediately, its executable debit would
be:

$$
D_{long,take}
=C_{1,ask}-C_{2,bid}-P_{1,bid}+P_{2,ask}
$$

If all four short-box legs were taken immediately, its executable credit would
be:

$$
R_{short,take}
=C_{1,bid}-C_{2,ask}-P_{1,ask}+P_{2,bid}
$$

These calculations must use volume-weighted executable prices for the intended
size, not only top-of-book prices.

Define the complete safety allowance:

$$
B=Fees+ExpectedSlippage+Funding+RiskBuffer+ProfitTarget
$$

Then the basic entry requirements are:

$$
D_{long} \le PV(W)-B
$$

and:

$$
R_{short} \ge PV(W)+B
$$

The production implementation must calculate fees separately for every buy and
sell. See [Iran Securities Trading Fees](fees.md).

---

## 7. Our Execution Model: One Maker, Then Three Takers

We do not begin by taking all four legs. We place one passive order as the
**maker leg**. Only after that order fills do we execute the remaining three
legs as **takers**.

```text
CALCULATE EXECUTABLE THREE-LEG HEDGE
                |
                v
       PLACE ONE MAKER ORDER
                |
      +---------+----------+
      |                    |
  NOT FILLED             FILLED
      |                    |
REPRICE/CANCEL      FREEZE FILLED QTY
                           |
                           v
             TAKE THE OTHER THREE LEGS
                           |
                           v
               RECONCILE ALL FOUR LEGS
```

“Then” means immediately after receiving a confirmed fill. It does not mean
waiting for a later market opportunity. Between the first fill and completion
of the other three legs, the strategy is not a box and has delta, gamma, vega,
and price-gap risk.

The three hedge orders should be submitted together when the venue and order
gateway allow it. Use aggressive limit orders with explicit price collars,
normally IOC or FOK where supported. Unbounded market orders can turn a small
expected box edge into a large loss.

---

## 8. Maker Leg and Taker Directions

Any one of the four legs can be selected as the maker. After it fills, the
other three orders must follow the same row's box directions.

### Long box

| Possible maker | Maker side | Three taker orders after fill |
|---|---|---|
| $C_1$ | Buy | Sell $C_2$, sell $P_1$, buy $P_2$ |
| $C_2$ | Sell | Buy $C_1$, sell $P_1$, buy $P_2$ |
| $P_1$ | Sell | Buy $C_1$, sell $C_2$, buy $P_2$ |
| $P_2$ | Buy | Buy $C_1$, sell $C_2$, sell $P_1$ |

### Short box

| Possible maker | Maker side | Three taker orders after fill |
|---|---|---|
| $C_1$ | Sell | Buy $C_2$, buy $P_1$, sell $P_2$ |
| $C_2$ | Buy | Sell $C_1$, buy $P_1$, sell $P_2$ |
| $P_1$ | Buy | Sell $C_1$, buy $C_2$, sell $P_2$ |
| $P_2$ | Sell | Sell $C_1$, buy $C_2$, buy $P_1$ |

The maker should normally be the leg with the best combination of:

- Fill probability
- Maker price improvement
- Stable order book and low adverse selection
- Sufficient depth in all three taker legs
- Fast and reliable fill notifications

The maker leg must not be chosen only because its own spread is wide. The
quality and depth of the three-leg hedge determine whether the complete trade
is safe.

---

## 9. Calculating the Maker Quote

Represent every entry cash flow as a signed cost:

- Buy premium: positive cost
- Sell premium: negative cost

Let:

- $x$: proposed maker price
- $s_m=+1$ if the maker order buys, and $s_m=-1$ if it sells
- $H$: signed executable cost of the other three legs, including their bid/ask
  sides and intended depth
- $T$: maximum permitted signed cost for the complete strategy

The completed package cost is:

$$
C_0=s_mx+H
$$

For a long box:

$$
T_{long}=PV(W)-B
$$

For a short box, whose acceptable entry is a sufficiently large credit:

$$
T_{short}=-PV(W)-B
$$

In both cases require:

$$
C_0 \le T
$$

Therefore:

### When the maker leg is a buy

The highest safe passive bid is:

$$
\boxed{x_{max}=T-H}
$$

Round the result down to a valid tick.

### When the maker leg is a sell

The lowest safe passive ask is:

$$
\boxed{x_{min}=H-T}
$$

Round the result up to a valid tick.

Recalculate $H$ whenever any of the three taker books, fees, funding inputs, or
risk limits change. Cancel or replace the maker quote when its safe price or
safe size changes.

---

## 10. Worked Example

Assume:

$$
K_1=100,\qquad K_2=110,\qquad W=10
$$

Suppose we want a long box and make a passive bid in $C_1$. At the intended
size, the other three legs are executable at:

| Taker leg | Action | Executable price | Signed cost |
|---|---|---:|---:|
| $C_2$ | Sell | 7.80 bid | $-7.80$ |
| $P_1$ | Sell | 2.20 bid | $-2.20$ |
| $P_2$ | Buy | 6.50 ask | $+6.50$ |

Thus:

$$
H=-7.80-2.20+6.50=-3.50
$$

Assume the present value of the width is $9.80$ and the combined fee,
slippage, risk, and profit allowance is $0.30$:

$$
T_{long}=9.80-0.30=9.50
$$

The maximum maker bid for $C_1$ is:

$$
x_{max}=T-H=9.50-(-3.50)=13.00
$$

If our $C_1$ bid fills at $12.90$, immediately taking the other legs gives:

$$
D_{long}=12.90-7.80-2.20+6.50=9.40
$$

The expected value after the $0.30$ allowance is:

$$
9.80-9.40-0.30=0.10
$$

per underlying unit. Multiply by the contract multiplier and filled box
quantity to obtain the trade-level amount.

If one of the taker prices moves before execution, recompute using actual fills.
The pre-fill expected edge is not realized profit.

---

## 11. Partial Fills and Sizing

The maker order may fill partially. Hedge only the confirmed cumulative filled
quantity that has not already been hedged:

$$
q_{\text{to hedge}}
=q_{\text{maker filled}}-q_{\text{already hedged}}
$$

For every fill event:

1. Read the authoritative cumulative maker fill quantity.
2. Make the event idempotent so duplicate messages cannot create duplicate
   hedges.
3. Calculate the unhedged increment.
4. Submit all three taker orders for that increment.
5. Record acknowledgements and fills by leg.
6. Retry or escalate any residual quantity under strict price and risk limits.
7. Verify that all four normalized leg quantities match.

Before quoting, cap maker size by the minimum safely executable depth across all
three taker legs:

$$
q_{maker,max}
\le
\min(q_{taker,1},q_{taker,2},q_{taker,3},q_{risk},q_{margin})
$$

The depth calculation must include quantity ratios when contract multipliers
differ. If exact payoff normalization is impossible, do not call the position a
box.

---

## 12. Failure Handling

### Maker fills but a taker leg does not

The position is incomplete. Do not report box profit or fixed payoff. First:

1. Cancel any obsolete residual orders.
2. Re-read the missing leg's book.
3. Complete it within the emergency price collar if risk permits.
4. If completion is impossible, flatten or delta-hedge according to the desk's
   incident policy.
5. Stop new maker quotes until positions and orders reconcile.

### Market data is stale

Cancel the maker order. Three-leg hedge prices are valid only when all four
books are live, synchronized, and tradable.

### Fill event is delayed or duplicated

Use exchange order state and cumulative filled quantity as the source of truth.
Hedge logic must be idempotent.

### Price moves through the expected edge

Complete or flatten according to the configured loss and exposure limits. Do
not leave a directional option portfolio open merely to wait for the original
edge to return.

---

## 13. Risk and Validity Checks

A textbook fixed payoff does not guarantee a risk-free production trade. Check:

- **Exercise style:** early exercise of American-style options can break the
  expected cash-flow timing.
- **Settlement:** physical and cash-settled contracts have different delivery,
  assignment, and funding requirements.
- **Contract specifications:** multiplier, expiry, underlying, price scale, and
  strike must match.
- **Assignment and margin:** a short option can require substantial collateral
  even when the complete box has fixed terminal value.
- **Liquidity:** displayed quantity can disappear before taker orders arrive.
- **Fees:** charge all four opening trades and any closing, exercise, assignment,
  or settlement costs.
- **Funding:** long and short boxes may require different lending, borrowing,
  collateral, and opportunity-cost curves.
- **Rounding:** quote buys down and sells up when protecting the required edge.
- **Position limits:** enforce limits during the incomplete-box interval, not
  only after all four legs fill.
- **Expiry operations:** verify exercise instructions and available cash or
  deliverable inventory before cutoff times.

Boxes using American options or contracts with uncertain exercise and
settlement behavior should not be valued as perfectly fixed cash flows without
an explicit early-exercise and operations model.

---

## 14. Production State Machine

```text
SCANNING
  -> QUOTING_ONE_MAKER
  -> MAKER_PARTIAL_OR_FILLED
  -> HEDGING_THREE_TAKERS
  -> RECONCILING
  -> COMPLETE

Any state
  -> CANCELING        when data, edge, or limits fail before a maker fill
  -> EMERGENCY_HEDGE  when a maker fill leaves unmatched exposure
  -> HALTED           when orders and positions cannot be reconciled
```

Required records for each box attempt:

- Strategy ID and maker order ID
- Underlying, expiry, $K_1$, $K_2$, and multiplier
- Long-box or short-box direction
- Maker leg, side, quote price, and fill timestamps
- Three-leg hedge snapshot used to calculate the maker quote
- Every order acknowledgement, fill price, and fill quantity
- Expected edge before fill
- Realized entry cash flow after all fills
- Fees, slippage, funding assumption, and residual exposure
- Final reconciliation status

---

## 15. Pre-Trade and Post-Trade Checklist

### Before placing the maker order

- [ ] All contracts share the correct underlying and expiry.
- [ ] Strike order is $K_1<K_2$.
- [ ] Multipliers and quantity ratios produce equal payoff units.
- [ ] Exercise and settlement rules are acceptable.
- [ ] All four books are fresh and the market is open.
- [ ] The three taker legs have enough executable depth.
- [ ] Maker price includes all four-leg fees, slippage, funding, risk, and target
  profit.
- [ ] Margin, position, and order-rate limits pass.
- [ ] Emergency hedge and kill-switch paths are available.

### After a maker fill

- [ ] Freeze the confirmed unhedged fill quantity.
- [ ] Send the three taker orders immediately.
- [ ] Track partial and rejected taker orders.
- [ ] Cancel remaining maker quantity if hedge capacity has fallen.
- [ ] Reconcile normalized quantities on all four legs.
- [ ] Calculate realized entry debit or credit from actual fills.
- [ ] Verify fees, residual Greeks, margin, and settlement obligations.

---

## 16. Summary

Long box:

$$
+C_1-C_2-P_1+P_2
\quad\Longrightarrow\quad
+W\text{ at expiry}
$$

Short box:

$$
-C_1+C_2+P_1-P_2
\quad\Longrightarrow\quad
-W\text{ at expiry}
$$

Our live execution loop is:

```text
PRICE THE THREE-LEG HEDGE
-> MAKE ONE LEG
-> WHEN FILLED, TAKE THE OTHER THREE
-> HANDLE PARTIAL FILLS
-> RECONCILE
-> VERIFY REALIZED EDGE
```

The key rule is that the maker quote is derived from the prices at which the
other three legs can actually be taken. Until all four legs are confirmed and
reconciled, the strategy is an exposed multi-leg position, not a completed box.
