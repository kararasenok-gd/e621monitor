import configparser
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.orm import DeclarativeBase
from loguru import logger


# ---------- Base ----------
class Base(DeclarativeBase):
    pass


# ---------- config ----------
def load_config(path="config.ini"):
    cfg = configparser.ConfigParser()
    cfg.read(path)
    return cfg


def build_db_url(cfg):
    driver = cfg["database"]["driver"]

    if driver == "sqlite":
        return f"sqlite+aiosqlite:///{cfg['database']['sqlite_path']}"

    if driver == "postgres":
        return (
            f"postgresql+asyncpg://"
            f"{cfg['database']['pg_user']}:{cfg['database']['pg_password']}"
            f"@{cfg['database']['pg_host']}:{cfg['database']['pg_port']}"
            f"/{cfg['database']['pg_db']}"
        )

    if driver == "mysql":
        return (
            f"mysql+aiomysql://"
            f"{cfg['database']['mysql_user']}:{cfg['database']['mysql_password']}"
            f"@{cfg['database']['mysql_host']}:{cfg['database']['mysql_port']}"
            f"/{cfg['database']['mysql_db']}"
        )

    raise ValueError(f"Unknown driver: {driver}")


# ---------- init ----------
def init_db(config_path="config.ini"):
    cfg = load_config(config_path)
    url = build_db_url(cfg)

    engine = create_async_engine(
        url,
        echo=cfg.getboolean("bot", "debug", fallback=False),
        future=True,
    )

    SessionLocal = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    return engine, SessionLocal, cfg


def _sync_schema(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue

        existing_cols = {col["name"] for col in inspector.get_columns(table.name)}
        for col in table.columns.values():
            if col.name in existing_cols:
                continue

            col_type = col.type.compile(conn.dialect)

            default_clause = ""
            if col.default is not None and hasattr(col.default, "arg") and not callable(col.default.arg):
                val = col.default.arg
                if isinstance(val, str):
                    default_clause = f" DEFAULT '{val}'"
                elif isinstance(val, bool):
                    default_clause = f" DEFAULT {int(val)}"
                else:
                    default_clause = f" DEFAULT {val}"
            elif col.nullable:
                default_clause = " DEFAULT NULL"

            conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}{default_clause}"))
            logger.debug(f"Added column: {table.name}.{col.name}")


async def init_models(engine):
    import importlib
    from pathlib import Path

    models_dir = Path(__file__).parent.parent / "models"
    for path in sorted(models_dir.glob("*.py")):
        if path.stem != "__init__":
            importlib.import_module(f"models.{path.stem}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_sync_schema)