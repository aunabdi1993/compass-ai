"""Entry point: `uvicorn compass.server:app`. Loads .env, then builds the real app."""

import logging

from compass.api import create_app
from compass.config import load_dotenv_file, load_settings

logging.basicConfig(level=logging.INFO)
load_dotenv_file()
app = create_app(load_settings())
