"""MySQL connection (SQLAlchemy + PyMySQL). Credentials come from environment variables / .env."""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker


def load_env_file():
    """Tiny .env reader (avoids an extra dependency). Real environment variables win."""
    path = Path(__file__).parent / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


load_env_file()
DB_NAME = os.getenv("DB_NAME", "network_simulation")


def db_url(with_database=True):
    return URL.create("mysql+pymysql", username=os.getenv("DB_USER", "root"),
                      password=os.getenv("DB_PASSWORD", ""), host=os.getenv("DB_HOST", "localhost"),
                      port=int(os.getenv("DB_PORT", "3306")),
                      database=DB_NAME if with_database else None)


Base = declarative_base()
engine = create_engine(db_url(), pool_pre_ping=True, connect_args={"connect_timeout": 5})
SessionLocal = sessionmaker(bind=engine, autoflush=False)
