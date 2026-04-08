"""
Database connection helpers.
"""
import os
import ssl

from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()


def build_engine(host: str, port: int, name: str, user: str, password: str):
    """Create a SQLAlchemy engine from explicit credentials."""
    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}"
    if host == "localhost":
        return create_engine(url, connect_args={"ssl_disabled": True})
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return create_engine(url, connect_args={"ssl": ctx})


def get_engine():
    """Read credentials from .env and return a SQLAlchemy engine."""
    return build_engine(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        name=os.getenv("DB_NAME", "ReportingSystemDB"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
    )
