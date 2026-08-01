# Build the FastAPI backend.
#
# ChromaDB is baked into the image at build time.
# Before running docker build, ingest the CWE corpus locally:
#
#   cd backend
#   python -m rag.ingest
#
# This creates backend/chroma_db/ which is then copied into the image.
# The chroma_db directory is git-ignored, so it must exist on disk when
# you build — it is not recreated inside the container.

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed by some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies before copying source so this layer
# is cached across code-only changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend source.
# This includes backend/chroma_db/ if you ran rag.ingest locally first.
COPY backend/ ./backend/
COPY data/ ./data/

# Work from the backend directory so relative paths (chroma_db/, rag/)
# resolve correctly — this matches the documented run commands.
WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
