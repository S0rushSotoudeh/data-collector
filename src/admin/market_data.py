import json
from datetime import date
from typing import Any
from urllib.parse import urlencode

from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _PAGE_SIZE, _error_response, _render
from src.admin._views import ClickHouseListView
from src.db.clickhouse import price_to_storage
from src.db.clickhouse.market_data import latest_market_date, market_data_page


def _parse_cursor(raw: str) -> tuple[int, str, int]:
    try:
        if len(raw) > 1024:
            raise ValueError
        value = json.loads(raw)
        if (
            not isinstance(value, list) or len(value) != 3
            or type(value[0]) is not int or not 0 <= value[0] < 2**32
            or not isinstance(value[1], str) or len(value[1]) > 256
            or type(value[2]) is not int or not 0 <= value[2] < 2**64
        ):
            raise ValueError
        return tuple(value)
    except (ValueError, TypeError):
        raise ValueError("Invalid page link. Reset the filters and try again.") from None


class MarketDataListView(ClickHouseListView):
    table_name: str

    @staticmethod
    def resolve_instrument_code(raw: str) -> str | None:
        return raw.strip() or None

    async def fetch_rows(self, filters, cursor=None, backwards=False):
        query_filters = dict(filters)
        query_filters["instrument_code"] = self.resolve_instrument_code(filters["instrument_code"])
        query_filters["trade_date"] = date.fromisoformat(filters["trade_date"])
        query_filters["data_source"] = filters["data_source"] or None
        for field in ("min_price", "max_price"):
            if field in query_filters:
                raw = query_filters[field]
                query_filters[field] = price_to_storage(raw) if raw else None
        return await market_data_page(
            self.table_name, query_filters, cursor, backwards, _PAGE_SIZE + 1,
        )

    async def _list(self, request: Request) -> HTMLResponse:
        qp = dict(request.query_params)
        backwards = bool(qp.get("before"))
        cursor = None
        try:
            if qp.get("before") and qp.get("after"):
                raise ValueError("Use only one page direction.")
            raw_cursor = qp.get("before") or qp.get("after")
            if raw_cursor:
                cursor = _parse_cursor(raw_cursor)
                if not qp.get("trade_date"):
                    raise ValueError("A page link must include its trade date.")
            if qp.get("trade_date"):
                try:
                    date.fromisoformat(qp["trade_date"])
                except ValueError:
                    raise ValueError("Enter a valid trade date (YYYY-MM-DD).") from None
            else:
                latest = await latest_market_date(self.table_name)
                qp["trade_date"] = latest.isoformat() if latest else ""
            filters = self.parse_filters(qp)
            rows = await self.fetch_rows(filters, cursor, backwards) if qp["trade_date"] else []
        except ValueError as exc:
            response = _error_response(exc)
            response.status_code = 400
            return response
        except Exception as exc:
            return _error_response(exc)

        has_more = len(rows) > _PAGE_SIZE
        rows = rows[:_PAGE_SIZE]
        if backwards:
            rows.reverse()
        has_prev = has_more if backwards else cursor is not None
        has_next = cursor is not None if backwards else has_more
        # Keep the resolved date in every link so pagination cannot cross sessions.
        link_params = {k: v for k, v in qp.items() if k not in ("page", "before", "after")}

        def page_url(direction: str, row: dict[str, Any]) -> str:
            row_id = "depth_level" if "depth_level" in row else "trade_id"
            token = json.dumps([row["trade_time"], row["instrument_code"], row[row_id]])
            return "?" + urlencode({**link_params, direction: token})

        ctx = {
            "request": request,
            "admin": self._admin_ref,
            "title": self.page_title,
            "subtitle": self.page_subtitle,
            "rows": rows,
            "prev_url": page_url("before", rows[0]) if rows and has_prev else None,
            "next_url": page_url("after", rows[-1]) if rows and has_next else None,
            "first_url": "?" + urlencode(link_params),
            "url_for": lambda n, **kw: request.url_for(n, **kw),
            **filters,
        }
        return HTMLResponse(_render(self.template_name, ctx))
