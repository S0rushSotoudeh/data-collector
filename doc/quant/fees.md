# Iran Securities Trading Fees

This document summarizes the trading fees for three main categories in Iran's capital market:

1. Stocks
2. Options
3. Bonds, including Akhza treasury bills

All rates are stated as a percentage of the transaction value.

---

## 1. Stocks

### Tehran Stock Exchange

| Fee Recipient | Buy | Sell |
|---|---:|---:|
| Brokerage | 0.3040% | 0.3040% |
| Tehran Stock Exchange | 0.0256% | 0.0256% |
| Securities and Exchange Organization | 0.0256% | 0.0256% |
| Central Securities Depository | 0.0096% | 0.0144% |
| Technology Management Company | 0.0080% | 0.0120% |
| Sales tax | 0.0000% | 0.5000% |
| **Total** | **0.3712%** | **0.8800%** |

**Total round-trip cost:** 1.2512%

A round trip means buying and later selling the same position at the same transaction value. It does not include bid-ask spread, slippage, or price movement.

### Iran Fara Bourse

| Fee Recipient | Buy | Sell |
|---|---:|---:|
| Brokerage | 0.3040% | 0.3040% |
| Iran Fara Bourse | 0.0256% | 0.0256% |
| Securities and Exchange Organization | 0.0160% | 0.0240% |
| Central Securities Depository | 0.0096% | 0.0144% |
| Technology Management Company | 0.0080% | 0.0120% |
| Sales tax | 0.0000% | 0.5000% |
| **Total** | **0.3632%** | **0.8800%** |

**Total round-trip cost:** 1.2432%

### Important Notes

- The 0.5% tax applies only when selling ordinary shares.
- There is no equivalent sales tax on the purchase side.
- For stocks and preemptive rights, 30% of the brokerage commission is allocated to the Market Development Fund.
- This allocation is deducted from the brokerage's own commission and is not an additional fee charged to the trader.

For example, from the 0.304% brokerage fee on one side of a stock trade:

- 0.0912% goes to the Market Development Fund.
- 0.2128% remains as the brokerage's gross share.

---

## 2. Options

Option trading fees are calculated on the **option premium transaction value**, not on the strike value, exercise value, or notional value of the underlying asset.

### Options Listed on the Tehran Stock Exchange

| Fee Recipient | Buy | Sell |
|---|---:|---:|
| Brokerage | 0.0800% | 0.0800% |
| Tehran Stock Exchange | 0.0080% | 0.0080% |
| Central Securities Depository | 0.0080% | 0.0080% |
| Technology Management Company | 0.0040% | 0.0040% |
| Securities and Exchange Organization | 0.0030% | 0.0030% |
| **Total** | **0.1030%** | **0.1030%** |

**Total round-trip cost:** 0.2060%

### Options Listed on Iran Fara Bourse

| Fee Recipient | Buy | Sell |
|---|---:|---:|
| Brokerage | 0.0800% | 0.0800% |
| Iran Fara Bourse | 0.0080% | 0.0080% |
| Central Securities Depository | 0.0080% | 0.0080% |
| Technology Management Company | 0.0040% | 0.0040% |
| Securities and Exchange Organization | 0.0020% | 0.0030% |
| **Total** | **0.1020%** | **0.1030%** |

**Total round-trip cost:** 0.2050%

### Important Notes

- These rates apply to ordinary opening and closing trades.
- Exercise, assignment, expiration, and settlement may involve separate rules or charges.
- Option fees are much lower than stock fees because there is no 0.5% stock-sale tax.
- For strategy and arbitrage calculations, fees should be applied to every executed option leg separately.

---

## 3. Bonds and Akhza

Akhza instruments are Iranian government treasury bills and are treated as debt securities for trading-fee purposes.

The published rates are the same for debt securities traded on the Tehran Stock Exchange and Iran Fara Bourse.

| Fee Recipient | Buy | Sell |
|---|---:|---:|
| Brokerage | 0.0600% | 0.0600% |
| Exchange or Iran Fara Bourse | 0.0100% | 0.0100% |
| Central Securities Depository | 0.0015% | 0.0015% |
| Technology Management Company | 0.0010% | 0.0010% |
| **Total** | **0.0725%** | **0.0725%** |

**Total round-trip cost:** 0.1450%

### Important Notes

- Akhza trades do not carry the 0.5% sales tax that applies to ordinary shares.
- The fee is charged on the transaction value.
- Buy and sell fee rates are identical.
- For yield and arbitrage calculations, the round-trip fee should be included whenever the bond may need to be sold before maturity.
- Holding an Akhza instrument to maturity may avoid a secondary-market sale transaction, but settlement and maturity procedures should still be checked separately.

---

## Quick Comparison

| Instrument | Buy Fee | Sell Fee | Round Trip |
|---|---:|---:|---:|
| Tehran Stock Exchange stock | 0.3712% | 0.8800% | 1.2512% |
| Iran Fara Bourse stock | 0.3632% | 0.8800% | 1.2432% |
| Tehran Stock Exchange option | 0.1030% | 0.1030% | 0.2060% |
| Iran Fara Bourse option | 0.1020% | 0.1030% | 0.2050% |
| Akhza / debt security | 0.0725% | 0.0725% | 0.1450% |

> Rates may change after new regulatory circulars. Always verify the latest official fee schedule before using these figures in production trading or arbitrage systems.