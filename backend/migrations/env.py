from alembic import context
from app import models, profile_models  # noqa: F401
from app.ai import models as ai_models  # noqa: F401
from app.collection import models as collection_models  # noqa: F401
from app.config import get_settings
from app.db import Base
from app.notifications import models as notification_models  # noqa: F401
from sqlalchemy import create_engine, pool


def include_name(name, type_, parent_names):
    return not (type_ == "table" and name.startswith("procrastinate_"))


if context.is_offline_mode():
    context.configure(
        url=get_settings().sqlalchemy_url(),
        target_metadata=Base.metadata,
        literal_binds=True,
        include_name=include_name,
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
        context.configure(
            connection=connection, target_metadata=Base.metadata, include_name=include_name
        )
        with context.begin_transaction():
            context.run_migrations()
