"""
rag/ingest.py
-------------
Loads the CWE Top 25 corpus, splits each entry into focused chunks,
embeds them using OpenAI text-embedding-3-small, and stores everything
in a local ChromaDB vector database.

Run once before using the RAG retriever. Re-running is safe — it skips
if the collection already exists. Pass force=True to recreate from scratch.
"""

import json
import os
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from dotenv import load_dotenv

load_dotenv()

# ── Paths and constants ────────────────────────────────────────────────────────

CORPUS_PATH = Path("rag/cwe_corpus/cwe_top25.json")
CHROMA_PATH = Path("chroma_db")
COLLECTION_NAME = "cwe_top25"
EMBEDDING_MODEL = "text-embedding-3-small"

# ── Embedding function ─────────────────────────────────────────────────────────

def get_embedding_function() -> OpenAIEmbeddingFunction:
    """
    Returns the OpenAI embedding function that ChromaDB will use to
    convert text into vectors.

    We use text-embedding-3-small because it is fast, cheap, and accurate
    enough for a 25-entry corpus. The same model must be used at ingest
    time and at retrieval time — mixing models breaks similarity search.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set.")
    return OpenAIEmbeddingFunction(
        api_key=api_key,
        model_name=EMBEDDING_MODEL,
    )

# ── Chunking ───────────────────────────────────────────────────────────────────

def chunk_entry(entry: dict) -> list[dict]:
    """
    Converts one CWE entry into three focused chunks.

    Why three chunks instead of one?
    If we stored the entire entry as one chunk, a query about mitigations
    would retrieve the chunk but most of its content would be about the
    description and examples — not what the agent needs. Three focused
    chunks give the retriever more precise targets.

    Returns a list of dicts, each with:
      - 'id':       unique string identifier for this chunk
      - 'text':     the text that gets embedded and stored
      - 'metadata': tags used for filtering before vector search
    """
    cwe_id    = entry["id"]
    rank      = entry["rank"]
    name      = entry["name"]
    short_name = entry["short_name"]
    severity  = entry["severity"]
    domain    = entry["domain"]
    score     = entry["score"]

    # Metadata is stored alongside every chunk in ChromaDB.
    # The retriever uses domain and severity to filter before searching,
    # so the vector search only compares against relevant entries.
    base_metadata = {
        "cwe_id":     cwe_id,
        "rank":       rank,
        "score":      score,
        "short_name": short_name,
        "severity":   severity,
        "domain":     domain,
    }

    chunks = []

    # ── Chunk 1: Core description ──────────────────────────────────────────────
    # This chunk answers "what is this weakness and why does it matter?"
    # It is the primary chunk that the Threat Modeller uses to understand
    # a risk before writing threats into the structured output.
    main_text = (
        f"{cwe_id} (Rank {rank}/25): {name}\n"
        f"Domain: {domain} | Severity: {severity} | MITRE Score: {score}\n\n"
        f"{entry['description']}\n\n"
        f"{entry['extended_description']}"
    )
    chunks.append({
        "id":       f"{cwe_id}_main",
        "text":     main_text,
        "metadata": {**base_metadata, "chunk_type": "main"},
    })

    # ── Chunk 2: Mitigations ───────────────────────────────────────────────────
    # This chunk answers "how do I prevent this weakness?"
    # The Code Generator and Verifier use mitigations to understand what
    # secure code should look like for a given CWE.
    mitigations_text = (
        f"{cwe_id}: {short_name} — Mitigations and Prevention\n\n"
        + "\n".join(f"- {m}" for m in entry["mitigations"])
    )
    chunks.append({
        "id":       f"{cwe_id}_mitigations",
        "text":     mitigations_text,
        "metadata": {**base_metadata, "chunk_type": "mitigations"},
    })

    # ── Chunk 3: Examples ──────────────────────────────────────────────────────
    # This chunk answers "what does vulnerable code look like in practice?"
    # The Verifier uses examples to recognise vulnerable patterns in the
    # generated code when checking against the threat model.
    examples_text = (
        f"{cwe_id}: {short_name} — Vulnerable Code Scenarios\n\n"
        + "\n".join(f"- {e}" for e in entry["examples"])
    )
    chunks.append({
        "id":       f"{cwe_id}_examples",
        "text":     examples_text,
        "metadata": {**base_metadata, "chunk_type": "examples"},
    })

    return chunks

# ── Main ingest function ───────────────────────────────────────────────────────

def ingest(force: bool = False) -> int:
    """
    Runs the full ingestion pipeline: load → chunk → embed → store.

    Parameters
    ----------
    force : bool
        If False (default), skips ingestion if the collection already
        exists with data. If True, deletes the existing collection and
        rebuilds from scratch. Use force=True after updating the corpus.

    Returns
    -------
    int
        The total number of chunks stored in ChromaDB.
    """

    # Step 1: Load the CWE corpus from disk.
    # The corpus is the source of truth — all 25 entries with their full
    # descriptions, mitigations, and examples.
    if not CORPUS_PATH.exists():
        raise FileNotFoundError(
            f"Corpus not found at {CORPUS_PATH}. "
            "Make sure rag/cwe_corpus/cwe_top25.json exists."
        )
    with open(CORPUS_PATH, encoding="utf-8") as f:
        corpus = json.load(f)

    entries = corpus["entries"]
    print(f"Loaded {len(entries)} CWE entries (year: {corpus['metadata']['year']})")

    # Step 2: Connect to ChromaDB.
    # PersistentClient stores the vector database on disk at CHROMA_PATH.
    # This means the vectors survive between runs — we only embed once.
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))

    # Step 3: Handle existing collection.
    # Check if we have already run ingestion before.
    existing_names = [c.name for c in client.list_collections()]

    if COLLECTION_NAME in existing_names:
        if force:
            # Delete and start fresh.
            client.delete_collection(COLLECTION_NAME)
            print(f"Deleted existing collection '{COLLECTION_NAME}' (force=True)")
        else:
            # Reuse existing collection — no need to re-embed.
            collection = client.get_collection(
                name=COLLECTION_NAME,
                embedding_function=get_embedding_function(),
            )
            count = collection.count()
            if count > 0:
                print(
                    f"Collection '{COLLECTION_NAME}' already exists "
                    f"with {count} chunks. Skipping ingestion."
                )
                print("Run ingest(force=True) to rebuild from scratch.")
                return count

    # Step 4: Create a fresh collection.
    # hnsw:space=cosine tells ChromaDB to measure similarity using cosine
    # distance, which works better for text embeddings than Euclidean distance.
    embedding_fn = get_embedding_function()
    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )
    print(f"Created ChromaDB collection '{COLLECTION_NAME}'")

    # Step 5: Chunk every entry.
    # Each of the 25 entries produces 3 chunks = 75 chunks total.
    all_chunks = []
    for entry in entries:
        all_chunks.extend(chunk_entry(entry))

    print(f"Produced {len(all_chunks)} chunks from {len(entries)} entries")

    # Step 6: Embed and store.
    # ChromaDB calls the embedding function automatically when we pass
    # documents to collection.add(). Each document text gets converted to
    # a vector and stored alongside its metadata.
    ids       = [c["id"]       for c in all_chunks]
    texts     = [c["text"]     for c in all_chunks]
    metadatas = [c["metadata"] for c in all_chunks]

    print(f"Embedding {len(texts)} chunks with {EMBEDDING_MODEL}...")
    collection.add(
        ids=ids,
        documents=texts,
        metadatas=metadatas,
    )

    total = collection.count()
    print(f"Ingestion complete. {total} chunks stored in '{CHROMA_PATH}/'")
    return total


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    if force:
        print("Force mode: will delete and recreate the collection.")
    ingest(force=force)
