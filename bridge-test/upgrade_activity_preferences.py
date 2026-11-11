"""Add the expiring activity preferences table; preserve all existing records."""
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy import text
from maria_storage import MariaStorage, SCHEMAS


def upgrade(storage):
    table = storage.table('bridge', 'hidden_activities')
    columns = storage.qualify('bridge', SCHEMAS['bridge']['hidden_activities'])
    with storage.engine.begin() as db:
        db.execute(text(f'CREATE TABLE IF NOT EXISTS `{table}` ({columns}) '
                        'ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin'))


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    storage = MariaStorage(dotenv_values(root / '.env')['DATABASE_URL'])
    try:
        upgrade(storage)
        print('Activity preferences table is ready; existing data preserved.')
    finally:
        storage.engine.dispose()
