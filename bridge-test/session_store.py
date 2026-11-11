"""Private, atomic storage of browser cookies/state; never stores a password."""
import json
import os
from pathlib import Path
import tempfile


class SessionStore:
    def __init__(self, directory=None):
        self.directory = Path(directory or os.environ.get('BRIDGE_STATE_DIR') or
                              Path.home() / '.local/state/aitu-bridge')
        self.path = self.directory / 'session.json'

    def load(self):
        try:
            state = json.loads(self.path.read_text())
            if isinstance(state, dict) and isinstance(state.get('cookies'), list) and isinstance(state.get('origins'), list):
                return state
        except (OSError, ValueError):
            pass
        return None

    async def save(self, context):
        state = await context.storage_state(indexed_db=True)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        fd, filename = tempfile.mkstemp(prefix='.session-', dir=self.directory)
        try:
            with os.fdopen(fd, 'w') as file:
                json.dump(state, file)
                file.flush()
                os.fsync(file.fileno())
            os.replace(filename, self.path)
        finally:
            Path(filename).unlink(missing_ok=True)

    def clear(self):
        self.path.unlink(missing_ok=True)
