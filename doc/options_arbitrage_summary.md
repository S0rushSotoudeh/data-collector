# Stakeholder Summary: Options Arbitrage with a Locked Payoff

## What we are proposing

We want to build an automated strategy that finds temporary pricing differences
between related shares and options.

The strategy is not intended to predict whether a share price will go up or
down. Instead, it combines several instruments so that, once every trade is
completed, the amount received or paid at expiry is known in advance.

We will trade only when the expected return, after all costs, is higher than an
investable market benchmark with a similar maturity, such as the relevant
Iranian government-bond (`اخزا`) yield.

## Options explained simply

An **option** is a contract linked to a share:

- A **call option** gives its buyer the right to buy the share at an agreed
  price.
- A **put option** gives its buyer the right to sell the share at an agreed
  price.
- The agreed price is called the **strike price**.
- The contract's final date is called its **expiry**.

Options with the same share and expiry are mathematically connected. If one is
temporarily too cheap or too expensive compared with the others, we may be able
to buy the cheaper combination and sell the more expensive one.

## The three opportunities

### 1. Long box: similar to lending money

A long box combines four options at two different strike prices. It requires a
cash payment today and produces a fixed receipt at expiry, regardless of the
final share price.

For example, a box using strikes of 100 and 110 pays exactly 10 at expiry. If we
can create it for an all-in cost of 9.40, the gross difference is 0.60. We trade
only if the return remaining after fees, funding, slippage, and risk buffers is
higher than the comparable market return.

### 2. Short box: similar to borrowing money

A short box is the reverse. It provides cash today and creates a fixed payment
at expiry.

It is useful when the implied cost of this funding is lower than the funding
available elsewhere, or when the cash received can earn a higher net return.
The calculation must include the collateral required by the broker.

### 3. Put-call parity: combining a share and options

Put-call parity means that two different portfolios can produce the same result
at expiry.

One practical combination is:

- buy or hold the share;
- buy a put option for protection; and
- sell a call option.

When the contracts match correctly, the gain or loss on one component offsets
the others and creates a known expiry value. We act when this package offers a
better net return than the market benchmark.

## How a trade is executed

Paying the market spread on every component can remove the profit. Our process
therefore uses one passive order first and completes the other components only
after that order fills.

```text
Find an opportunity
        ↓
Place one maker order at our required price
        ↓
Wait for a confirmed full or partial fill
        ↓
Immediately take the remaining legs for the filled quantity
        ↓
Check that all positions and quantities match
        ↓
Register the linked strategies in EasyTrader
        ↓
Release excess collateral and monitor through expiry
```

A **maker order** waits in the order book and seeks a better price. A **taker
order** executes against an available price. The system calculates the maker
price from the prices at which all remaining components can actually be traded.

If only part of the maker order fills, we complete the other legs only for that
confirmed quantity. If a required leg cannot be completed, the system must
stop new orders and urgently complete, hedge, or close the exposure.

## Why EasyTrader matters

Some parts of a box involve selling options. If the broker sees those positions
individually, it may treat them as unprotected and reserve substantial
collateral.

After every leg is filled and verified, we register the positions in
EasyTrader as recognized spreads and covered strategies. This shows the broker
which purchased option or share protects each sold option. The broker may then
release collateral that is no longer required.

This improves capital efficiency, but collateral release is never assumed in
advance. We recognize it only after EasyTrader confirms the strategy and the
broker confirms the new collateral balance.

## How we determine whether a trade is worthwhile

Before submitting an order, the system includes:

- actual buy and sell prices for the required quantity;
- all trading and settlement fees;
- expected slippage;
- funding and collateral costs;
- a safety allowance for execution risk; and
- the minimum profit required by stakeholders.

The trade is permitted only when:

```text
Expected net annualized return
    > comparable investable market return
    + approved safety margin
```

After execution, performance is recalculated using actual fills and actual
costs. Indicative profit shown before a fill is never reported as realized
profit.

## Is the profit risk-free?

The final payoff can be locked only after every component has been executed
correctly. Before that point, market prices can move and one of the remaining
orders can fail.

Other risks include:

- insufficient market liquidity;
- partial fills or rejected orders;
- broker or EasyTrader errors;
- unexpected margin requirements;
- exercise, assignment, and settlement problems;
- stale market data or software failures; and
- fees or funding costs being higher than expected.

For this reason, the accurate description is **locked-payoff arbitrage**, not a
guarantee of risk-free profit.

## Proposed next step

We recommend a limited-capital pilot:

1. Validate the calculations using historical and live market data.
2. Run in observation mode without placing real orders.
3. Test partial fills, rejected orders, emergency hedging, and collateral
   registration.
4. Start with small real positions and strict limits.
5. Increase capital only after realized returns, collateral usage, and incident
   rates meet the approved targets.

The goal is to capture pricing inconsistencies systematically, lock the payoff
quickly after the first fill, and use EasyTrader to improve collateral
efficiency without increasing uncontrolled exposure.

For calculations, detailed controls, and the exact EasyTrader mappings, see the
[full stakeholder proposal](stakeholder_options_arbitrage_strategy.md).
