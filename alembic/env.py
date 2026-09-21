import os
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

# Alembic komutları bot'un Telegram/SMTP davranışını kullanmaz ama database.py
# config.py'yi import ettiği için TELEGRAM_BOT_TOKEN yine de tanımlı olmalı.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "alembic-tooling-placeholder")

if os.environ.get("DATABASE_URL"):
    os.environ.setdefault("_ALEMBIC_DATABASE_URL", os.environ["DATABASE_URL"])

from database import Base  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Gerçek veritabanı adresi commit edilen alembic.ini'ye yazılmaz; her zaman
# DATABASE_URL environment değişkeninden okunur (bkz. ADR-006). URL, Config'in
# ConfigParser'ına hiç yazılmaz: `set_main_option`/`get_section` yolu
# ConfigParser'ın `%` interpolation'ından geçtiği için parolasında `%`
# (percent-encoded karakter) geçen geçerli bir URL burada patlar. Bunun yerine
# aşağıdaki fonksiyonlar `database_url`'i doğrudan kullanır.
database_url = os.environ.get("_ALEMBIC_DATABASE_URL")

# Interpret the config file for Python logging.
# This line sets up loggers basically. disable_existing_loggers=False,
# yoksa aynı süreçte alembic'ten sonra çalışan testlerin logging/caplog
# handler'ları da devre dışı kalıyor (ör. pytest caplog).
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = database_url or config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    url = database_url or config.get_main_option("sqlalchemy.url")
    connectable = create_engine(url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
