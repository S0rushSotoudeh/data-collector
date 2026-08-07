from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from src.config import env


class BasicAuthBackend(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username: str = form.get("username", "")
        password: str = form.get("password", "")
        admin_user = env("ADMIN_USER")
        admin_pass = env("ADMIN_PASSWORD")
        if username == admin_user and password == admin_pass:
            request.session.update({"user": username})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return bool(request.session.get("user"))
