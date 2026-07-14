"""
config.py
---------
Shared configuration for all agents (baseline and multi-agent).

Import `client` and `MODEL` rather than instantiating OpenAI elsewhere.
The client is created once at import time so every agent shares a single
connection pool and the API key is validated on startup.
"""

import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

MODEL = "gpt-4o"
TEMPERATURE = 0.2

_api_key = os.environ.get("OPENAI_API_KEY")
if not _api_key:
    raise EnvironmentError(
        "OPENAI_API_KEY is not set. Add it to your .env file before running."
    )

client = OpenAI(api_key=_api_key)
