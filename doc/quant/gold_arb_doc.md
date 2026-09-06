# Intraday Relative-Value Trading for Iranian Gold ETFs

> **Core position:** The defensible starting point is intraday relative-value trading with uncertain exposures—not a presumption of risk-free arbitrage. Build a small family of transparent models, estimate how much of each apparent discrepancy actually closes, and trade only when the expected executable profit survives uncertainty, costs, and incomplete execution.

With no historical observations, live quotes, or account permissions supplied here, the present trading decision is **stand aside**. What follows is a research and execution specification that can produce a reproducible trade/no-trade decision once calibrated. Numerical settings below are proposed research defaults, not measured properties of Iranian gold ETFs.

## 1. Separate underlying value, normal market valuation, and executable price

For ETF $i$, define:

$$
V_{i,t}=\text{latent economic value of assets less liabilities, per unit}
$$

$$
F_{i,t}=\text{estimated normal secondary-market price}
$$

$$
P^{\mathrm{buy}}_{i,t}(q),\quad P^{\mathrm{sell}}_{i,t}(q)
=\text{executable average prices for quantity }q.
$$

A useful decomposition is:

$$
\log M_{i,t}
=
v_{i,t}+\bar\pi_{i,t}+u_{i,t}+\epsilon_{i,t},
\qquad v_{i,t}=\log V_{i,t},
$$

where:

- $M_{i,t}$: a valid order-book midpoint.
- $\bar\pi_{i,t}$: persistent or normally expected premium/discount.
- $u_{i,t}$: potentially temporary dislocation.
- $\epsilon_{i,t}$: microstructure and observation noise.

Then:

$$
F_{i,t}=\exp(\widehat v_{i,t}+\widehat{\bar\pi}_{i,t}).
$$

This distinction prevents two expensive mistakes:

1. Calling every premium to NAV a trading opportunity.
2. Treating the ETF sector’s consensus price as independent evidence of underlying value.

**Without holdings, exposures and underlying value are only partially identifiable.** A fund with cash and leveraged derivatives can resemble a fully invested physical portfolio over a short sample. A common premium across all ETFs can resemble a change in local gold value. Published NAV helps constrain the problem, but does not eliminate it.

Maintain separate outputs for estimated underlying value, normal market value, and expected executable liquidation value.

## 2. Treat the four strategy types as separate hypotheses

| Strategy | Source of expected profit | Necessary evidence | Main obstacle here |
|---|---|---|---|
| Low-latency arbitrage | Acting before a stale executable quote updates | Reliable event timing; signal survives actual order latency; feasible hedge or conversion | An estimated ETF basket is not exact replication |
| Intraday statistical arbitrage | Relative residuals converge over seconds or minutes | Stable out-of-sample convergence after costs | Exposure changes and persistent premiums |
| Market making with a correlated hedge | Compensation for supplying liquidity, after hedging and adverse selection | Positive fill-conditioned returns and realistic queue simulation | You tend to fill when your quote becomes unattractive |
| Premium/discount trading | Market price moves toward estimated underlying value | Evidence that the particular premium closes, with an identifiable mechanism or stable history | NAV can catch up to price instead of price reverting |

A quote reacting slowly to a predictive feed may support **latency-sensitive statistical trading**. It becomes genuine arbitrage only if the economic relationship and completion mechanism justify that description.

Creation/redemption, borrowing, or direct certificate conversion must never be assumed available merely because the product is called an ETF.

## 3. Build a dated Iranian instrument-and-rules register before interpreting prices

I checked official sources on **5 September 2026**. Several exchange, disclosure, and regulator pages were inaccessible, so I could not establish current instrument-level fees, trading hours, price limits, or short-selling access.

Two official findings are directly relevant:

- The CBI describes its weighted FX rate as a calculated indicator based on transactions over the preceding month, and explicitly distinguishes it from an operational trading rate. Therefore, “official USD/IRR” does not automatically mean an executable or timely hedge input. [CBI exchange-rate methodology](https://www.cbi.ir/exrates/rates_fa.aspx)
- An IME news report describes access for managed portfolios as dependent on account documentation and trading-system connectivity. Product existence and operational access are separate facts. [IME report on PRX access](https://www.imereport.ir/news/99004/کدهای-PRX-آماده-بهره-برداری-مسیر-ورود-حرفه-ای-سبدگردان-ها-به)

For this framework, the following is the **Iran-specific verification register**. Every entry needs an effective date, source document, and account/instrument scope.

| Fact to verify | Required detail | Authoritative evidence to obtain |
|---|---|---|
| Instrument identity | Exchange identifier, symbol changes, fund type, listings and closures | Exchange instrument master; fund documents |
| Currency convention | Rial/toman, displayed versus order-entry units, any historical denomination changes | Feed specification; exchange specification |
| Bullion certificate unit | Mass per certificate, trading fineness, purity adjustment, warehouse and delivery terms | Current and historical IME contract specifications |
| Coin certificate unit | Fraction or whole coin per quoted unit, coin specification, series and warehouse | Instrument-specific IME notices |
| Fund mandate | Permitted certificates, cash, derivatives, other assets, exposure/leverage limits | Prospectus and amendments; disclosures |
| NAV definition | Indicative, subscription, redemption, or accounting NAV; valuation methods; liabilities and unit count | Fund administrator’s methodology |
| NAV timing | Economic valuation time, publication time, update schedule, rounding and revisions | Administrator/feed documentation and observed logs |
| Common fees | Buy/sell commission, exchange/clearing charges, minimums and caps | Effective official tariff |
| Other costs | Taxes, custody/storage, borrowing, funding, derivative charges | Official schedules; account agreements |
| Trading calendar | Sessions, auctions, holidays, emergency closures, overlapping hedge hours | Exchange notices and session messages |
| Price and quantity rules | Ticks, lots, minimum value, maximum order size, daily bounds and reference-price calculation | Exchange specifications |
| Matching and orders | Priority rules; IOC/FOK availability; validity; amend/cancel behavior; auction eligibility | Exchange/OMS documentation |
| Selling and hedging access | Owned inventory, borrowing or authorized short mechanism, eligibility and limits | Applicable rules plus broker/account confirmation |
| Settlement and funding | Settlement cycles, intraday reuse of proceeds, separate wallets, collateral, transfer delays | Clearing and broker documentation |
| Creation/redemption | Eligible participants, cash/in-kind terms, minimum size, timing, suspension and costs | Fund prospectus and operational procedures |
| Market-maker arrangements | Obligations, exceptions, privileges, and applicability to your account | Exchange/fund agreement |
| Automation and data | Permitted access, throttles, timestamps, sequence numbers, depth completeness, trade reporting | Exchange, broker, OMS and vendor specifications |
| FX market identity | Cash/remittance, venue, eligibility, settlement, executable size, official/indicative methodology | Provider specification and applicable CBI rules |
| Cross-border linkage | Actual ability and cost to convert, transfer, import/export or hedge offshore | Applicable rules and operational evidence |

**Use the same ETF fee schedule and general trading rules in the research configuration, as requested, unless dated official evidence establishes an exception.** Equal fees do not imply equal spreads, market impact, borrowing access, or hedge costs. Do not assume certificate or derivative fees equal ETF fees.

## 4. Normalize contract economics before estimating statistical relationships

Let:

- $Q_{k,t}$: quoted price of certificate $k$.
- $c_k$: conversion from displayed currency to IRR.
- $m_k$: gross grams represented by one quoted unit.
- $a_k$: applicable fineness.
- $g_k=m_ka_k$: fine-gold-equivalent grams per quoted unit.

Then:

$$
X_{k,t}^{\mathrm{fine}}
=
\frac{c_kQ_{k,t}}{g_k}
$$

is IRR per fine gram.

Use the **contractual trading convention**, not a guessed physical convention. If purity adjustment is already embedded in the quotation, do not apply it twice.

For a coin certificate representing $n_k$ coins:

$$
g_k=n_km_{\mathrm{coin}}a_{\mathrm{coin}}.
$$

Coin prices retain a coin-specific premium after normalization. Equal fine-gold content does not make coin and bullion certificates economically interchangeable.

A recent official IME report separately reports bullion certificates and coin certificates, including 330 coin certificates corresponding to 330 coins in that report. That is a useful consistency check, but it is not a substitute for each symbol’s historical contract specification. [IME gold-market report](https://www.imereport.ir/news/99027/ثبت-ارزش-۲۲-همتی-در-صندوق-های-طلا)

For global gold:

$$
G_t^{(r)}
=
\frac{Z_tD_t^{(r)}}{31.1034768},
$$

where $Z_t$ is USD per troy ounce and $D_t^{(r)}$ is IRR per USD for the specifically identified FX feed $r$.

For statistical work, use dimensionless log returns:

$$
r_{k,t}=\log X_{k,t}-\log X_{k,t-\Delta}.
$$

For order sizing and P&L, retain native prices, quantities, and contract multipliers.

**Do not assign an ETF a fixed grams-per-unit conversion.** Its effective gold exposure can change with cash, derivatives, liabilities, and portfolio decisions.

Across multiple bullion warehouses or coin series, start with separate series. Combine them only after testing warehouse/series basis stability. Construct any composite using lagged liquidity weights and archived constituents.

## 5. Make the information set reproducible

Each observation should contain at least:

$$
(\text{instrument},t^{event},t^{publish},t^{receive},
\text{sequence},\text{value},\text{status},\text{version}).
$$

At decision time $t$:

$$
\mathcal I_t
=
\{\text{observations received and processed by }t\}.
$$

An observation with an earlier exchange timestamp but a later receive time was unavailable to the strategy until it arrived.

Use two complementary clocks:

- **Economic/event time:** to investigate genuine lead-lag relationships.
- **Receive time:** to test what your system could actually exploit.

Operational rules:

- Use backward-looking as-of joins; never nearest-neighbor joins that select future observations.
- Never linearly interpolate between a past and future tick for a historical decision.
- Track quote age and feed heartbeat separately. An unchanged price is not necessarily a broken feed.
- Record crossed, locked, one-sided, halted, auction, and limit-bound books.
- Treat closed markets as unavailable observations, not fresh zero returns.
- Preserve original NAV releases and later revisions separately.
- Use historically correct calendars and timestamp conversions.
- If precise receipt timestamps were not recorded, introduce conservative latency assumptions and report the resulting uncertainty. Do not claim a low-latency edge from coarse timestamps.

An observation-error model can depend on age and quality:

$$
R_{k,t}
=
R_{k,0}
+\omega_k\,\mathrm{Age}_{k,t}
+\chi_k\,\mathrm{Spread}_{k,t}^{2}
+\psi_k\,\mathrm{QualityPenalty}_{k,t}.
$$

Estimate these relationships; linear age growth is only a starting approximation. Include a nonzero uncertainty floor, particularly during halts and price-limit queues.

## 6. Begin with simple competing baselines, giving every feed a fair test

The first useful baseline is **a noisy NAV anchor propagated by a fixed, recently estimated return exposure**.

Let $x_t$ contain one candidate factor initially:

- Bullion return index.
- Coin return index.
- Global gold converted through the specified FX feed.
- A leave-one-out ETF-sector factor.

Between NAV observations:

$$
\widehat v_{i,t}^{-}
=
\widehat v_{i,s}^{+}
+\widehat\beta_i^\top(x_t-x_s)
-\widehat c_i(t-s).
$$

Here $\widehat c_i$ represents expected net carry/expense drift, with its uncertainty included. The anchor at $s$ is an estimate, not a declaration that NAV is exact.

Compare this against two null benchmarks:

$$
\widehat V_{i,t}=N_{i,\mathrm{last}},
\qquad
\widehat M_{i,t+H}=M_{i,t}.
$$

The first tests whether propagation improves on stale NAV. The second tests whether a forecasting model beats “the current price persists.”

For the initial exposure estimate, fit returns at intervals long enough to reduce asynchronous noise. For example, compare 1-, 5-, and 15-minute observations before considering subsecond estimation.

**Assumptions:** exposures are approximately stable over the calibration window; the selected factor carries relevant information; NAV provides a usable but noisy level constraint.

**Data:** archived certificate/global/FX/ETF prices and NAV vintages, with timing metadata.

**Recalibration:** coefficients daily using a candidate 20–60-session rolling window; state updates whenever valid information arrives.

**Advantages:** transparent, easy to diagnose, inexpensive to maintain.

**Weaknesses:** misses changing coin/bullion composition and may confuse premium changes with portfolio exposure.

**Look-ahead protection:** select the factor/window in prior validation data; only use NAVs already published; freeze coefficients during the next evaluation period.

No candidate is declared the primary anchor in advance.

## 7. Infer effective exposures with rolling and robust regression

For market-price returns:

$$
r^M_{i,t}
=
\alpha_i+\beta_i^\top f_t+\eta_{i,t}.
$$

For NAV observations valued at $\tau_{n-1}$ and $\tau_n$:

$$
\Delta\log N_{i,n}
=
\alpha_i\Delta\tau_n
+
\beta_i^\top
\left[x_{\tau_n}-x_{\tau_{n-1}}\right]
+\nu_{i,n}.
$$

The latter requires credible valuation timestamps. NAV observation errors can be serially correlated, so overlapping release intervals are not independent samples.

Market-return coefficients estimate **market behavior**. NAV-return coefficients estimate **exposure under the administrator’s valuation process**. Neither alone proves actual holdings.

A regularized rolling fit is:

$$
\min_{\alpha_i,\beta_i}
\sum_{t\in W}w_t
\left(r_{i,t}-\alpha_i-\beta_i^\top f_t\right)^2
+\lambda\|\beta_i-\beta_{0,i}\|_2^2.
$$

A robust alternative replaces squared error with Huber loss:

$$
\min_{\alpha_i,\beta_i}
\sum_{t\in W}w_t
\rho_\delta
\left(
\frac{r_{i,t}-\alpha_i-\beta_i^\top f_t}{s_i}
\right)
+\lambda\|\beta_i-\beta_{0,i}\|_2^2,
$$

$$
\rho_\delta(u)=
\begin{cases}
u^2/2,&|u|\leq\delta,\\
\delta|u|-\delta^2/2,&|u|>\delta.
\end{cases}
$$

Robust estimation reduces the influence of isolated errors. Persistent large residuals should trigger a structural-break investigation rather than being repeatedly suppressed.

**Should exposures sum to one?**

For genuine, exhaustive balance-sheet weights:

$$
w_B+w_C+w_{\mathrm{cash}}+w_{\mathrm{other}}=1
$$

may be appropriate after correctly accounting for liabilities and derivative market values.

For regression betas:

$$
\boxed{\sum_k\beta_{i,k}=1\text{ is generally unjustified}.}
$$

Reasons include overlapping factors, derivatives, leverage, basis exposure, and omitted assets. Derivative market-value weight is also different from delta exposure.

A constrained physical-mixture model can be a challenger when the mandate supports it:

$$
w_B,w_C,w_{\mathrm{cash}}\geq0,
\qquad
w_B+w_C+w_{\mathrm{cash}}=1.
$$

Compare it against an unconstrained, regularized exposure model. Do not interpret a coefficient of $0.7$ on bullion as proven 70% bullion holdings.

**Avoid double-counting FX.** Local certificate prices already embed currency effects. One possible factor basis is:

$$
f_t=
\begin{bmatrix}
\Delta\log G_t\\
\Delta\log(B_t/G_t)\\
\Delta\log(C_t/B_t)
\end{bmatrix}.
$$

This separates global-converted gold, local bullion basis, and coin-versus-bullion basis. It is a parameterization, not a claim that $G$ leads.

Alternatively, model global-gold and FX returns separately. Since:

$$
\Delta\log G=\Delta\log Z+\Delta\log D,
$$

including all three unrestricted creates exact redundancy.

**Assumptions:** approximately linear local sensitivities and enough independent factor variation.

**Data:** aligned returns, quality weights, and preferably NAV observations as a second target.

**Recalibration:** daily; compare 20-, 40-, and 60-session windows in validation.

**Advantages:** interpretable exposures, straightforward hedge design, robust version handles contaminated observations.

**Weaknesses:** collinearity can make individual coefficients unstable even when predictions are good; nonlinear derivatives remain imperfectly represented.

**Look-ahead protection:** estimate scaling, penalties, robust-loss settings and priors only from prior data; use time-blocked uncertainty estimates.

## 8. Use the ETF cross-section as an information source with explicit circularity controls

Start with a robust leave-one-out sector return:

$$
f_{-i,t}
=
\operatorname{weighted\,median}_{j\ne i}(r^M_{j,t}).
$$

Use lagged liquidity weights, exclude invalid books, and cap individual influence.

Then compare PCA:

$$
\Sigma_W u_k=\lambda_k u_k,
\qquad
f_{k,t}=u_k^\top \widetilde r_t,
$$

where $\widetilde r_t$ uses training-window means and scales.

Reconstruct ETF returns:

$$
\widehat r_{i,t}
=
\widehat\alpha_i+\widehat\ell_i^\top f_{-i,t}.
$$

For a pair $i,j$, preferably exclude **both** from the peer factor used to judge their discrepancy.

PCA identifies common price variation. It does not establish economic fair value. If all ETFs become expensive together, a peer-only model may see no problem.

**Assumptions:** a low-dimensional common component exists and enough independently updating ETFs remain available.

**Data:** broad historical ETF books, point-in-time universe membership and liquidity.

**Recalibration:** factor scores intraday; weights/loadings daily; choose factor count in prior validation, starting with one.

**Advantages:** can capture local information that certificate or FX feeds miss.

**Weaknesses:** circularity, common premium contamination, changing loadings, and dominance by liquid funds.

**Look-ahead protection:** exclude target instruments; freeze loadings and standardization; use only received peer prices; never use current constituents throughout history.

## 9. Let delayed NAV update the historical state and propagate that correction forward

Write a NAV release received at $t_n$, valued at $\tau_n\leq t_n$, as:

$$
y_{i,n}=\log N_{i,n}
=
v_{i,\tau_n}+b_i+\epsilon_{i,n},
\qquad
\operatorname{Var}(\epsilon_{i,n})=R_{i,n}.
$$

Here $b_i$ represents possible valuation bias. Without independent evidence, $b_i$ and the absolute value level may not be separately identifiable. Use a conservative prior or scenario range rather than freely fitting both.

For a scalar state with known observation time:

$$
K=
\frac{P^-_{\tau_n}}{P^-_{\tau_n}+R_{i,n}},
$$

$$
\widehat v^+_{\tau_n}
=
\widehat v^-_{\tau_n}
+
K\left(y_{i,n}-b_i-\widehat v^-_{\tau_n}\right).
$$

The correction affects the current estimate through propagation.

More generally, the direct current-state correction is:

$$
\widehat v_t^+
=
\widehat v_t^-
+
\frac{\operatorname{Cov}(v_t,v_{\tau_n}\mid\mathcal I_{t^-})}
{\operatorname{Var}(v_{\tau_n}\mid\mathcal I_{t^-})+R_{i,n}}
\left(y_{i,n}-b_i-\widehat v^-_{\tau_n}\right).
$$

Thus an old NAV is not simply pasted onto the present.

A fuller Kalman specification is:

$$
s_t=A_ts_{t-1}+B_tf_t+\eta_t,
\qquad
\eta_t\sim(0,Q_t),
$$

$$
\log M_{i,t}=v_{i,t}+\pi_{i,t}+\epsilon^M_{i,t},
$$

$$
\pi_{i,t}
=
\bar\pi_i+\phi_i(\pi_{i,t-1}-\bar\pi_i)+\xi_{i,t}.
$$

The state can contain value and premium. Add drifting exposures only if fixed exposures fail:

$$
\beta_{i,t}=\beta_{i,t-1}+\zeta_{i,t}.
$$

Do not allow value, premium, NAV bias, and all exposures to drift freely at once: the model may explain everything while identifying little.

Increase NAV noise for uncertain valuation times, rounding, unexplained revisions, or stale constituent marks. Model overlapping NAV errors as correlated, or avoid counting repeated stale valuations as independent evidence.

**Assumptions:** a sufficiently identified state model; approximately useful process/observation covariance estimates.

**Data:** timestamped NAV vintages, price feeds, and stored state history.

**Recalibration:** states on events; observation/process parameters weekly initially; exposures daily or slowly varying.

**Advantages:** coherent asynchronous updates and time-varying uncertainty.

**Weaknesses:** false precision from misspecified noise; confounding between value and premium.

**Look-ahead protection:** process a delayed observation only when received. An internal historical-state correction is allowed then; previously recorded decisions and estimates remain immutable. Never use a full-sample smoother for historical signals.

## 10. Require evidence of convergence through cointegration and error correction

Return correlation is insufficient.

For a pair:

$$
s_t=\log M_{i,t}-a-h\log M_{j,t}.
$$

For an underlying basket:

$$
s_t=\log M_{i,t}-a-\theta^\top x_t.
$$

A cointegration claim requires compatible integration properties and a stable stationary residual—not merely a high level-regression $R^2$. This is the distinction underlying the cointegration/error-correction framework. [Engle and Granger, 1987](https://doi.org/10.2307/1913236)

An error-correction model is:

$$
\Delta\log M_{i,t}
=
\lambda_i s_{t-1}
+
\sum_{\ell=1}^{L}\gamma_{i,\ell}\Delta\log M_{i,t-\ell}
+
\sum_{\ell=1}^{L}\delta_{i,\ell}^\top\Delta x_{t-\ell}
+\epsilon_{i,t}.
$$

For a positive residual interpreted as an expensive ETF, the expected restoring response requires the appropriate negative adjustment.

A simple residual process is:

$$
s_{t+\Delta}-\mu
=
\phi(s_t-\mu)+\eta_{t+\Delta},
\qquad 0<\phi<1.
$$

Its half-life is:

$$
H_{1/2}
=
-\frac{\Delta\log2}{\log\phi}.
$$

Expected convergence over $H=n\Delta$:

$$
E[s_{t+H}-s_t\mid\mathcal I_t]
=
-(1-\phi^n)(s_t-\mu).
$$

If $\phi$ is indistinguishable from one, or half-life uncertainty extends beyond the feasible holding period, disable convergence trading.

**Assumptions:** stable equilibrium and restoring dynamics over the trading regime.

**Data:** synchronized levels over many sessions, returns, and costs. A few hours of high-frequency ticks do not establish a durable equilibrium.

**Recalibration:** equilibrium relation weekly on candidate 60–120-session windows; short-run dynamics daily; stability monitored intraday.

**Advantages:** directly estimates how much discrepancy should close and how quickly.

**Weaknesses:** breaks, selection bias across many pairs, and convergence through the supposedly “fair” leg moving instead.

**Look-ahead protection:** select pairs and estimate equilibrium using training data; use appropriate residual-based critical values; validate actual convergence separately; never select pairs from full-sample stationarity.

## 11. Keep order-book adjustments in the short-horizon market-price layer

For best bid $b$, ask $a$, and corresponding depths $D_b,D_a$:

$$
M=\frac{a+b}{2},
\qquad
I=\frac{D_b-D_a}{D_b+D_a},
$$

$$
M^{micro}
=
\frac{aD_b+bD_a}{D_b+D_a}.
$$

The microprice is a candidate predictor, not an intrinsic-value estimate.

A modest overlay is:

$$
E[\log M_{i,t+H}\mid\mathcal I_t]
=
\widehat v_{i,t}
+\widehat{\bar\pi}_{i,t}
+\widehat u_{i,t+H}
+\gamma_{i,H}^\top z_{i,t},
$$

where $z$ can include imbalance, spread, depth slope, recent executed flow if available, volatility, observation ages and time-of-day indicators.

Use book features to predict short-horizon movement, adverse selection and execution cost. Do not mechanically increase economic NAV because the bid queue is large.

**Assumptions:** book information has stable incremental predictive content at the chosen horizon.

**Data:** sequential depth observations; trade messages for reliable executed-flow measures.

**Recalibration:** daily coefficients; weekly time-of-day profiles using prior sessions.

**Advantages:** directly relevant to execution.

**Weaknesses:** fleeting quotes, cancellations, own-order contamination and fill-selection effects.

**Look-ahead protection:** features must precede the decision; train on future markouts only after they mature; exclude your own displayed size where identifiable.

## 12. Select feeds empirically, separately by target and horizon

The question is not simply “Which feed is best?” It is:

> Which feed adds reliable information for this ETF, at this horizon, under the observations actually available?

Use three distinct targets:

1. **NAV tracking:** later-received NAV measured at its stated valuation time, acknowledging it is noisy.
2. **Market-price prediction:** future ETF midpoint or robust short-window price.
3. **Trading outcome:** executable, net, fill-conditioned P&L.

Success on one does not imply success on the others. A feed can predict the administrator’s valuation conventions without predicting future tradable prices.

Compare a prespecified candidate set:

- Each individual feed.
- Bullion plus coin.
- Global gold and FX separately.
- Local feeds plus incremental global/FX information.
- Leave-one-out ETF factor.
- Small combinations of peer and underlying factors.
- Versions with age/quality weighting.
- Versions excluding each feed in turn.

For predictive lead-lag testing:

$$
r_{i,t\rightarrow t+H}
=
a_H+
\sum_{k,\ell\geq0}
b_{k,\ell,H}r_{k,t-\ell}
+c_H^\top z_t+\epsilon_{i,t+H}.
$$

All predictors must be available at $t$. Investigate both directions: ETFs may predict certificates or FX proxies.

For incremental information:

$$
\Delta_k
=
L(\mathcal M_{-k})-L(\mathcal M_{+k}),
$$

where $L$ is out-of-sample loss. Positive $\Delta_k$ favors adding feed $k$.

Evaluate MAE/RMSE, predictive log loss or interval score, coverage, turnover, and net executable results. Use session-block bootstrap intervals and account for overlapping forecast horizons and multiple candidate searches.

An illustrative promotion policy, fixed **before** final testing:

| Decision | Criteria |
|---|---|
| Retain as a core input | At least 2% relative loss improvement; positive improvement in at least 4 of 5 chronological validation blocks; block-bootstrap 95% lower bound above zero; no material deterioration in tail errors or net execution |
| Retain conditionally | Benefit is reproducible only in a defined regime, such as a market closure or low-liquidity interval |
| Down-weight | Marginal gain, high redundancy, wide coefficient uncertainty, or worsening age/liquidity |
| Exclude from active forecasting | Documented data defect; unavailable timing; or repeated out-of-sample harm after convention and latency investigation |
| Keep as a diagnostic | No reliable predictive gain, but useful for checking basis, units, or regime changes |

The 2% and 4-of-5 settings are proposed governance choices, not universal statistical constants.

For contradictory feeds, investigate in this order:

1. Currency and physical units.
2. Contract, warehouse, purity and valuation conventions.
3. Actual event and receive latency.
4. Quote versus trade versus indicative value.
5. Liquidity and executable size.
6. Revisions and vendor transformations.
7. Regime-specific lead-lag changes.

**Disagreement alone is never an exclusion rule.**

For a small ensemble, choose nonnegative model weights from prior validation:

$$
\min_{\omega}
\sum_t\left(y_t-\sum_m\omega_m\widehat y_{m,t}\right)^2
+\lambda\|\omega\|_2^2
+\eta\sum_m\omega_m\,\mathrm{Instability}_m,
$$

$$
\omega_m\geq0,\qquad\sum_m\omega_m=1.
$$

These are model-combination weights, not portfolio exposures. Missing-feed handling must use previously validated fallback models; do not silently renormalize an untested combination.

Report each feed’s improvement interval, rank range, frequency of being best across blocks, age-conditioned performance and outage performance. Without the actual dataset, **the feed ranking is unknown**.

## 13. Let global gold × USD/IRR earn its role

The proxy has a clear dimensional meaning:

$$
G_t=\frac{Z_tD_t}{31.1034768}.
$$

But a local bullion price can be represented as:

$$
\log B_t
=
\log G_t+\ell_t,
$$

where $\ell_t$ captures local basis, segmentation, settlement differences, access restrictions, and measurement mismatch.

Nothing requires $\ell_t$ to be small or rapidly mean-reverting.

Test three roles:

| Candidate role | Evidence required |
|---|---|
| Primary statistical anchor | Stable local relationship; reliable timing; best out-of-sample level/return performance; manageable basis uncertainty |
| Incremental fast predictor | Predicts local changes beyond certificates and peer ETFs at executable latency |
| Slower reference | Helps explain longer-horizon value or stress scenarios but adds little intraday information |

It may serve different roles during different sessions. For example, a globally fresh gold quote multiplied by an old or non-executable FX indication is not a fully fresh local gold quote.

If multiple FX feeds become available, model them separately initially. If only one is available, characterize that one precisely and acknowledge that alternative-rate model risk cannot be empirically resolved from the given data.

A statistical anchor need not be tradable. An arbitrage anchor requires a feasible conversion or hedge mechanism in addition to predictive quality.

## 14. Produce uncertainty bands that include model disagreement

For a propagated log-value estimate, a useful decomposition is:

$$
\sigma^2_{v,i,t}
\approx
P_{\mathrm{anchor}}
+\Delta x^\top\operatorname{Var}(\widehat\beta_i)\Delta x
+\widehat\beta_i^\top\Omega_{\mathrm{feed},t}\widehat\beta_i
+Q_i\Delta t
+\sigma^2_{\mathrm{spec},i,t}.
$$

The terms represent anchor, exposure, feed, portfolio-drift and model-specification uncertainty. This additive form is approximate; retain cross-covariances when material, and do not add components already included in a state covariance twice.

For model disagreement:

$$
\bar v_i=\sum_m\omega_m\widehat v_{i,m},
$$

$$
\sigma^2_{\mathrm{ensemble},i}
=
\sum_m\omega_m
\left[
\sigma^2_{i,m}
+(\widehat v_{i,m}-\bar v_i)^2
\right].
$$

Under a calibrated approximately Gaussian log-state:

$$
\widehat V_i^{median}=e^{\bar v_i},
$$

$$
[V_i^L,V_i^U]
=
\left[
e^{\bar v_i-z\sigma_i},
e^{\bar v_i+z\sigma_i}
\right].
$$

The mean under that assumption is $e^{\bar v_i+\sigma_i^2/2}$. Do not use the median as an expected cash-flow value without considering this distinction.

Prefer empirically calibrated residual quantiles when tails are asymmetric:

$$
[V_i^L,V_i^U]
=
\left[
e^{\bar v_i+q_{0.025}},
e^{\bar v_i+q_{0.975}}
\right].
$$

Use separate bands for:

- Current latent underlying value.
- Future market price.
- Net executable trade P&L.

A confidence interval around the fitted mean is usually too narrow for trading decisions. The future-P&L distribution must also include convergence failure, hedge mismatch, fills, and exit costs.

Validate coverage by ETF, time of day, volatility, feed age and market status. Since true economic NAV is unobserved, state explicitly that underlying-value coverage is only partially testable; later published NAV is an imperfect benchmark.

For pair uncertainty, preserve covariance:

$$
\operatorname{Var}(v_i-hv_j)
=
\sigma_i^2+h^2\sigma_j^2-2h\operatorname{Cov}(v_i,v_j).
$$

Also include uncertainty in $h$.

## 15. Detect structural changes before the model explains them away

Monitor standardized one-step innovations:

$$
z_{i,t}
=
\frac{y_{i,t}-\widehat y_{i,t|t^-}}
{\sqrt{S_{i,t}}}.
$$

A two-sided CUSUM is:

$$
C_t^+=\max(0,C_{t-1}^++z_t-k),
$$

$$
C_t^-=\max(0,C_{t-1}^--z_t-k).
$$

Monitor exposure changes:

$$
D_t=
(\widehat\beta_{\mathrm{short}}-\widehat\beta_{\mathrm{long}})^\top
\widehat\Omega_\Delta^{-1}
(\widehat\beta_{\mathrm{short}}-\widehat\beta_{\mathrm{long}}),
$$

where $\widehat\Omega_\Delta$ accounts for overlap between the two estimates.

Also watch:

- Persistent NAV innovations in one direction.
- Residual variance increases.
- Loss of convergence.
- Changes in NAV release timing.
- Previously stable warehouse or coin/bullion basis relationships breaking.
- Multiple ETFs moving together against all non-ETF references.

**Calibration:** choose alarm thresholds on earlier sessions to target a tolerable false-alarm rate, such as one false alarm per 20 sessions as an initial research setting.

**Action:** pause new entries in the affected ETF, cancel exposed quotes, widen model uncertainty, and manage existing positions using the precommitted risk policy. Re-enable only after a fresh validation period or an explained data correction.

**Limitation:** price data can establish a behavior change; it generally cannot prove a portfolio change.

## 16. Define the relative-value trade and hedge in economic units

Let:

$$
e_{i,t}=\log M_{i,t}-\log F_{i,t}.
$$

For long $i$, short or inventory-sale $j$:

$$
d_t=e_{i,t}-h e_{j,t}.
$$

A negative $d_t-\mu_d$ indicates that $i$ is relatively cheap under the model.

If $h$ is a hedge-notional ratio:

$$
q_j
\approx
h\,q_i\frac{M_i}{M_j}.
$$

Round to valid lots, then recompute exposure and costs. Equal units are generally incorrect.

A single-factor hedge uses:

$$
h=\frac{\beta_i}{\beta_j}.
$$

A multifactor hedge can minimize:

$$
\min_h
(\beta_i-h\beta_j)^\top\Sigma_f(\beta_i-h\beta_j)
+\lambda_h\,\mathrm{Cost}(h).
$$

With several hedge instruments, let $n$ be their signed IRR notionals:

$$
\min_n
(N\beta_i+B_H^\top n)^\top
\Sigma_f
(N\beta_i+B_H^\top n)
+\lambda\,\mathrm{Cost}(n),
$$

subject to inventory, borrowing, liquidity, cash and position constraints.

Two ETFs may share overall gold exposure while differing materially in coin-premium exposure. A one-leg hedge cannot generally neutralize several independent factors.

Using:

$$
d_{t+\Delta}-\mu_d
=
\phi(d_t-\mu_d)+\eta_{t+\Delta},
$$

the approximate gross convergence profit over $H=n\Delta$, for long-leg notional $N$, is:

$$
\widehat G_H
=
-N(1-\phi^n)(d_t-\mu_d).
$$

This is a local return approximation. The execution decision should ultimately use native-unit cash flows and joint price/fill scenarios.

## 17. Use an exact entry gate based on the full round trip

For long $q_i$ units of $i$ and short $q_j$ units of $j$:

$$
\Pi_H
=
q_i(P^{sell}_{i,t+H}-P^{buy}_{i,t})
+
q_j(P^{sell}_{j,t}-P^{buy}_{j,t+H})
-C_{\mathrm{fees}}
-C_{\mathrm{funding}}
-C_{\mathrm{borrow}}.
$$

If executable prices already contain spread and depth impact, do not subtract those costs again.

Under a simplified common proportional fee $f$ per side and approximately unchanged notionals:

$$
C_{\mathrm{fees}}\approx2fN(1+h).
$$

There are four transactions in a completed pair round trip.

Set the entry condition:

$$
\boxed{
\widehat G_H
>
\widehat C_{\mathrm{roundtrip}}
+B_{\mathrm{model}}
+B_{\mathrm{legging}}
+B_{\mathrm{tail}}
+\Pi_{\min}
}
$$

and, independently, require a positive conservative lower confidence bound on expected net profit. Where components overlap, use a joint scenario model instead of summing duplicated buffers.

An initial research filter can require:

$$
\frac{|d_t-\mu_d|}{\widehat\sigma_d}\geq2.5.
$$

That filter never overrides the economic gate. A three-standard-deviation signal can still be too expensive to trade.

**Take the trade only if all conditions hold:**

- The model and this ETF/pair passed out-of-sample validation.
- Required feeds and books pass quality/age limits.
- Expected convergence fits within the permitted holding period.
- Native-unit executable prices satisfy the entry inequality.
- All sale legs are permitted and operationally available.
- Cash, inventory, collateral and settlement resources are reserved.
- Rounded quantities remain within factor-risk limits.
- Both normal exit and partial-fill recovery are feasible.

Otherwise: **stand aside**.

For an unhedged ETF discount purchase, evaluate the ETF’s entire directional P&L distribution. A discount is not a hedge against gold falling.

## 18. Choose legs according to actual selling access

| Available access | Permitted strategy |
|---|---|
| Confirmed ETF short mechanism | Buy cheap ETF; short rich ETF in calibrated quantities |
| Owned rich ETF inventory | Sell part of that inventory and buy cheap ETF |
| Executable, authorized derivative hedge | Trade ETF against a calibrated derivative hedge, including basis, multiplier, margin and expiry |
| No short access and no suitable inventory | No market-neutral pair entry |
| Certificate prices without executable certificate books/access | Use certificates as signals only |

An inventory switch creates a relative position **against the portfolio you otherwise would have held**. The remaining portfolio can still be directionally long gold. Report both absolute P&L and performance versus that unchanged-inventory benchmark.

The stated feeds include full ETF books, but not necessarily full certificate books or derivative books. Therefore the first execution backtest should use **ETF legs only**, unless additional executable hedge data are obtained.

## 19. Use bounded limit orders and an explicit execution state machine

Use marketable limit orders for taking liquidity. Use IOC only if the venue and OMS support it as documented. If IOC is unavailable, a limit order followed by cancellation remains exposed until cancellation is acknowledged.

Before submission, choose leg limits $L_i^B,L_j^S$ satisfying:

$$
q_iL_i^B-q_jL_j^S
\leq
E[q_iP_{i,H}-q_jP_{j,H}\mid\mathcal I_t]
-C_{\mathrm{remaining}}
-B-\Pi_{\min}.
$$

Allocate the price budget between legs using estimated liquidity and slippage. Respect ticks and daily limits.

The initial intraday policy should be:

1. **Observe and reserve.** Validate the signal; reserve both legs’ resources.
2. **Submit the harder-to-fill leg first.** Classify difficulty from prior fill/slippage evidence. Require the other leg to be sufficiently liquid for prompt hedging.
3. **Hedge actual fills immediately.** For every acknowledged partial fill, submit only the corresponding hedge quantity.
4. **Cancel unused quantity.** If the signal fails, quote conditions change, or the order lifetime expires, request cancellation.
5. **Reconcile.** Include fills received while cancellation is pending. Never assume cancel-request means canceled.
6. **Manage the matched position.**
7. **Exit and verify flatness or restored inventory.**

If both legs are liquid, near-simultaneous bounded orders can be a separate tested policy. They are not atomic. Do not automatically prefer speed over controlled partial-fill exposure.

Predefine maximum unhedged exposure $E_{\max}$ and duration $\tau_{\max}$. One practical duration rule is:

$$
\tau_{\max}
=
\min\left(
2L_{99}^{hedge},
\ \tau:\mathrm{StressLoss}(E,\tau)=B_{\mathrm{leg}}
\right),
$$

where $L_{99}^{hedge}$ is measured end-to-end hedge completion latency. If ordinary hedge completion cannot reliably fit inside the risk deadline, reject the trade before entry.

On hedge failure:

- Cancel outstanding alpha quantity.
- Attempt the pre-authorized substitute hedge if available.
- Otherwise reduce the original fill using a precommitted emergency price budget.
- If markets prevent execution, record the trapped exposure and stop new trading. Do not assume a stop order can force a fill through a halt or empty book.

Freeze the trade’s hedge ratio unless a separate risk trigger justifies rebalancing. Constant small hedge changes can consume the expected edge.

## 20. Define cancellation, exit, and no-trade conditions in advance

Cancel an unfilled order when:

- Recomputed conservative expected profit is below the minimum.
- Price moves beyond its approved limit.
- Required depth disappears.
- A feed becomes stale beyond its validated threshold.
- A halt, auction transition, price-bound restriction, or structural-break alarm occurs.
- Cash, inventory, position or message-rate constraints are breached.
- The approved order lifetime expires.

For a matched convergence position, an initial research policy is:

- **Profit exit:** residual reaches its estimated center or enters $|z|\leq0.5$, subject to executable exit economics.
- **Time exit:** close at a preselected horizon, initially test $H_{\max}=3H_{1/2}$, capped before the relevant session close.
- **Risk exit:** close or reduce when the trade-loss budget, factor-exposure limit, or model-break rule triggers.
- **Continuation check:** exit earlier when expected additional convergence no longer compensates for incremental holding risk and cost.

The 2.5 entry and 0.5 exit levels are starting candidates. Select them using validation, then freeze them for testing.

Hard no-trade conditions include:

- No independent sellable/hedge leg.
- Insufficient economic-timestamp information for the claimed horizon.
- The apparent edge exists only against stale NAV.
- Too much unresolved model disagreement.
- Unstable hedge ratio or unidentified factor exposures.
- No credible convergence within the available session.
- A locked limit queue or halt prevents an acceptable recovery path.
- Missing data whose fallback model has not been tested.
- Dependence on receiving sale proceeds before they are actually reusable.

## 21. Treat market making as a separate fill-conditioned business

Let $Q$ be signed ETF inventory and $\sigma^2_{\mathrm{unhedged}}$ its residual risk after feasible hedging. A simple reservation price is:

$$
R_{i,t}
=
F_{i,t}
-\gamma Q_{i,t}\sigma^2_{\mathrm{unhedged}}H.
$$

Candidate quotes are:

$$
p^b=R-\delta_b,
\qquad
p^a=R+\delta_a.
$$

The spreads must cover hedge cost, fees, adverse selection, uncertainty and inventory risk. This inventory-risk perspective is consistent with the classical market-making literature, but the original model’s assumptions require local validation. [Avellaneda and Stoikov](https://math.nyu.edu/inmemoriam/avellaneda/HighFrequencyTrading.pdf)

For the bid, require:

$$
E[P^{liquidation}_{i,t+H}-p^b
\mid \text{bid fills},\mathcal I_t]
-C_{\mathrm{hedge,fees}}>0.
$$

For the ask:

$$
E[p^a-P^{replacement}_{i,t+H}
\mid \text{ask fills},\mathcal I_t]
-C_{\mathrm{hedge,fees}}>0.
$$

Conditioning on fills matters: a quote can have positive unconditional theoretical edge and lose money whenever it actually trades.

Use passive limit orders, inventory limits and the same hedge-recovery machinery. Quote only the side allowed by available inventory/access. Cancel when fill-conditioned value deteriorates or the hedge becomes unavailable.

Estimate quote distance, lifetime and inventory skew from historical fill-conditioned outcomes; refresh parameters daily and monitor realized markouts intraday.

## 22. Build the backtest as a replay of information and orders

The simulator needs two separate views:

- **Strategy view:** only information received by the simulated decision time.
- **Venue view:** the reconstructed market state when the simulated order reaches the exchange.

Core events are:

- Book updates and snapshots.
- Trade reports, if available.
- Certificate, global-gold and FX updates.
- NAV publications and revisions.
- Session/status changes.
- Decision and order submission.
- Exchange arrival, acknowledgement, partial fill, rejection.
- Cancel request and cancel acknowledgement.
- Settlement, funding and margin events.

Model latency as distributions:

$$
L_{\mathrm{total}}
=
L_{\mathrm{feed}}
+L_{\mathrm{processing}}
+L_{\mathrm{outbound}}
+L_{\mathrm{exchange}}
+L_{\mathrm{return}}.
$$

Use measured distributions when possible, including congestion and outages. Test sensitivity to materially worse latency.

For taking orders:

- Match at simulated exchange-arrival time.
- Respect the order limit.
- Consume displayed depth conservatively.
- Permit partial fills and rejections.
- Account for depth disappearance before arrival.

For passive orders, track queue ahead:

$$
Q^{ahead}_{t+1}
=
Q^{ahead}_t
-\text{executions ahead}
-\text{estimated cancellations ahead}.
$$

With order-level data and documented priority, reconstruction can be relatively precise. With price-level data, cancellation location is uncertain. Run pessimistic, central and optimistic queue assumptions.

**Full depth is not necessarily full order-level history.** Depth reduction does not tell you whether orders traded or canceled. Never assume a fill merely because the market touched your price or displayed size declined.

If trade messages and order identifiers are unavailable, passive-fill results remain a bounded sensitivity analysis. They cannot justify a precise market-making profitability claim.

Include:

- Correct historical fee schedules and rules.
- Settlement-aware cash and segregated funding.
- Inventory and borrowing constraints.
- Funding/storage/derivative costs where applicable.
- Halts, auctions, price limits and rejected orders.
- Partial fills and emergency unwinds.
- Survivorship-free ETF membership.
- NAV and corporate-action vintages.
- All parameter changes and model versions.
- Capacity and own-market-impact scenarios.

Historical market replay is counterfactual: your orders would have changed the book. Restrict initial sizes and stress impact rather than claiming exact fills at unlimited scale.

## 23. Validate in chronological stages and demand economic improvement

A practical first dataset target is several months of complete event history covering different volatility and liquidity conditions. A useful walk-forward template is:

- 60 sessions for estimation.
- 20 sessions for model/threshold validation.
- 20 sessions for untouched evaluation.
- Roll forward chronologically.
- Reserve a final period not used in any design choice.

Adjust lengths to the actual history and regime stability. Large tick counts do not replace independent market regimes.

Purge samples whose future-return labels cross training boundaries. Keep scaling, feature selection, pair selection, PCA loadings, latency estimates and threshold choices inside the permitted historical window.

Run tests in this order:

| Stage | Required question |
|---|---|
| Data audit | Are units, timestamps, revisions and book reconstruction credible? |
| Fair-value estimation | Does the model beat stale NAV and simple single-feed alternatives? |
| Forecasting | Does it beat price persistence at the intended horizon? |
| Feed selection | Does each retained feed add stable information? |
| Convergence | Do selected discrepancies actually close within the holding period? |
| Execution | Does the advantage survive arrival latency, depth and partial fills? |
| Portfolio | Does it survive shared factors, inventory and funding constraints? |
| Stress | Does it remain viable under outages, worse latency and poorer fills? |

Report:

- Error and interval coverage by ETF, horizon and regime.
- Exposure uncertainty and structural-break frequency.
- Net P&L and session-level risk-adjusted returns.
- Maximum drawdown and expected shortfall.
- Fill ratio, completion ratio and hedge delay.
- Realized adverse-selection markouts.
- Inventory duration and trapped exposure.
- Turnover, costs, capital usage and capacity.
- Dependence on individual days, ETFs and assumptions.

Promote a more complex model only if it improves **out-of-sample calibration or net economic results** enough to justify its additional failure modes. PCA, Kalman filtering and robust regression are challengers to the baseline, not mandatory layers.

A numerical illustration shows how this becomes a decision. Suppose a calibrated pair has an 80-basis-point residual discrepancy, but only 50% is expected to close during the permitted holding period:

$$
\text{expected gross convergence}=40\text{ bp}.
$$

If the full round trip costs 24 bp, model/legging reserves are 12 bp, and minimum required profit is 5 bp:

$$
40<24+12+5.
$$

The decision is **stand aside**, despite the apparently large 80 bp discrepancy.

If a second opportunity offers 60 bp expected convergence under the same assumptions:

$$
60>24+12+5,
$$

it passes the economic gate—but proceeds only if quantities, sale access, depth, recovery path and risk limits also pass.

The first system I would take into paper trading is therefore a **fixed-exposure, NAV-updated baseline with a separately validated peer-relative signal, ETF-only executable legs, conservative marketable limits, and explicit partial-fill handling**. Its essential output is one auditable decision record: estimated values and bands, expected convergence, exact quantities and limits, full costs, remaining risks, cancellation deadlines, and either **trade** or **stand aside**.
