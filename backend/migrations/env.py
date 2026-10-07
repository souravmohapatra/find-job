from alembic import context
from app import models, profile_models  # noqa: F401
from app.config import get_settings
from app.db import Base
from sqlalchemy import create_engine, pool

if context.is_offline_mode():
    context.configure(
        url=get_settings().sqlalchemy_url(), target_metadata=Base.metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(
        get_settings().sqlalchemy_url(),
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": 10},
        hide_parameters=True,
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
