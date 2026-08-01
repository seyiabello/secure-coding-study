"""
rag/retriever.py
----------------
Advanced RAG retrieval pipeline for the CWE Top 25 corpus.

Pipeline:
  1. Query rewrite: GPT-4o expands the task into security search terms
                      and identifies relevant CWE domains
  2. Metadata filter: restrict ChromaDB search to relevant domains only
  3. Similarity search: top-10 results by cosine similarity
  4. LLM re-rank: GPT-4o selects the top-3 most relevant chunks
  5. Return: structured list ready for injection into agent prompts

Used by: Threat Modeller and Verifier agents only.
"""

import json
import os
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from dotenv import load_dotenv

from config import client as openai_client, MODEL, TEMPERATURE

load_dotenv()

# ── Constants ──────────────────────────────────────────────────────────────────

CHROMA_PATH      = Path("chroma_db")
COLLECTION_NAME  = "cwe_top25"
EMBEDDING_MODEL  = "text-embedding-3-small"
N_SEARCH_RESULTS = 10   # how many chunks to retrieve before re-ranking
N_FINAL_RESULTS  = 3    # how many chunks to return after re-ranking

# All domain values present in the corpus metadata.
# Shown to GPT-4o during query rewrite so it picks from this exact list.
AVAILABLE_DOMAINS = [
    "injection",
    "memory",
    "access_control",
    "input_validation",
    "information_disclosure",
    "network",
    "resource_management",
]

# ── ChromaDB connection ────────────────────────────────────────────────────────

def get_collection() -> chromadb.Collection:
    """
    Opens the ChromaDB collection that was built by ingest.py.

    Raises a clear error if ingest has not been run yet, so the developer
    knows exactly what to do rather than seeing a cryptic ChromaDB error.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set.")

    chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))

    existing = [c.name for c in chroma_client.list_collections()]
    if COLLECTION_NAME not in existing:
        raise RuntimeError(
            f"ChromaDB collection '{COLLECTION_NAME}' not found. "
            "Run `python -m rag.ingest` first to build the vector store."
        )

    embedding_fn = OpenAIEmbeddingFunction(
        api_key=api_key,
        model_name=EMBEDDING_MODEL,
    )
    return chroma_client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
    )

# ── Step 1: Query rewrite ──────────────────────────────────────────────────────

def rewrite_query(task: str) -> tuple[str, list[str]]:
    """
    Uses GPT-4o to expand the task into security-relevant search terms
    and to identify which CWE domains are relevant.

    Why rewrite at all?
    A task like "write a login form" is too generic for a good vector search.
    The rewritten version: "authentication password brute force credential
    validation session management" - matches CWE descriptions much better.

    Returns
    -------
    search_query : str
        Expanded security-focused search string.
    relevant_domains : list[str]
        Subset of AVAILABLE_DOMAINS that apply to this task.
    """
    system_prompt = f"""You are a security analyst assistant.
Given a coding task, you do two things:
1. Rewrite the task as a security-focused search query using relevant
   security terminology. Expand abbreviations. Include attack names,
   vulnerability classes, and prevention concepts.
2. Identify which of the following security domains are relevant to the task.

Available domains: {', '.join(AVAILABLE_DOMAINS)}

Respond with valid JSON only. No other text. Use this exact schema:
{{
  "search_query": "security-focused expanded search terms",
  "relevant_domains": ["domain1", "domain2"]
}}"""

    response = openai_client.chat.completions.create(
        model=MODEL,
        temperature=TEMPERATURE,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Coding task: {task}"},
        ],
    )

    result = json.loads(response.choices[0].message.content)

    # Validate that returned domains are from the known list.
    # If GPT-4o hallucinated a domain name, filter it out silently.
    search_query = result.get("search_query", task)
    relevant_domains = [
        d for d in result.get("relevant_domains", AVAILABLE_DOMAINS)
        if d in AVAILABLE_DOMAINS
    ]

    # Fallback: if no valid domains returned, search across all.
    if not relevant_domains:
        relevant_domains = AVAILABLE_DOMAINS

    return search_query, relevant_domains

# ── Step 2 + 3: Filter and search ─────────────────────────────────────────────

def search(
    collection: chromadb.Collection,
    search_query: str,
    relevant_domains: list[str],
    n_results: int = N_SEARCH_RESULTS,
) -> list[dict]:
    """
    Queries ChromaDB with a metadata filter on domain, then returns
    the top-n results by cosine similarity.

    The metadata filter runs first (fast, no embeddings needed), then
    the vector search runs only against the filtered subset.

    Returns a list of result dicts, each containing:
      - 'id':       chunk identifier (e.g. 'CWE-89_main')
      - 'text':     the chunk text that was embedded
      - 'metadata': the metadata dict (cwe_id, domain, severity, etc.)
      - 'distance': cosine distance from query (lower = more similar)
    """
    # Build the ChromaDB where clause.
    # $in means "domain must be one of these values".
    where_filter = {"domain": {"$in": relevant_domains}}

    results = collection.query(
        query_texts=[search_query],
        n_results=min(n_results, collection.count()),
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )

    # ChromaDB returns nested lists (one list per query).
    # We only sent one query, so we unwrap the first element.
    chunks = []
    for doc, meta, dist, chunk_id in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
        results["ids"][0],
    ):
        chunks.append({
            "id":       chunk_id,
            "text":     doc,
            "metadata": meta,
            "distance": dist,
        })

    return chunks

# ── Step 4: LLM re-rank ────────────────────────────────────────────────────────

def rerank(task: str, candidates: list[dict], n_final: int = N_FINAL_RESULTS) -> list[dict]:
    """
    Uses GPT-4o to select the most relevant chunks from the candidates.

    Why re-rank after vector search?
    Vector similarity finds chunks that are semantically close to the
    search query, but it cannot reason about which are *most important*
    for this specific task. A language model can. It reads each candidate
    and picks the ones that matter most, not just the closest vectors.

    Returns the top-n candidates in order of relevance.
    """
    if len(candidates) <= n_final:
        # Fewer candidates than requested: return all of them.
        return candidates

    # Build a compact summary of each candidate for the prompt.
    # We truncate text to 200 chars to keep the re-rank prompt short.
    candidate_summaries = []
    for i, c in enumerate(candidates):
        meta = c["metadata"]
        preview = c["text"][:200].replace("\n", " ")
        candidate_summaries.append(
            f"[{i}] {meta['cwe_id']} ({meta['short_name']}) "
            f"| domain: {meta['domain']} | chunk: {meta['chunk_type']}\n"
            f"    {preview}..."
        )

    system_prompt = (
        f"You are a security expert. Given a coding task and {len(candidates)} "  # nosec B608
        f"candidate CWE chunks, select the {n_final} most relevant chunks.\n\n"
        "Respond with valid JSON only. No other text. Use this schema:\n"
        f'{{"top_indices": [i, j, k]}} '
        f"where each value is a 0-based index from the candidate list."
    )

    user_message = (
        f"Coding task: {task}\n\n"
        "Candidates:\n" + "\n".join(candidate_summaries)
    )

    response = openai_client.chat.completions.create(
        model=MODEL,
        temperature=TEMPERATURE,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
    )

    result = json.loads(response.choices[0].message.content)
    top_indices = result.get("top_indices", list(range(n_final)))

    # Validate indices are in range. If GPT-4o returns an out-of-range
    # index, fall back to the top-n by distance.
    valid_indices = [i for i in top_indices if 0 <= i < len(candidates)]
    if len(valid_indices) < n_final:
        # Pad with the next best by distance if we got bad indices.
        for i in range(len(candidates)):
            if i not in valid_indices:
                valid_indices.append(i)
            if len(valid_indices) == n_final:
                break

    ranked = [candidates[i] for i in valid_indices[:n_final]]

    # Deduplicate by CWE ID so we return coverage across different weaknesses
    # rather than multiple chunks from the same CWE entry.
    seen_ids = set()
    deduped = []
    for chunk in ranked:
        cwe_id = chunk["metadata"]["cwe_id"]
        if cwe_id not in seen_ids:
            seen_ids.add(cwe_id)
            deduped.append(chunk)

    # If deduplication left us short, pad from remaining candidates.
    if len(deduped) < n_final:
        for chunk in candidates:
            if chunk["metadata"]["cwe_id"] not in seen_ids:
                seen_ids.add(chunk["metadata"]["cwe_id"])
                deduped.append(chunk)
            if len(deduped) == n_final:
                break

    return deduped[:n_final]

# ── Step 5: Format for prompt injection ───────────────────────────────────────

def format_for_prompt(results: list[dict]) -> str:
    """
    Converts retrieval results into a formatted string for injection
    into an agent's system prompt.

    Agents receive this as their security context. The format is chosen
    to be readable both by the LLM and by a human reviewing the prompts.
    """
    if not results:
        return "No relevant CWE entries found."

    lines = ["=== Relevant CWE Security Context ===\n"]
    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        lines.append(
            f"[{i}] {meta['cwe_id']} - {meta['short_name']}\n"
            f"    Rank: {meta['rank']}/25 | Severity: {meta['severity']} "
            f"| Domain: {meta['domain']}\n"
            f"\n{r['text']}\n"
            f"{'-' * 60}"
        )
    return "\n".join(lines)

# ── Full pipeline ──────────────────────────────────────────────────────────────

def retrieve(task: str, n_final: int = N_FINAL_RESULTS) -> list[dict]:
    """
    Runs the complete Advanced RAG pipeline for a given coding task.

    This is the main function agents call. It handles all four steps
    internally and returns the top-n most relevant CWE chunks.

    Parameters
    ----------
    task : str
        The coding task as submitted by the participant.
    n_final : int
        Number of chunks to return after re-ranking (default 3).

    Returns
    -------
    list[dict]
        Top-n chunks, each with 'id', 'text', 'metadata', 'distance'.
    """
    print(f"[RAG] Retrieving for task: {task[:80]}...")

    # Step 1: Expand the task into security search terms.
    search_query, relevant_domains = rewrite_query(task)
    print(f"[RAG] Rewritten query: {search_query[:80]}...")
    print(f"[RAG] Relevant domains: {relevant_domains}")

    # Step 2 + 3: Filter by domain and search.
    collection = get_collection()
    candidates = search(collection, search_query, relevant_domains)
    print(f"[RAG] Vector search returned {len(candidates)} candidates")

    # Step 4: Re-rank with GPT-4o.
    top_chunks = rerank(task, candidates, n_final)
    print(f"[RAG] Re-ranked to top {len(top_chunks)} chunks: "
          f"{[c['metadata']['cwe_id'] for c in top_chunks]}")

    return top_chunks


# ── CLI smoke test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_task = "Write a Python function that accepts a username and password and authenticates against a database"
    print(f"Test task: {test_task}\n")

    results = retrieve(test_task)

    print("\n" + "=" * 60)
    print("RETRIEVAL RESULTS")
    print("=" * 60)
    print(format_for_prompt(results))
