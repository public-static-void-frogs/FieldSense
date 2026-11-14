from alembic import context

from app.core.config import Settings
from app.core.database import Base, database_engine
from app.repositories import fields, maps, users  # noqa: F401

target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(
        url=Settings().database_url, target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = database_engine(Settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
