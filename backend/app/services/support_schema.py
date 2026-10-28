"""Back up existing SQLite databases before introducing support credential schema."""
from datetime import datetime
from contextlib import closing
from pathlib import Path
import sqlite3
from sqlalchemy import inspect


def backup_before_support_schema(engine):
    if engine.dialect.name != 'sqlite' or not engine.url.database or engine.url.database == ':memory:':
        return
    path = Path(engine.url.database).resolve()
    if not path.exists() or not inspect(engine).has_table('warranty_tickets') or inspect(engine).has_table('ticket_lookup_credentials'):
        return
    folder = path.parent / 'backup'
    folder.mkdir(exist_ok=True)
    target = folder / (path.name + '.before_support_' + datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f') + '.bak')
    # SQLite's online backup API also includes committed WAL pages.
    with closing(sqlite3.connect(str(path))) as source, closing(sqlite3.connect(str(target))) as dest:
        with dest:
            source.backup(dest)
