# Retrieving Gold Market Data from IME and TSETMC

## Overview

Gold instruments in the Iranian financial market include Exchange Traded Funds (صندوق‌های سرمایه‌گذاری مبتنی بر طلا/کالا) listed on the Iran Mercantile Exchange (IME) and traded on TSETMC.

This doc covers retrieving the official Gold Fund Universe, instrument metadata, historical order books (top-5 bid/ask limits), and historical trade ticks.

---

## 1. Official Gold Fund Universe (IME Portal)

Retrieves all official gold exchange-traded funds registered with IME.

```
GET https://www.ime.co.ir/ExchangeTradedFunds.html
```

### HTML Table Structure

Each table row contains:
- `td[0]`: Asset Class (`طلا` or `شاخه طلا`)
- `td[1]`: Fund Name / Symbol (e.g. `صندوق سرمایه گذاری طلای عیار مفید`)
- `td[2]`: TSETMC Link containing `insCode` (e.g. `instInfo/34144395039913458` or `?i=34144395039913458`)

---

## 2. Instrument Info (TSETMC CDN)

Fetches comprehensive reference metadata for a specific gold fund using its `insCode`.

```
GET https://cdn.tsetmc.com/api/Instrument/GetInstrumentInfo/{insCode}
```

### Example

```bash
curl -H "User-Agent: Mozilla/5.0" https://cdn.tsetmc.com/api/Instrument/GetInstrumentInfo/34144395039913458
```

### Response (abridged)

```json
{
  "instrumentInfo": {
    "insCode": "34144395039913458",
    "lVal30": "صندوق طلاي عيار مفيد",
    "lVal18": "Ayat Gold Fund",
    "lVal18AFC": "عيار",
    "cIsin": "IRO1GLD00001",
    "instrumentID": "GLD001",
    "zTitad": 5000000000.0,
    "baseVol": 1,
    "flow": 1,
    "flowTitle": "بورس اوراق بهادار تهران",
    "cgrValCot": "1",
    "cgrValCotTitle": "عادي",
    "cSecVal": "68",
    "lSecVal": "صندوق سرمايه گذاري قابل معامله",
    "staticThreshold": {
      "psGelStaMax": 615000.00,
      "psGelStaMin": 575000.00
    },
    "minWeek": 580000.00,
    "maxWeek": 610000.00,
    "minYear": 320000.00,
    "maxYear": 610000.00,
    "qTotTran5JAvg": 15000000.0,
    "dEven": 20260829
  }
}
```

---

## 3. Order Book (Best Limits) History

Fetches historical snapshots of the top-5 bid/ask depth for a given date.

```
GET https://cdn.tsetmc.com/api/BestLimits/{insCode}/{yyyyMMdd}
```

### Example

```bash
curl -H "User-Agent: Mozilla/5.0" https://cdn.tsetmc.com/api/BestLimits/34144395039913458/20260826
```

### Response

```json
{
  "bestLimitsHistory": [
    {
      "hEven": 123000,
      "refID": 15683334859,
      "number": 1,
      "pMeDem": 596950.0,
      "qTitMeDem": 2247,
      "zOrdMeDem": 1,
      "pMeOf": 596960.0,
      "qTitMeOf": 31851,
      "zOrdMeOf": 8
    }
  ]
}
```

---

## 4. Trade History (Intraday Ticks)

Fetches every executed trade transaction for a given date.

```
GET https://cdn.tsetmc.com/api/Trade/GetTradeHistory/{insCode}/{yyyyMMdd}/false
```

### Example

```bash
curl -H "User-Agent: Mozilla/5.0" https://cdn.tsetmc.com/api/Trade/GetTradeHistory/34144395039913458/20260826/false
```

### Response

```json
{
  "tradeHistory": [
    {
      "nTran": 128774,
      "hEven": 123000,
      "pTran": 596950.0,
      "qTitTran": 200,
      "canceled": 0
    }
  ]
}
```
