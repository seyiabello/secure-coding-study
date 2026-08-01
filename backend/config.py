"""
config.py
---------
Shared configuration for all agents (baseline and multi-agent).

Exports:
  client   — OpenAI client (langfuse.openai drop-in when keys are present)
  MODEL    — model name string
  TEMPERATURE — shared temperature (0.2)
  langfuse — Langfuse singleton for scoring/flushing (None if not configured)

Import these rather than instantiating OpenAI or Langfuse inside agent files.
"""

import os
from dotenv import load_dotenv

load_dotenv()

MODEL = "gpt-4o"
TEMPERATURE = 0.2

_api_key = os.environ.get("OPENAI_API_KEY")
if not _api_key:
    raise EnvironmentError(
        "OPENAI_API_KEY is not set. Add it to your .env file before running."
    )

# When Langfuse keys are present, swap in the drop-in wrapper so every
# client.chat.completions.create() call is automatically traced (latency,
# tokens, cost, input/output) without any other code changes.
_langfuse_configured = bool(
    os.environ.get("LANGFUSE_PUBLIC_KEY") and
    os.environ.get("LANGFUSE_SECRET_KEY")
)

if _langfuse_configured:
    try:
        from langfuse.openai import OpenAI
    except ImportError:
        from openai import OpenAI
        _langfuse_configured = False
else:
    from openai import OpenAI

client = OpenAI(api_key=_api_key)

# Langfuse singleton — used for scoring and explicit flush at session end.
# get_client() returns the module-level singleton; safe to call multiple times.
langfuse = None
if _langfuse_configured:
    try:
        from langfuse import get_client
        langfuse = get_client()
    except Exception:
        pass
