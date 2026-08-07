import urllib.parse

from src.config import env


def get_database_url() -> str:
    user = env("POSTGRES_USER")
    password = env("POSTGRES_PASSWORD")
    host = env("POSTGRES_HOST")
    port = env("POSTGRES_PORT")
    db = env("POSTGRES_DB")
    return (
        f"postgresql+psycopg2://{user}:{urllib.parse.quote(password, safe='')}"
        f"@{host}:{port}/{db}"
    )
