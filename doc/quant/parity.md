# Put–Call Parity for Option Market Making

## 1. Why Put–Call Parity Matters

Put–call parity is one of the most important no-arbitrage relationships in options.

It connects four instruments with the same underlying and expiry:

- Call option
- Put option
- Underlying asset
- Cash or financing

For European options without dividends:

$$
C - P = S - K e^{-rT}
$$

Equivalently:

$$
C + K e^{-rT} = P + S
$$

Where:

- $C$: call price
- $P$: put price
- $S$: underlying spot price
- $K$: strike price
- $r$: continuously compounded risk-free rate
- $T$: time to expiry in years
- $K e^{-rT}$: present value of the strike

The equation says that these two portfolios have the same payoff at expiry:

### Portfolio A

- Long one call
- Hold enough cash today to pay the strike at expiry

### Portfolio B

- Long one put
- Long one share of the underlying

Because both portfolios have identical expiry payoffs, they should have approximately the same value today.

---

## 2. Payoff Proof from Scratch

Consider the portfolios:

$$
\text{Portfolio A} = C + PV(K)
$$

$$
\text{Portfolio B} = P + S
$$

### Assumptions and units

This payoff proof is stated **per underlying share**. It assumes that the call
and put are European, have the same underlying, strike $K$, and expiry $T$;
there are no dividends or other carry payments before expiry; and the
underlying can be traded and shorted without constraints. If an option
contract represents $m$ shares, multiply every payoff below by $m$.

The cash leg is $PV(K)$ today and is worth exactly $K$ at expiry. Let $S_T$
denote the underlying price at expiry. There are two exhaustive payoff
regions.

### Underlying finishes above the strike: $S_T > K$

The call has positive intrinsic value, while the put expires worthless.

Portfolio A:

$$
(S_T-K)+K=S_T
$$

The put expires worthless.

Portfolio B:

$$
0+S_T=S_T
$$

### Underlying finishes at or below the strike: $S_T \le K$

The call expires worthless, while the put has value only when $S_T<K$.

Portfolio A:

$$
0+K=K
$$

The put is exercised.

Portfolio B:

$$
(K-S_T)+S_T=K
$$

Both portfolios have identical payoffs in every state.

Therefore:

$$
C + PV(K)=P+S
$$

and:

$$
C=P+S-PV(K)
$$

---

# 3. Synthetic Instruments

Put–call parity allows one instrument to be replicated using the others.

## Synthetic Call

$$
C_{\text{synthetic}}=P+S-PV(K)
$$

A call can be replicated by:

- Long put
- Long underlying
- Borrow the present value of the strike

---

## Synthetic Put

$$
P_{\text{synthetic}}=C-S+PV(K)
$$

A put can be replicated by:

- Long call
- Short underlying
- Lend the present value of the strike

---

## Synthetic Stock

$$
S_{\text{synthetic}}=C-P+PV(K)
$$

A stock position can be replicated by:

- Long call
- Short put
- Hold the present value of the strike

---

## Synthetic Bond

$$
PV(K)=P+S-C
$$

A bond paying $K$ at expiry can be replicated by:

- Long put
- Long underlying
- Short call

---

# 4. Parity with Dividends and Carry

For an underlying with known cash dividends:

$$
C-P=S-PV(D)-PV(K)
$$

Where:

$$
PV(D)=\text{present value of dividends paid before expiry}
$$

So:

$$
C_{\text{synthetic}}=P+S-PV(D)-PV(K)
$$

For an asset with continuous dividend yield $q$:

$$
C-P=S e^{-qT}-K e^{-rT}
$$

Therefore:

$$
C_{\text{synthetic}}=P+S e^{-qT}-K e^{-rT}
$$

In practice, the theoretical relationship may also need adjustments for:

- Stock borrow cost
- Short-sale constraints
- Funding cost
- Margin cost
- Settlement rules
- Exercise style
- Taxes
- Trading fees
- Contract multiplier
- Discrete dividends
- Stale quotes

For market making, the correct equation is not simply textbook parity. It is parity after all executable costs and operational constraints.

---

# 5. Executable Parity

Using mid-prices is useful for monitoring, but it is not enough for trading.

To hedge a filled option, the other legs must be executed at their actual bid or ask prices.

Suppose you want to buy a call and hedge it by:

- Selling the corresponding put
- Buying the underlying
- Borrowing cash

The relevant executable synthetic call cost is approximately:

$$
C_{\text{synthetic,buy}}
=
P_{\text{bid}}
+
S_{\text{ask}}
-
PV(K)
+
\text{costs}
$$

Why?

- You sell the put at its bid.
- You buy the stock at its ask.
- You borrow the strike financing amount.
- You pay fees, spread, slippage, and financing costs.

If instead you want to sell a call and hedge it by:

- Buying the put
- Selling the underlying
- Lending cash

The executable synthetic call sale value is approximately:

$$
C_{\text{synthetic,sell}}
=
P_{\text{ask}}
+
S_{\text{bid}}
-
PV(K)
-
\text{costs}
$$

This creates a no-arbitrage interval rather than one exact fair value:

$$
C_{\text{synthetic,sell}}
\le C \le
C_{\text{synthetic,buy}}
$$

A market maker should normally quote inside this interval only when the expected edge remains positive after all costs.

---

# 6. Core Market-Making Idea

For a call option, estimate its value from parity:

$$
C^*=P+S-PV(K)
$$

Then include a required profit margin and execution costs.

A simple call bid can be written as:

$$
\text{Call Bid}
=
C_{\text{parity}}
-
\text{required edge}
-
\text{expected hedge cost}
-
\text{risk buffer}
$$

A simple call ask can be written as:

$$
\text{Call Ask}
=
C_{\text{parity}}
+
\text{required edge}
+
\text{expected hedge cost}
+
\text{risk buffer}
$$

The market-making cycle is:

1. Observe the put, stock, rates, fees, and market depth.
2. Calculate the executable parity value.
3. Add the desired profit margin and risk buffer.
4. Submit a passive call bid or ask.
5. Recalculate continuously.
6. Cancel or replace the quote if its fair value changes.
7. If the call quote fills, execute the other parity legs.
8. Verify that the final portfolio is hedged.
9. Manage any residual risk caused by partial fills or slippage.

---

# 7. Making a Bid for a Call

Suppose you want to make a passive bid in a call.

If the bid fills, you become long the call.

From parity:

$$
C=P+S-PV(K)
$$

To offset a long call, trade the opposite synthetic call:

$$
-C=-P-S+PV(K)
$$

So after buying the call, the ideal hedge is:

- Sell the corresponding put
- Sell the underlying
- Lend or hold the present value of the strike

The resulting portfolio is:

$$
+C-P-S+PV(K)=0
$$

This is the clean parity hedge for a long call.

Therefore, before placing the call bid, calculate how much money you could receive from immediately executing the hedge.

Let:

$$
H_{\text{long call}}
=
P_{\text{bid}}
+
S_{\text{bid}}
-
PV(K)
$$

This is the approximate hedge value available after buying the call, before costs.

The maximum rational call bid is:

$$
C_{\text{bid,max}}
=
P_{\text{bid}}
+
S_{\text{bid}}
-
PV(K)
-
\text{all costs}
-
\text{required profit}
$$

A more complete formula is:

$$
C_{\text{bid}}
=
P_{\text{bid,executable}}
+
S_{\text{bid,executable}}
-
PV(K)
-
F
-
L
-
R
-
M
$$

Where:

- $F$: commissions, exchange fees, clearing fees, taxes
- $L$: expected slippage and market impact
- $R$: risk buffer
- $M$: required profit margin

This is the central idea:

> Bid for the call only at a price that still leaves profit after immediately selling the put and the stock and accounting for financing and costs.

---

# 8. Making an Ask for a Call

If your call ask fills, you become short the call.

To offset a short call, buy the synthetic call:

- Buy the corresponding put
- Buy the underlying
- Borrow the present value of the strike

The final portfolio is:

$$
-C+P+S-PV(K)=0
$$

The minimum rational call ask is approximately:

$$
C_{\text{ask,min}}
=
P_{\text{ask}}
+
S_{\text{ask}}
-
PV(K)
+
\text{all costs}
+
\text{required profit}
$$

More completely:

$$
C_{\text{ask}}
=
P_{\text{ask,executable}}
+
S_{\text{ask,executable}}
-
PV(K)
+
F
+
L
+
R
+
M
$$

---

# 9. Worked Example: Setting an Executable Call Bid

The following is a **per-share** example for one European call contract. It
uses executable quotes, not mid-prices. The option contract multiplier is
$m=100$ shares, so the quoted prices and calculations below are per share and
the final result is multiplied by 100 for one contract.

### Market, contract, and financing assumptions

- The call and put have the same underlying, strike $K=100.00$, and expiry in
  $T=30/365$ years.
- The underlying pays no dividends before expiry; there is no stock-borrow fee
  during the holding period; and stock borrow is already confirmed for the
  required 100 shares.
- The continuously compounded cash lending/borrowing rate is $r=8.00\%$ per
  year. Therefore the present value of the strike is

  $$
  PV(K)=100.00e^{-0.08(30/365)}=99.3446
  $$

- At the intended size, the executable order book has at least one put
  contract bid at 4.80 and at least 100 stock shares bid at 100.00. The best
  asks (5.00 for the put and 100.10 for the stock) are shown only to make the
  spread explicit; they are not usable when selling the hedge.
- All prices are in the same currency and settlement convention. The price
  tick is 0.01.
- Estimated costs are 0.03 for selling the put, 0.02 for selling the stock,
  and 0.01 for financing/settlement, or 0.06 per share in total. These costs
  exclude the risk reserve below.
- The desk requires 0.15 per share of profit and reserves 0.08 per share for
  quote-to-hedge price movement and partial-fill risk.

If the passive call bid fills, the market maker is long the call. The exact
parity hedge is to sell the matching put at its bid, sell 100 shares at their
bid, and lend the strike present value. The executable hedge value per share
is:

$$
H_{\text{long call}}
=4.80+100.00-99.3446
=5.4554
$$

The unrounded maximum bid that preserves the stated edge is:

$$
\begin{aligned}
C_{\text{bid,max}}
&=5.4554-0.06-0.15-0.08\\
&=5.1654
\end{aligned}
$$

Because a bid must be rounded **down** to the 0.01 tick, the system can quote:

$$
\boxed{C_{\text{bid}}=5.16\text{ per share}}
$$

For one 100-share contract, the order notional is $516.00$. If it fills at
5.16 and both hedge legs fill at the assumed executable bids, the realized
net edge is:

$$
(5.4554-5.1600-0.0600)\times100=23.54
$$

This $23.54$ consists of the $15.00 profit target, the $8.00 risk reserve that
was not needed in this favorable outcome, and $0.54 created by rounding down.
It is not a guaranteed profit: a lower hedge fill, borrow recall, fee change,
or failure to complete the package can consume the reserve. The quote must be
cancelled or repriced when any stated input is no longer valid.

---

# 10. Cancel and Replace Logic

Your quote is valid only while the inputs used to calculate it remain valid.

Recalculate whenever one of the following changes:

- Put bid or ask
- Stock bid or ask
- Available depth
- Interest rate
- Dividend estimate
- Fees
- Time to expiry
- Borrow availability
- Volatility regime
- Inventory
- Margin utilization
- Hedge venue status
- Trading halt or price limit status

For a call bid:

$$
B_t
=
P_{\text{bid},t}
+
S_{\text{bid},t}
-
PV_t(K)
-
F_t
-
L_t
-
R_t
-
M_t
$$

Let the current working order price be $Q_t$.

Cancel or replace it when:

$$
|B_t-Q_t|>\delta
$$

Where $\delta$ is the repricing threshold.

You may also cancel immediately if:

$$
\text{Expected Edge}<\text{Minimum Edge}
$$

or if the hedge is no longer executable at the required size.

---

## Stale Quote Risk

A quote can become dangerous when:

- The stock moves.
- The put quote disappears.
- The available hedge quantity falls.
- The market becomes locked or crossed.
- The feed is delayed.
- The option market reacts more slowly than the stock.
- A volatility event occurs.
- The underlying reaches a price limit.
- The hedge leg is halted.

A market maker must use quote age limits.

Example:

```text
Cancel the call bid if:
- stock quote age > 100 ms
- put quote age > 100 ms
- hedge depth < requested option size
- calculated edge < minimum edge
- stock moved more than configured threshold
```

The exact numbers depend on market speed and infrastructure.

---

# 11. What to Do After a Call Bid Fills

Suppose your passive call bid fills.

You are now:

$$
+\text{Call}
$$

Your intended hedge is:

$$
-\text{Put}
-\text{Stock}
+PV(K)
$$

Operationally:

1. Detect the call fill.
2. Determine the exact filled quantity.
3. Immediately submit hedge orders.
4. Sell the put.
5. Sell the corresponding amount of stock.
6. Record financing or cash exposure.
7. Check whether all hedge legs filled.
8. Cancel any unnecessary remaining orders.
9. Recalculate the final realized edge.
10. Manage residual positions.

For contract multiplier $m$ and filled option quantity $n$:

$$
\text{Stock hedge quantity}=n \times m
$$

If one option contract represents 1,000 shares and 3 calls fill:

$$
\text{Stock quantity}=3 \times 1{,}000=3{,}000
$$

The put quantity is normally the same number of contracts:

$$
\text{Put quantity}=n
$$

---

# 12. Fill the Other Pairs

The phrase “fill the other pairs” should mean completing the parity package.

For a filled long call:

| Filled leg | Hedge action |
|---|---|
| Long call | Sell same-strike, same-expiry put |
| Long call | Sell underlying shares |
| Long call | Hold or lend strike present value |

For a filled short call:

| Filled leg | Hedge action |
|---|---|
| Short call | Buy same-strike, same-expiry put |
| Short call | Buy underlying shares |
| Short call | Borrow strike present value |

All option legs must have:

- Same underlying
- Same strike
- Same expiry
- Compatible contract multiplier
- Compatible settlement method

Otherwise, the hedge is not exact parity.

---

# 13. Partial-Fill Risk

The clean parity trade assumes simultaneous execution.

Real markets create leg risk.

Example:

- Call bid fills.
- Put sell order fills only partially.
- Stock hedge fills at a worse price.
- The remaining position is exposed.

Possible temporary residual exposures include:

- $\Delta$ (delta) risk
- $\Gamma$ (gamma) risk
- $\mathcal{V}$ (vega) risk
- Directional stock risk
- Volatility skew risk
- Funding risk
- Short-stock risk
- Early-exercise risk
- Dividend risk

A robust system must have explicit partial-fill rules.

Example:

```text
If call fills:
    hedge stock immediately
    hedge put immediately

If only stock fills:
    continue working put hedge for a short timeout
    then cross the spread if residual risk is too large

If only put fills:
    hedge stock aggressively
    monitor net delta

If hedge is impossible:
    flatten the filled call or use the nearest available substitute
```

---

# 14. Hedge Priority

The ideal priority depends on the market.

A common approach is:

1. Hedge the fastest and most liquid risk first.
2. Then complete the exact parity package.
3. Finally optimize financing and inventory.

Often the underlying is the most liquid leg, so the system may hedge stock first.

However, stock alone removes mainly delta risk. It does not eliminate the relative-value exposure between the call and put.

For exact parity convergence, both the put and stock legs are needed.

---

# 15. Two Execution Styles

## Style A: Exact Parity Completion

After the call fills:

- Immediately cross the spread in the put.
- Immediately cross the spread in the stock.
- Lock the parity profit.

Advantages:

- Low market risk
- Fast risk removal
- Clear realized profit

Disadvantages:

- Pays spread on hedge legs
- Higher fees
- More slippage
- Lower apparent edge

---

## Style B: Passive Hedge Completion

After the call fills:

- Place passive orders in the put and stock.
- Wait for better execution.

Advantages:

- Lower spread cost
- Better expected execution price

Disadvantages:

- Significant leg risk
- Profit is not locked
- Inventory can grow
- Adverse selection can erase the edge

For a low-risk arbitrage system, aggressive hedge completion is usually safer.

---

# 16. Quote Size Must Respect Hedge Depth

Do not quote more option size than can be hedged.

For a call bid, the executable hedge quantity is limited by:

$$
Q_{\max}
=
\min
\left(
Q_{\text{put bid}},
\frac{Q_{\text{stock bid}}}{m},
Q_{\text{margin}},
Q_{\text{borrow}}
\right)
$$

Where:

- $Q_{\text{put bid}}$: put contracts available at usable prices
- $Q_{\text{stock bid}}$: shares available at usable prices
- $m$: option multiplier
- $Q_{\text{margin}}$: size allowed by margin
- $Q_{\text{borrow}}$: shortable stock capacity

For multiple book levels, calculate the volume-weighted hedge price rather than using only the best bid or ask.

---

# 17. Depth-Aware Pricing

Suppose you want to bid for 10 call contracts.

The first 10 contracts of put liquidity may not all exist at the best bid.

Similarly, selling the required stock quantity may consume multiple stock bid levels.

Use volume-weighted executable prices:

$$
\bar{P}_{\text{sell}}(q)
=
\frac{\sum_i p_i q_i}{q}
$$

$$
\bar{S}_{\text{sell}}(qm)
=
\frac{\sum_j s_j x_j}{qm}
$$

Then:

$$
C_{\text{bid}}(q)
=
\bar{P}_{\text{sell}}(q)
+
\bar{S}_{\text{sell}}(qm)
-
PV(K)
-
\text{costs}(q)
-
\text{profit target}(q)
$$

This means the correct quote may depend on size.

A 1-contract bid can be profitable while a 20-contract bid is not.

---

# 18. Inventory-Aware Quoting — $\Delta$, $\Gamma$, and vega

Even parity market making can create inventory because hedges may be delayed or incomplete.

Let:

- $I_C$: call inventory
- $I_P$: put inventory
- $I_S$: stock inventory
- $\Delta_{\mathrm{net}}$: net delta
- $\mathcal{V}_{\mathrm{net}}$: net vega
- $\Gamma_{\mathrm{net}}$: net gamma

Adjust quotes based on inventory.

Example:

$$
\text{Adjusted Call Bid}
=
\text{Base Call Bid}
-
\lambda_\Delta \Delta_{\mathrm{net}}
-
\lambda_{\mathcal{V}}\mathcal{V}_{\mathrm{net}}
-
\lambda_{\Gamma}\Gamma_{\mathrm{net}}
$$

If you are already too long calls, reduce the call bid or stop bidding.

If you are too short calls, increase the bid or reduce the ask.

Possible controls:

- Maximum call inventory
- Maximum put inventory
- Maximum net delta
- Maximum net gamma
- Maximum net vega
- Maximum short-stock position
- Maximum margin utilization
- Maximum exposure per expiry
- Maximum exposure per strike

---

# 19. American Options

The exact textbook parity equation applies directly to European options.

For American options, early exercise creates inequalities rather than one exact equality.

For non-dividend-paying stock:

$$
S-K \le C_A-P_A \le S-PV(K)
$$

The exact bounds depend on:

- Dividend timing
- Interest rates
- Early exercise incentives
- Borrow cost
- Settlement rules

A market maker should not blindly use European parity for American options.

Near dividend dates, deep in-the-money calls may be exercised early.

Deep in-the-money puts may also have early-exercise value when rates are positive.

---

# 20. Profit Calculation

For a long-call parity package:

- Buy call at $C_f$$
- Sell put at $P_h$$
- Sell stock at $S_h$$
- Allocate $PV(K)$ to the cash leg

Gross edge:

$$
E_{\text{gross}}
=
P_h+S_h-PV(K)-C_f
$$

Net edge:

$$
E_{\text{net}}
=
E_{\text{gross}}
-
\text{fees}
-
\text{slippage}
-
\text{funding}
-
\text{borrow cost}
-
\text{tax}
$$

For $n$ contracts and multiplier $m$:

$$
\text{Total Net Profit}
=
E_{\text{net}} \times n \times m
$$

Be careful: some markets quote option premiums per share, while others quote per contract.

---

# 21. Recommended System Architecture

A parity market-making system can be divided into the following components.

## Market Data Engine

Tracks:

- Option order books
- Underlying order book
- Trades
- Interest rates
- Dividends
- Contract specifications
- Trading status
- Quote timestamps

## Valuation Engine

Calculates:

- Present value of strike
- Executable synthetic prices
- Fair bid and ask
- Fees
- Slippage
- Risk buffers
- Inventory adjustment

## Quote Engine

Decides:

- Whether to quote
- Bid and ask prices
- Quote size
- Repricing threshold
- Cancel conditions
- Queue position policy

## Execution Engine

Handles:

- New orders
- Cancels
- Replacements
- Partial fills
- Hedge orders
- Retry logic
- Exchange rejects

## Risk Engine — $\Delta$, $\Gamma$, and vega

Monitors:

- $\Delta$ (delta)
- $\Gamma$ (gamma)
- $\mathcal{V}$ (vega)
- Stock inventory
- Margin
- Borrow
- Position limits
- Loss limits
- Feed quality
- Hedge availability

## Reconciliation Engine

Verifies:

- Exchange positions
- Internal positions
- Filled quantities
- Cash balances
- Fees
- Realized profit
- Open hedge residuals

---

# 22. Simplified Quoting Algorithm

```python
def compute_call_bid(
    put_bid,
    stock_bid,
    pv_strike,
    fees,
    slippage,
    risk_buffer,
    target_profit,
):
    synthetic_exit_value = put_bid + stock_bid - pv_strike

    call_bid = (
        synthetic_exit_value
        - fees
        - slippage
        - risk_buffer
        - target_profit
    )

    return call_bid
```

Quote management:

```python
while market_is_open:
    data = read_latest_market_data()

    if data.is_stale:
        cancel_call_bid()
        continue

    if not hedge_is_available(data):
        cancel_call_bid()
        continue

    fair_bid = compute_call_bid(
        put_bid=data.put_bid,
        stock_bid=data.stock_bid,
        pv_strike=data.pv_strike,
        fees=estimate_fees(data),
        slippage=estimate_slippage(data),
        risk_buffer=calculate_risk_buffer(data),
        target_profit=target_profit,
    )

    fair_bid = round_down_to_tick(fair_bid)

    if expected_edge(fair_bid, data) < minimum_edge:
        cancel_call_bid()
        continue

    size = calculate_hedgeable_size(data)

    if size <= 0:
        cancel_call_bid()
        continue

    if no_working_order():
        place_call_bid(price=fair_bid, size=size)

    elif working_price() != fair_bid:
        cancel_and_replace_call_bid(
            price=fair_bid,
            size=size,
        )
```

---

# 23. Fill Handler

```python
def on_call_bid_fill(fill):
    option_qty = fill.quantity
    multiplier = fill.contract_multiplier
    stock_qty = option_qty * multiplier

    # A call bid fill creates a long-call position.
    # Complete the opposite synthetic call:
    # sell put, sell stock, hold PV(K).

    put_result = sell_put_aggressively(
        strike=fill.strike,
        expiry=fill.expiry,
        quantity=option_qty,
    )

    stock_result = sell_stock_aggressively(
        symbol=fill.underlying,
        quantity=stock_qty,
    )

    record_cash_leg(
        amount=present_value_of_strike(
            strike=fill.strike,
            expiry=fill.expiry,
            quantity=option_qty,
            multiplier=multiplier,
        )
    )

    residual = calculate_residual_risk(
        call_fill=fill,
        put_fill=put_result,
        stock_fill=stock_result,
    )

    if residual.exceeds_limit:
        emergency_flatten(residual)

    record_realized_edge(
        call_fill=fill,
        put_fill=put_result,
        stock_fill=stock_result,
    )
```

---

# 24. Event-Driven State Machine

A useful implementation model is a state machine.

## State: IDLE

No active quote.

Move to `QUOTING` when:

- Data is fresh.
- Hedge is available.
- Expected edge is sufficient.
- Risk limits allow quoting.

## State: QUOTING

A passive call order is active.

Actions:

- Recalculate fair value.
- Cancel if stale.
- Replace if price changes.
- Reduce size if hedge depth falls.
- Stop if inventory limits are reached.

Move to `HEDGING` when a fill occurs.

## State: HEDGING

The call has filled and hedge orders are being executed.

Actions:

- Send put hedge.
- Send stock hedge.
- Monitor partial fills.
- Reprice aggressively if necessary.

Move to `HEDGED` when all legs are complete.

Move to `EMERGENCY` if risk exceeds limits.

## State: HEDGED

The parity package is complete.

Actions:

- Record profit.
- Release quote capacity.
- Reconcile positions.

## State: EMERGENCY

The system cannot complete the intended hedge safely.

Actions may include:

- Cross remaining hedge legs.
- Flatten the option.
- Use a substitute strike.
- Use another expiry temporarily.
- Stop quoting.
- Alert the operator.

---

# 25. Practical Safety Rules

A production system should include at least these controls:

1. Never quote using stale stock or put prices.
2. Never quote more size than available hedge depth.
3. Cancel quotes when the hedge market disappears.
4. Recalculate after every order-book update.
5. Use executable bid and ask prices, not only mid-prices.
6. Include all fees and taxes before quoting.
7. Include stock borrow and funding costs.
8. Handle partial fills explicitly.
9. Use maximum quote age.
10. Use maximum order lifetime.
11. Use maximum inventory limits.
12. Use a kill switch.
13. Stop after repeated hedge rejects.
14. Stop if position reconciliation fails.
15. Stop if exchange timestamps or local timestamps become unreliable.
16. Separate expected profit from risk buffer.
17. Log every valuation input used for every quote.
18. Recompute profit using actual fill prices.
19. Test contract multipliers carefully.
20. Treat dividend dates and expiry days as special regimes.

---

# 26. Common Mistakes

## Mistake 1: Using Mid-Prices

Mid-price parity can show a theoretical opportunity that cannot be executed.

Always calculate both:

- Synthetic buy price
- Synthetic sell price

---

## Mistake 2: Wrong Hedge Direction

For a filled long call, the parity hedge is:

- Short put
- Short stock
- Long cash

For a filled short call, the parity hedge is:

- Long put
- Long stock
- Short cash

---

## Mistake 3: Ignoring Quantity

Best bid and ask may support only one contract.

Use full order-book depth for the intended size.

---

## Mistake 4: Ignoring Contract Multiplier

One option contract may represent many shares.

The stock hedge must use:

$$
\text{contracts} \times \text{multiplier}
$$

---

## Mistake 5: Treating the Cash Leg as Free

The strike must be financed.

Funding rates, lending rates, collateral rules, and margin all affect profitability.

---

## Mistake 6: Slow Cancellation

A stale passive quote is often selected exactly when it is bad for the market maker.

This is adverse selection.

---

## Mistake 7: Assuming the Hedge Will Fill

Expected profit is not locked until the hedge executes.

---

## Mistake 8: Ignoring American Exercise

American-option early exercise can invalidate simple European parity assumptions.

---

# 27. Minimal Production Formula

For a passive call bid of size $q$:

$$
\boxed{
B_C(q)
=
\bar{P}_{bid}(q)
+
\bar{S}_{bid}(qm)
-
PV(K)
-
Fees(q)
-
Slippage(q)
-
Funding(q)
-
Borrow(q)
-
Risk(q)
-
ProfitTarget(q)
}
$$

For a passive call ask of size $q$:

$$
\boxed{
A_C(q)
=
\bar{P}_{ask}(q)
+
\bar{S}_{ask}(qm)
-
PV(K)
+
Fees(q)
+
Slippage(q)
+
Funding(q)
+
Borrow(q)
+
Risk(q)
+
ProfitTarget(q)
}
$$

These formulas are the practical foundation of parity-based market making.

---

# 28. Complete Call-Bid Workflow

```text
1. Read call, put, and stock order books.
2. Validate timestamps and market status.
3. Match same strike and expiry.
4. Calculate PV(strike).
5. Calculate the executable value of selling the put.
6. Calculate the executable value of selling the stock.
7. Subtract every cost.
8. Subtract required profit.
9. Subtract risk buffer.
10. Round the result down to the valid tick.
11. Limit size by available put and stock depth.
12. Place passive call bid.
13. Recalculate after every relevant market update.
14. Cancel or replace when the valid bid changes.
15. If the call fills:
    a. Sell the put.
    b. Sell the stock.
    c. Record the cash leg.
16. Handle partial fills.
17. Verify net position.
18. Calculate realized profit.
19. Stop quoting if risk, margin, feed, or reconciliation limits fail.
```

---

# 29. Final Intuition

Put–call parity gives a model-free relative value for an option.

For a call:

$$
C=P+S-PV(K)
$$

A parity market maker does not need to begin by predicting volatility.

Instead, the system asks:

> At what call price can I trade passively and then execute the put, stock, and financing legs while still earning a positive net profit?

For a call bid:

$$
\text{Bid}
=
\text{value received from hedge}
-
\text{costs}
-
\text{risk buffer}
-
\text{profit target}
$$

The quote must be canceled whenever the hedge value changes enough to remove the expected edge.

When the call fills, complete the opposite synthetic position:

$$
+\text{Call}
-\text{Put}
-\text{Stock}
+PV(K)
=0
$$

That is the core parity market-making loop:

```text
VALUE
→ QUOTE
→ CANCEL/REPRICE
→ FILL
→ HEDGE OTHER LEGS
→ VERIFY
→ REPEAT
```
