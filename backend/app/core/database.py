from collections.abc import Generator

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings
import app.models  # noqa: F401


settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    ensure_task_text_columns()
    ensure_agent_run_columns()


def ensure_task_text_columns() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("task"):
        return

    dialect = engine.dialect.name
    if dialect == "sqlite":
        return

    with engine.begin() as connection:
        if dialect == "mysql":
            connection.execute(text("ALTER TABLE task MODIFY COLUMN description TEXT NOT NULL"))
        else:
            connection.execute(text("ALTER TABLE task ALTER COLUMN description TYPE TEXT"))

    if not inspector.has_table("taskevent"):
        return
    with engine.begin() as connection:
        if dialect == "mysql":
            connection.execute(text("ALTER TABLE taskevent MODIFY COLUMN message TEXT NULL"))
        else:
            connection.execute(text("ALTER TABLE taskevent ALTER COLUMN message TYPE TEXT"))


def ensure_agent_run_columns() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("agentrun"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("agentrun")}
    column_sql = {
        "agent_session_id": "INTEGER NULL",
        "provider_type": "VARCHAR(80) NOT NULL DEFAULT 'local_cli'",
        "external_thread_id": "VARCHAR(120) NULL",
        "external_turn_id": "VARCHAR(120) NULL",
        "command_display": "VARCHAR(500) NULL",
        "cwd": "VARCHAR(1000) NULL",
        "exit_code": "INTEGER NULL",
        "stderr": "TEXT NULL",
        "created_at": "DATETIME NULL",
    }
    dialect = engine.dialect.name
    missing_columns = [(name, definition) for name, definition in column_sql.items() if name not in existing_columns]
    if missing_columns:
        with engine.begin() as connection:
            for name, definition in missing_columns:
                if dialect == "sqlite":
                    connection.execute(text(f"ALTER TABLE agentrun ADD COLUMN {name} {definition}"))
                else:
                    connection.execute(text(f"ALTER TABLE agentrun ADD COLUMN {name} {definition}"))

    if dialect == "sqlite":
        return

    existing_columns = {column["name"] for column in inspect(engine).get_columns("agentrun")}
    text_columns = ["input_payload", "output_payload", "stderr", "error_message"]
    with engine.begin() as connection:
        for name in text_columns:
            if name not in existing_columns:
                continue
            if dialect == "mysql":
                connection.execute(text(f"ALTER TABLE agentrun MODIFY COLUMN {name} TEXT NULL"))
            else:
                connection.execute(text(f"ALTER TABLE agentrun ALTER COLUMN {name} TYPE TEXT"))


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
