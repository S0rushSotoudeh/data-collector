import asyncio
import secrets
from hmac import compare_digest
from typing import Any

from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _parse_date, _render
from src.admin._views import ClickHouseListView
from src.collectors.parsian_stream import (
    credential_status, encryption_key_configured, normalize_token, save_credential, stream_status,
    validate_live_token,
)
from src.db.clickhouse.deposit_certificates import paginated


class DepositCertificateOrderBookView(ClickHouseListView):
    template_name = "gold/deposit_certificate_order_book.html"
    page_title = "Deposit Certificate Order Book"
    page_subtitle = "Changed top-three levels from the Parsian live feed"
    name = "Certificate Order Book"
    identity = "deposit-certificate-order-book"
    icon = "fa-solid fa-layer-group"
    category = "Gold Market"
    category_icon = "fa-solid fa-coins"

    def parse_filters(self, qp: dict[str, str]) -> dict[str, Any]:
        symbol = qp.get("symbol", "")
        return {"symbol": symbol if symbol in {"GOLDBAR", "GOLDCOIN"} else "", "trade_date": qp.get("trade_date", "")}

    async def fetch(self, filters, offset, limit):
        raw_date = filters["trade_date"]
        return await paginated(filters["symbol"] or None, _parse_date(raw_date) if raw_date else None, offset, limit)

    @expose("/deposit-certificate-order-book", methods=["GET"])
    async def list_page(self, request: Request) -> HTMLResponse:
        return await self._list(request)


class ParsianStreamSettingsView(BaseView):
    name = "Parsian Stream Settings"
    identity = "parsian-stream-settings"
    icon = "fa-solid fa-tower-broadcast"
    category = "Operations"
    category_icon = "fa-solid fa-gears"

    @expose("/parsian-stream-settings", methods=["GET", "POST"])
    async def settings(self, request: Request) -> HTMLResponse:
        messages: list[dict[str, str]] = []
        csrf = request.session.setdefault("parsian_csrf", secrets.token_urlsafe(32))
        if request.method == "POST":
            form = await request.form()
            if not compare_digest(str(form.get("csrf_token") or ""), csrf):
                messages.append({"type": "danger", "text": "The form expired. Reload and try again."})
            elif not encryption_key_configured():
                messages.append({
                    "type": "danger",
                    "text": "PARSIAN_TOKEN_ENCRYPTION_KEY is missing or invalid. Add it to .env and recreate the API container.",
                })
            else:
                try:
                    token = normalize_token(str(form.get("token") or ""))
                    await validate_live_token(token)
                    await asyncio.to_thread(save_credential, token)
                    messages.append({"type": "success", "text": "Token validated against both certificates and saved."})
                except ValueError as exc:
                    messages.append({"type": "danger", "text": str(exc)})
                except RuntimeError as exc:
                    messages.append({"type": "danger", "text": str(exc)})
                except Exception as exc:
                    messages.append({"type": "danger", "text": f"Token was not replaced ({type(exc).__name__})."})
        try:
            credential, status = await asyncio.gather(asyncio.to_thread(credential_status), stream_status())
        except Exception as exc:
            credential, status = {"configured": False}, {"error": type(exc).__name__}
        ctx = {
            "request": request, "admin": self._admin_ref, "title": "Parsian Stream Settings",
            "subtitle": "Write-only credential replacement and pipeline health", "messages": messages,
            "credential": credential, "status": status, "csrf_token": csrf,
            "url_for": lambda name, **params: request.url_for(name, **params),
        }
        return HTMLResponse(_render("operations/parsian_stream_settings.html", ctx))
