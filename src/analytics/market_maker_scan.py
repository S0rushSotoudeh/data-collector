"""Concise market-wide option route scanner."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from src.analytics.market_maker_quote import QuoteError, _parse_datetime, scan_market


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rank profitable option parity and box routes")
    parser.add_argument("time", help="ISO Tehran datetime")
    parser.add_argument("--side", choices=("buy", "sell", "both"), default="both")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--max-book-age", type=float, default=300)
    parser.add_argument("--max-cross-leg-skew", type=float, default=120)
    parser.add_argument("--max-spread-percent", type=float, default=20)
    parser.add_argument("--include-direct", action="store_true")
    parser.add_argument("--include-behind-market", action="store_true")
    try:
        args = parser.parse_args(argv)
        sides = ("buy", "sell") if args.side == "both" else (args.side,)
        scan = scan_market(
            _parse_datetime(args.time), sides, limit=args.limit,
            competitive_only=not args.include_behind_market,
            exclude_direct=not args.include_direct,
            max_book_age_seconds=args.max_book_age,
            max_cross_leg_skew_seconds=args.max_cross_leg_skew,
            max_spread_percent=args.max_spread_percent,
        )
    except (QuoteError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except Exception as exc:
        print(json.dumps({"error": f"scan failed: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 1

    opportunities = [{
        "option_instrument_code": item["option_instrument_code"],
        "symbol": item["symbol"],
        "side": item["side"],
        "action": item["action"],
        "path": item["path"],
        "execution_price": item["execution_price"],
        "calculated_limit_price": item["price"],
        "profit_headroom": item["profit_headroom_at_execution"],
        "profit_headroom_percent": item["execution_headroom_percent"],
        "best_bid": item["best_bid"],
        "best_ask": item["best_ask"],
        "max_quantity": item["max_quantity"],
        "expiry": item["expiry"],
    } for item in scan["results"]]
    output = {
        "at": scan["at"],
        "targets_scanned": scan["targets_scanned"],
        "routes_evaluated": scan["routes_evaluated"],
        "profitable_candidates": scan["competitive_candidates"],
        "filters": scan["filters"],
        "opportunities": opportunities,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
