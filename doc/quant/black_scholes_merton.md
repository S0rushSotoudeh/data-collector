# Black–Scholes–Merton (BSM) Model — Summary Guide

## 1. What the BSM Model Does

The Black–Scholes–Merton model estimates the theoretical price of a European option.

It answers:

> Given the stock price, strike, time to expiry, interest rate, and volatility, what should the option be worth?

The standard model prices:

- European call options
- European put options
- Options on non-dividend-paying stocks

A dividend-adjusted version can also price options on assets with a continuous dividend yield.

---

## 2. Required Inputs

| Symbol | Meaning |
|---|---|
| \(S\) | Current underlying price |
| \(K\) | Strike price |
| \(T\) | Time to expiration in years |
| \(r\) | Continuously compounded risk-free interest rate |
| \(\sigma\) | Annualized volatility |
| \(q\) | Continuous dividend yield |
| \(N(x)\) | Standard normal cumulative distribution function |

Example:

- 30 days to expiration:

$$
T = \frac{30}{365}
$$

- 25% annual volatility:

$$
\sigma = 0.25
$$

---

## 3. BSM Formulas

### Call Option

$$
C = S e^{-qT}N(d_1) - K e^{-rT}N(d_2)
$$

### Put Option

$$
P = K e^{-rT}N(-d_2) - S e^{-qT}N(-d_1)
$$

where:

$$
d_1 =
\frac{
\ln(S/K) + \left(r-q+\frac{\sigma^2}{2}\right)T
}{
\sigma\sqrt{T}
}
$$

$$
d_2 = d_1 - \sigma\sqrt{T}
$$

For a non-dividend-paying stock:

$$
q = 0
$$

---

## 4. Intuition Behind the Formula

The call formula has two main parts:

$$
C = S e^{-qT}N(d_1) - K e^{-rT}N(d_2)
$$

### First Part

$$
S e^{-qT}N(d_1)
$$

This represents the option's exposure to the underlying asset.

### Second Part

$$
K e^{-rT}N(d_2)
$$

This represents the present value of the strike payment, weighted by the risk-neutral probability of exercise.

The call value is approximately:

> expected value of receiving the stock minus expected present value of paying the strike.

---

## 5. Main Assumptions

The standard BSM model assumes:

1. The option is European and can only be exercised at expiration.
2. The underlying price follows a lognormal process.
3. Volatility is constant.
4. The risk-free rate is constant.
5. Markets are frictionless.
6. There are no transaction costs or taxes.
7. Trading is continuous.
8. The underlying can be bought or shorted freely.
9. There are no arbitrage opportunities.
10. Dividend yield is known and constant if dividends are included.

Real markets violate several of these assumptions.

---

## 6. What Increases an Option's Value?

### Call Option

A call usually becomes more valuable when:

- \(S\) increases
- \(\sigma\) increases
- \(T\) increases
- \(r\) increases
- \(K\) decreases
- \(q\) decreases

### Put Option

A put usually becomes more valuable when:

- \(S\) decreases
- \(\sigma\) increases
- \(T\) increases
- \(K\) increases
- \(q\) increases
- \(r\) decreases

---

## 7. Intrinsic and Time Value

### Call Intrinsic Value

$$
\max(S-K,0)
$$

### Put Intrinsic Value

$$
\max(K-S,0)
$$

### Time Value

$$
\text{Time Value}
=
\text{Option Price}
-
\text{Intrinsic Value}
$$

BSM estimates the total option value, including time value.

---

## 8. Moneyness

### Call Option

- In the money: \(S > K\)
- At the money: \(S \approx K\)
- Out of the money: \(S < K\)

### Put Option

- In the money: \(S < K\)
- At the money: \(S \approx K\)
- Out of the money: \(S > K\)

---

## 9. The Greeks

The Greeks measure how the BSM option price changes when an input changes.

### Delta

Delta measures sensitivity to the underlying price.

$$
\Delta_{\text{call}} = e^{-qT}N(d_1)
$$

$$
\Delta_{\text{put}} = e^{-qT}\left(N(d_1)-1\right)
$$

Interpretation:

- A call delta of \(0.60\) means the option price increases by approximately \(0.60\) when the stock rises by \(1\).
- Delta is also the hedge ratio in the BSM framework.

---

### Gamma

Gamma measures how fast delta changes.

$$
\Gamma =
\frac{
e^{-qT}\phi(d_1)
}{
S\sigma\sqrt{T}
}
$$

where \(\phi(x)\) is the standard normal probability density function.

Gamma is usually highest for near-expiry, at-the-money options.

---

### Vega

Vega measures sensitivity to volatility.

$$
\text{Vega}
=
S e^{-qT}\phi(d_1)\sqrt{T}
$$

Higher volatility generally increases both call and put values.

A common market convention reports vega for a 1 percentage-point volatility change, so the formula result may be divided by 100.

---

### Theta

Theta measures sensitivity to the passage of time.

Using the usual convention \(\Theta = \partial V / \partial t\), where calendar time \(t\) moves forward and \(T\) is time remaining to expiration:

$$
\Theta_{\text{call}} = -\frac{S e^{-qT}\phi(d_1)\sigma}{2\sqrt{T}} - rK e^{-rT}N(d_2) + qS e^{-qT}N(d_1)
$$

$$
\Theta_{\text{put}} = -\frac{S e^{-qT}\phi(d_1)\sigma}{2\sqrt{T}} + rK e^{-rT}N(-d_2) - qS e^{-qT}N(-d_1)
$$

For most long options, Theta is negative:

$$
\Theta < 0
$$

This means options usually lose value as expiration approaches, assuming other inputs stay unchanged.

Theta decay is often strongest near expiration for at-the-money options.

---

### Rho

Rho measures sensitivity to the risk-free rate.

Call rho:

$$
\rho_{\text{call}}
=
KTe^{-rT}N(d_2)
$$

Put rho:

$$
\rho_{\text{put}}
=
-KTe^{-rT}N(-d_2)
$$

Calls usually benefit from higher rates, while puts usually lose value.

---

## 10. Implied Volatility

BSM can be used in two directions.

### Pricing Direction

Given volatility:

$$
\sigma
$$

calculate the option price.

### Implied Volatility Direction

Given the market option price, solve for:

$$
\sigma_{\text{implied}}
$$

Implied volatility is the volatility value that makes the BSM price equal to the market price.

There is no simple closed-form formula for implied volatility, so numerical methods are used, such as:

- Newton–Raphson
- Bisection
- Brent's method

---

## 11. Put–Call Parity

For European options with the same strike and expiry:

$$
C - P
=
S e^{-qT}
-
K e^{-rT}
$$

Equivalent form:

$$
C + K e^{-rT}
=
P + S e^{-qT}
$$

Put–call parity is important for:

- arbitrage detection
- synthetic positions
- consistency checks
- option pricing validation

---

## 12. Risk-Neutral Pricing

BSM does not require the real expected return of the stock.

Instead, it assumes that under the risk-neutral measure, the underlying grows at:

$$
r-q
$$

This does not mean investors are actually risk-neutral.

It is a mathematical pricing framework where discounted tradable asset prices behave consistently with no-arbitrage.

---

## 13. Dynamic Hedging Idea

The BSM model is based on constructing a continuously rebalanced hedged portfolio.

For a call option:

$$
\Pi = C - \Delta S
$$

The stock exposure is offset by choosing:

$$
\Delta = \frac{\partial C}{\partial S}
$$

The hedged portfolio is locally insensitive to small stock-price movements.

Because the portfolio is treated as locally riskless, it should earn the risk-free rate.

This no-arbitrage argument leads to the Black–Scholes differential equation.

---

## 14. Black–Scholes PDE

The option value \(V(S,t)\) satisfies:

$$
\frac{\partial V}{\partial t}
+
\frac{1}{2}\sigma^2S^2
\frac{\partial^2 V}{\partial S^2}
+
(r-q)S
\frac{\partial V}{\partial S}
-
rV
=
0
$$

The closed-form BSM formulas are solutions to this equation under European call or put terminal payoffs.

At expiration:

### Call

$$
V(S,T)=\max(S-K,0)
$$

### Put

$$
V(S,T)=\max(K-S,0)
$$

---

## 15. Simple Numerical Example

Assume:

$$
S=100
$$

$$
K=100
$$

$$
T=1
$$

$$
r=0.05
$$

$$
q=0
$$

$$
\sigma=0.20
$$

Then:

$$
d_1
=
\frac{
\ln(100/100)
+
\left(0.05+\frac{0.20^2}{2}\right)
}{
0.20
}
=
0.35
$$

$$
d_2 = 0.35 - 0.20 = 0.15
$$

Using standard normal values:

$$
N(d_1)\approx 0.6368
$$

$$
N(d_2)\approx 0.5596
$$

Call value:

$$
C
=
100(0.6368)
-
100e^{-0.05}(0.5596)
$$

$$
C \approx 10.45
$$

The put value from put–call parity is approximately:

$$
P \approx 5.57
$$

---

## 16. Practical Limitations

BSM is useful, but real option markets differ from the model.

### Volatility Is Not Constant

Different strikes and expiries trade at different implied volatilities.

This creates:

- volatility smiles
- volatility skews
- volatility surfaces

### Returns May Have Jumps

Real prices can move suddenly, while basic BSM assumes continuous paths.

### Hedging Is Discrete

Traders cannot rebalance continuously.

This creates:

- slippage
- gap risk
- gamma risk
- transaction costs

### Rates and Dividends Change

Interest rates, borrow costs, and dividends may be uncertain.

### American Exercise

Standard BSM does not directly handle early exercise.

American options often require:

- binomial trees
- finite-difference methods
- approximation formulas
- Monte Carlo methods with exercise logic

---

## 17. When BSM Is Most Useful

BSM is useful for:

- understanding option pricing
- calculating theoretical values
- estimating implied volatility
- calculating Greeks
- comparing options
- detecting relative mispricing
- constructing delta hedges
- checking put–call parity
- building more advanced pricing models

It should usually be treated as a baseline model, not a perfect description of the market.

---

## 18. Minimal Implementation Logic

To price an option:

1. Convert time to years.
2. Convert volatility and interest rates to decimals.
3. Calculate \(d_1\).
4. Calculate \(d_2\).
5. Evaluate \(N(d_1)\) and \(N(d_2)\).
6. Use the call or put formula.
7. Compare the theoretical value with the market price.
8. Check implied volatility and Greeks before trading.

---

## 19. Key Takeaways

- BSM gives a no-arbitrage theoretical value for European options.
- The most important uncertain input is volatility.
- Delta is the hedge ratio.
- Gamma measures delta instability.
- Vega measures volatility exposure.
- Theta measures time decay.
- Implied volatility is often more useful than the raw model price.
- Real markets require adjustments for volatility smiles, jumps, costs, liquidity, dividends, borrow constraints, and discrete hedging.
- BSM is the foundation of modern option pricing, even when more advanced models are used.
