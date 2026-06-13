# Retrieving Akhza (اخزا) Data from TSETMC

## Overview

Akhza (اسناد خزانه اسلامی) = Islamic Treasury Bills traded on the Iran Fara Bourse (OTC Novel Financial Instruments market). This doc covers how to pull instrument metadata, live/static data, and order book history via TSETMC's REST APIs.

---

## 1. Instrument Info

Get metadata for a specific bond (insCode = 12-digit instrument ID).

```
GET https://cdn.tsetmc.com/api/Instrument/GetInstrumentInfo/{insCode}
```

### Example

```bash
curl https://cdn.tsetmc.com/api/Instrument/GetInstrumentInfo/36408112396351116
```

### Response (abridged)

```json
{
  "instrumentInfo": {
    "insCode": "36408112396351116",
    "lVal30": "اسنادخزانه-م2بودجه02-050923",
    "lVal18": "TreasuryBill261214",
    "lVal18AFC": "اخزا202",
    "cIsin": "IRB3TR160593",
    "instrumentID": "IRB3TR160591",
    "zTitad": 150000000.0,
    "baseVol": 1,
    "flow": 2,
    "flowTitle": "بازار فرابورس",
    "cgrValCot": "I1",
    "cgrValCotTitle": "بازار ابزارهاي نوين مالي فرابورس",
    "cSecVal": "69",
    "lSecVal": "اوراق تامين مالي",
    "staticThreshold": {
      "psGelStaMax": 867440.00,
      "psGelStaMin": 816920.00
    },
    "minWeek": 838150.00,
    "maxWeek": 844910.00,
    "minYear": 615670.00,
    "maxYear": 844910.00,
    "qTotTran5JAvg": 29068.0,
    "dEven": 20260610
  }
}
```

### Key Fields

| Field | Meaning |
|-------|---------|
| `insCode` | 12-digit instrument identifier |
| `lVal30` | Persian name (full) |
| `lVal18` | English short name (hints at maturity) |
| `cIsin` | ISIN code |
| `zTitad` | Total issued units |
| `flow` | Market flow (2 = Fara Bourse OTC) |
| `cgrValCot` | Market segment code |
| `psGelStaMax` | Upper static price threshold |
| `psGelStaMin` | Lower static price threshold |
| `dEven` | Last trade date (YYYYMMDD) |

---

## 2. Order Book (Best Limits) History

Get historical snapshots of the top-5 bid/ask for a given date.

```
GET https://cdn.tsetmc.com/api/BestLimits/{insCode}/{yyyyMMdd}
```

### Example

```bash
curl https://cdn.tsetmc.com/api/BestLimits/36408112396351116/20260608
```

### Response

```json
{
  "bestLimitsHistory": [
    {
      "idn": 0,
      "dEven": 0,
      "hEven": 60123,
      "refID": 15174976313,
      "number": 1,
      "qTitMeDem": 0,
      "zOrdMeDem": 0,
      "pMeDem": 0.000,
      "pMeOf": 821980.000,
      "zOrdMeOf": 1,
      "qTitMeOf": 79
    }
  ]
}
```

### Key Fields per Entry

| Field | Meaning |
|-------|---------|
| `hEven` | Time (HHMMSS, intraday) |
| `number` | Rank in the order book (1-5) |
| `pMeDem` | Bid price |
| `qTitMeDem` | Bid quantity |
| `zOrdMeDem` | Number of bid orders |
| `pMeOf` | Ask price |
| `qTitMeOf` | Ask quantity |
| `zOrdMeOf` | Number of ask orders |

If the market is closed or no data exists for that day, the array is empty: `{"bestLimitsHistory":[]}`.

---

## 3. Closed Price History

TSETMC provides daily closing prices. The exact endpoint pattern was not found via a simple guess. Likely candidates to explore:

```
GET https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceHistory/{insCode}
GET https://cdn.tsetmc.com/api/Instrument/GetInstrumentHistory/{insCode}
```

Further API discovery on `cdn.tsetmc.com` is needed.

---

## 4. Searching All Akhza Instruments

TSETMC has a text-search endpoint that accepts Persian keywords. Search for `اخزا` to get all matching instruments (active and historical).

```
GET https://cdn.tsetmc.com/api/Instrument/GetInstrumentSearch/{keyword}
```

### Example

```bash
curl https://cdn.tsetmc.com/api/Instrument/GetInstrumentSearch/%D8%A7%D8%AE%D8%B2%D8%A7
```

(`%D8%A7%D8%AE%D8%B2%D8%A7` = URL-encoded `اخزا`)

### Response Structure

```json
{
  "instrumentSearch": [
    {
      "insCode": "36408112396351116",
      "lVal30": "اسنادخزانه-م2بودجه02-050923",
      "lVal18AFC": "اخزا202",
      "flow": 2,
      "cgrValCot": "I1",
      "flowTitle": "بازار فرابورس",
      "cgrValCotTitle": "بازار ابزارهاي نوين مالي فرابورس",
      "lastDate": 1
    }
  ]
}
```

### Key Fields

| Field | Meaning |
|-------|---------|
| `insCode` | Primary instrument ID (use this for all other API calls) |
| `lVal30` | Persian name |
| `lVal18AFC` | Short code (e.g., اخزا202, اخزا203) |
| `flow` | `2` = Fara Bourse |
| `cgrValCot` | `"I1"` = Novel Financial Instruments, `"41"` = Options |
| `lastDate` | `1` = active (recent trades), `0` = expired/inactive |

### All Instruments Found (as of 2026-06-10)

| insCode | Name | Short Code | Status |
|---------|------|------------|--------|
| `21702706902357649` | اسنادخزانه-م1بودجه02-050325 | اخزا201 | active |
| `36408112396351116` | اسنادخزانه-م2بودجه02-050923 | اخزا202 | active |
| `58965534586323216` | اسنادخزانه-م3بودجه02-050818 | اخزا203 | active |
| `67294227180710857` | اسنادخزانه-م4بودجه02-051021 | اخزا204 | active |
| `14238016822124618` | اسناد خزانه-م8بودجه02-041211 | اخزا208 | active |
| `18889629243439978` | اسنادخزانه-م9بودجه02-050811 | اخزا209 | active |
| `16697812875985850` | اسنادخزانه-م10بودجه02-051112 | اخزا210 | active |
| `50949399050647500` | اسناد خزانه-م11بودجه02-050720 | اخزا211 | active |
| `36248702773456944` | اسناد خزانه-م12بودجه02-050916 | اخزا212 | active |
| `25402505872480393` | اسناد خزانه-م13بودجه02-051021 | اخزا213 | active |
| `20529306741775719` | اسناد خزانه-م1-س.قوا03-060615 | اخزا301 | active |
| `35905772492287302` | اسنادخزانه-م1بودجه04-070607 | اخزا401 | active |
| `8502069339043866` | اسناد خزانه-م2بودجه04-070614 | اخزا402 | active |
| `24327721111488243` | اسناد خزانه-م3بودجه04-070718 | اخزا403 | active |
| `57655849747995489` | اسناد خزانه-م4بودجه04-070816 | اخزا404 | active |
| `45765735050842391` | اسناد خزانه-م5بودجه04-070420 | اخزا405 | active |
| `19362905444618753` | اسناد خزانه-م6بودجه04-071019 | اخزا406 | active |
| `31253774350964911` | اسناد خزانه-م7بودجه04-071110 | اخزا407 | active |
| `376512217097110` | اسناد خزانه-م2-س.قوا03-070626 | كاخزا302 | active |
| `3577388800305243` | اسنادخزانه-م1بودجه00-030821 | اخزا001 | expired |
| `69723868583662174` | اسنادخزانه-م3بودجه00-030418 | اخزا003 | expired |
| `69706833029046389` | اسناد خزانه-م10بودجه00-031115 | اخزا010 | expired |
| `4034432815122384` | اختيارخ اخزا11-930781-960331 | اخزا11خ2 | expired |
| `70132433125268787` | اختيارخ اخزا11-932171-960331 | اخزا11خ3 | expired |
| `3692443157966617` | اختيارخ اخزا11-933566-960331 | اخزا11خ4 | expired |
| `71601274953984874` | اسناد خزانه اسلامي950821 | اخزا4 | expired |
| `5142626877687530` | اسنادخزانه-م5بودجه96-970926 | اخزا605 | expired |
| `70718604552494663` | اسنادخزانه-م14بودجه96-981016 | اخزا614 | expired |
| `1982233425566381` | اسنادخزانه-م1بودجه97-970920 | اخزا701 | expired |
| `71772000724177515` | اسنادخزانه-م6بودجه97-990423 | اخزا706 | expired |
| `69018118187907177` | اسنادخزانه-م17بودجه97-981017 | اخزا717 | expired |
| `71901111301490182` | اسنادخزانه-م18بودجه97-000525 | اخزا718 | expired |
| `5126621656875241` | اسنادخزانه-م22بودجه97-000428 | اخزا722 | expired |
| `5203880991539408` | اسنادخزانه-م7بودجه98-000719 | اخزا807 | expired |
| `67744724115735698` | اسنادخزانه-م11بودجه98-001013 | اخزا811 | expired |
| `68250192165442911` | اسنادخزانه-م18بودجه98-010614 | اخزا818 | expired |
| `5181039426047414` | اسنادخزانه-م19بودجه98-020322 | اخزا819 | expired |
| `3019817952865782` | اسنادخزانه-م21بودجه98-020906 | اخزا821 | expired |
| `68458335399886534` | اسنادخزانه-م3بودجه99-011110 | اخزا903 | expired |
| `3641651712782169` | اسنادخزانه-م15بودجه99-021118 | اخزا915 | expired |

**19 active + 21 expired = 40 total** instruments found via the `اخزا` search query.

---

## 5. Pipeline Algorithm

```
for each akhza instrument:
    fetch instrument info       → store metadata in PostgreSQL
    for each trading day:
        fetch BestLimits        → store in ClickHouse
        (future) fetch closing price → store in ClickHouse
```

---

## 6. API Base URL

All data endpoints live under:

```
https://cdn.tsetmc.com/api/
```

The consumer-facing SPA at `https://www.tsetmc.com/instInfo/{insCode}` is JavaScript-rendered and **not suitable** for programmatic data retrieval. Always use `cdn.tsetmc.com` directly.