import httpx
import json
import os
from datetime import datetime, timedelta

BASE = os.environ["TSETMC_CDN_BASE_URL"]
HEADERS = {"User-Agent": os.environ["TSETMC_USER_AGENT"]}

def get_akhza_instruments():
    url = f"{BASE}/Instrument/GetInstrumentSearch/%D8%A7%D8%AE%D8%B2%D8%A7"
    resp = httpx.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()["instrumentSearch"]

def get_instrument_info(ins_code: str):
    url = f"{BASE}/Instrument/GetInstrumentInfo/{ins_code}"
    resp = httpx.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()["instrumentInfo"]

def get_best_limits(ins_code: str, date_yyyymmdd: str):
    url = f"{BASE}/BestLimits/{ins_code}/{date_yyyymmdd}"
    resp = httpx.get(url, headers=HEADERS, timeout=15)
    if "text/html" in resp.headers.get("content-type", "") or not resp.text.strip():
        return None
    resp.raise_for_status()
    return resp.json().get("bestLimitsHistory", [])

def get_trade_history(ins_code: str, date_yyyymmdd: str):
    url = f"{BASE}/Trade/GetTradeHistory/{ins_code}/{date_yyyymmdd}/true"
    resp = httpx.get(url, headers=HEADERS, timeout=15)
    if "text/html" in resp.headers.get("content-type", "") or not resp.text.strip():
        return None
    resp.raise_for_status()
    return resp.json().get("tradeHistory", [])

def get_closing_price(ins_code: str):
    url = f"{BASE}/ClosingPrice/GetClosingPriceHistory/{ins_code}"
    resp = httpx.get(url, headers=HEADERS, timeout=15)
    if "text/html" in resp.headers.get("content-type", "") or not resp.text.strip():
        return None
    resp.raise_for_status()
    return resp.json()

def main():
    akhzas = get_akhza_instruments()
    active = [a for a in akhzas if a.get("lastDate") == 1]
    expired = [a for a in akhzas if a.get("lastDate") != 1]

    print(f"Active: {len(active)}  |  Expired: {len(expired)}  |  Total: {len(akhzas)}\n")

    print(f"{'insCode':>20}  {'ShortCode':<10}  {'Status':<8}  Name")
    print("-" * 100)
    for a in akhzas:
        status = "active" if a.get("lastDate") == 1 else "expired"
        print(f"{a['insCode']:>20}  {a.get('lVal18AFC',''):<10}  {status:<8}  {a['lVal30']}")

    print()

    first_active = active[0]
    ins_code = first_active["insCode"]
    name = first_active["lVal30"]
    short = first_active.get("lVal18AFC", "")
    print(f"--- Instrument Info: {short} ({name}) ---")
    info = get_instrument_info(ins_code)
    print(f"  ISIN:        {info.get('cIsin')}")
    print(f"  lVal18:      {info.get('lVal18')}")
    print(f"  zTitad:      {info.get('zTitad')}")
    print(f"  baseVol:     {info.get('baseVol')}")
    print(f"  flow:        {info.get('flow')} ({info.get('flowTitle')})")
    print(f"  market:      {info.get('cgrValCot')} ({info.get('cgrValCotTitle')})")
    print(f"  secVal:      {info.get('cSecVal')} ({info.get('lSecVal')})")
    print(f"  dEven:       {info.get('dEven')}")
    print(f"  price range: [{info['staticThreshold']['psGelStaMin']}, {info['staticThreshold']['psGelStaMax']}]")
    print(f"  5Y avg vol:  {info.get('qTotTran5JAvg')}")
    print()

    today = datetime.now()
    # Iran working days: Sat-Wed. Try last 10 days, pick those not Thu/Fri
    working = []
    for d in range(14):
        dt = today - timedelta(days=d)
        if dt.weekday() not in (4, 5):  # not Fri(4), Thu(5)
            working.append(dt)
        if len(working) == 5:
            break
    dates = [d.strftime("%Y%m%d") for d in working]

    for dt_str in dates:
        limits = get_best_limits(ins_code, dt_str)
        if limits:
            print(f"--- Best Limits for {short} on {dt_str} ---")
            print(f"  {'#':<3} {'Time':<8} {'BidPrice':<12} {'BidQty':<8} {'BidOrd':<6} {'AskPrice':<12} {'AskQty':<8} {'AskOrd':<6}")
            for lim in limits:
                h = str(lim['hEven']).zfill(6)
                t = f"{h[:2]}:{h[2:4]}:{h[4:]}"
                print(f"  {lim['number']:<3} {t:<8} {lim['pMeDem']:<12.0f} {lim['qTitMeDem']:<8} {lim['zOrdMeDem']:<6} {lim['pMeOf']:<12.0f} {lim['qTitMeOf']:<8} {lim['zOrdMeOf']:<6}")
            break
    else:
        print("(no best limits data for recent working days)")

    for dt_str in dates:
        trades = get_trade_history(ins_code, dt_str)
        if trades:
            print(f"\n--- TradeHistory for {short} on {dt_str} ---")
            print(f"  {'Time':<8} {'Seq':<5} {'Volume':<8} {'Price':<14} {'Canceled':<8}")
            for t in trades:
                h = str(t['hEven']).zfill(6)
                tstr = f"{h[:2]}:{h[2:4]}:{h[4:]}"
                print(f"  {tstr:<8} {t['nTran']:<5} {t['qTitTran']:<8} {t['pTran']:<14.0f} {t['canceled']:<8}")
            break
    else:
        print("\n(no trade data for recent working days)")

    print()
    print("--- Test: ClosingPrice History ---")
    cp = get_closing_price(ins_code)
    if cp is None:
        print("  (access blocked)")
    else:
        print(f"  {json.dumps(cp, ensure_ascii=False)[:500]}")

if __name__ == "__main__":
    main()
