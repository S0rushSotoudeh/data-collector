# Admin Panel Development

All custom `BaseView` pages must use manual `jinja2.Environment` + `_render()` helper.

## Page Types

| Type | Class | Use Case | Example |
|------|-------|----------|---------|
| CRUD | ModelView | CRUD on SQLModel entity | BondInstrumentAdmin |
| Custom | BaseView + _render() | Read-only views, task triggers | BondOrderBookView, CeleryTasksView |

## Template Rendering Pattern

```python
_TEMPLATE_DIR = Path(__file__).parent / "templates"
_SQLADMIN_TEMPLATE_DIR = Path(sqladmin.__file__).parent / "templates"
_TEMPLATE_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader([str(_TEMPLATE_DIR), str(_SQLADMIN_TEMPLATE_DIR)]),
    autoescape=True, auto_reload=False,
)
_TEMPLATE_ENV.globals.update(get_flashed_messages=get_flashed_messages, Secret=Secret, min=min, zip=zip)

def _render(name: str, ctx: dict[str, Any]) -> str:
    return _TEMPLATE_ENV.get_template(name).render(ctx)

class MyView(BaseView):
    name = "My View"; identity = "my-view"; icon = "fa-solid fa-star"

    @expose("/my-view", methods=["GET"])
    async def handler(self, request: Request) -> HTMLResponse:
        ctx: dict[str, Any] = {
            "request": request, "admin": self._admin_ref,  # NOT self.admin
            "url_for": lambda n, **kw: request.url_for(n, **kw),
            "title": "...", "subtitle": "...",
        }
        return HTMLResponse(_render("my_template.html", ctx))
```

## Mandatory Context Keys

| Key | Value | Purpose |
|-----|-------|---------|
| request | request | Required by layout.html |
| admin | **self._admin_ref** | NOT self.admin |
| url_for | lambda wrapping request.url_for | Static files, back link |
| title | str | Page header |
| subtitle | str | Below title |

## Template Inheritance

```
sqladmin/base.html → sqladmin/layout.html → admin_base.html → your_template.html
```

Blocks in admin_base.html: title, custom_styles, content, custom_js.

Template has access to: `{{ url_for('admin:index') }}`, `{{ url_for('admin:statics', path='...') }}`, `{{ admin.title }}`, `{{ request }}`.

## How to Add

1. Create BaseView subclass with @expose("/path") in src/admin/
2. Create Jinja2 template in src/admin/templates/ extending admin_base.html
3. Register in src/admin/__init__.py
4. Verify: `docker compose restart api` → `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/admin/my-view --user admin:admin` (expect 200)

## File Structure

```
src/admin/
├── __init__.py           # Register all views
├── auth.py               # BasicAuthBackend
├── bond_views.py         # ModelView (CRUD)
├── clickhouse_views.py   # BondOrderBookView + BondTradesView (BaseView)
├── task_views.py         # CeleryTasksView (BaseView)
└── templates/
    ├── admin_base.html
    ├── order_book_list.html
    ├── trades_list.html
    └── admin_tasks.html
```