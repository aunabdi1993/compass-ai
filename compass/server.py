"""Entry point: `uvicorn compass.server:app`. Loads .env, then builds the real app."""

import logging
from pathlib import Path

from compass.api import create_app
from compass.config import load_dotenv_file, load_settings

log = logging.getLogger("compass")
logging.basicConfig(level=logging.INFO)

# Look next to the code (the project folder) first, so it works whichever folder uvicorn is started from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
for candidate in (PROJECT_ROOT / ".env", Path.cwd() / ".env"):
    if candidate.is_file():
        log.info("Loading settings from %s", candidate)
        load_dotenv_file(candidate)
        break
else:
    log.warning("No .env file found in %s (or the current folder). Using environment variables only.", PROJECT_ROOT)

app = create_app(load_settings())
