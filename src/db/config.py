import os

import urllib.parse


def get_database_url() -> str:
    user = os.getenv("POSTGRES_USER", "dc_user")
    password = os.getenv("POSTGRES_PASSWORD", "dc_pass")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "dc_metadata")
    return (
        f"postgresql+psycopg2://{user}:{urllib.parse.quote(password, safe='')}"
        f"@{host}:{port}/{db}"
    )