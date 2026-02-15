"""
retriever.py
============
Connects LangChain to the existing ChromaDB (threat_db/, 176K docs).
Provides semantic search across all 6 threat domains.

Usage:
    from retriever import get_retriever, query_threats

    retriever = get_retriever()
    docs = query_threats("earthquake near coastal city with flooding", n=5)
"""

import os
import chromadb
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings


# ── Path to your existing persistent ChromaDB ──
# Searches common locations automatically
COLLECTION_NAME = "threat_data"

def _find_threat_db() -> str:
    """Auto-detect where threat_db/ lives."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.environ.get("CHROMA_PATH", ""),          # env var override
        os.path.join(script_dir, "threat_db"),       # same folder as this script
        os.path.join(script_dir, "..", "threat_db"), # one level up
        os.path.join(os.getcwd(), "threat_db"),      # current working dir
        os.path.join(os.getcwd(), "..", "threat_db"),# one up from cwd
    ]
    for path in candidates:
        if path and os.path.isdir(path):
            print(f"[RETRIEVER] Found ChromaDB at: {os.path.abspath(path)}")
            return os.path.abspath(path)

    # Fallback — let the user know
    print(f"[RETRIEVER] WARNING: Could not find threat_db/ directory!")
    print(f"[RETRIEVER] Searched: {[c for c in candidates if c]}")
    print(f"[RETRIEVER] Set CHROMA_PATH env var or move threat_db/ next to this script")
    return os.path.join(script_dir, "threat_db")

CHROMA_PATH = _find_threat_db()


# ── Cache the embedding model so it only loads once ──
_embedding_model = None

def get_embedding_function():
    """
    Use the same embedding model ChromaDB used when building the DB.
    ChromaDB's default is 'all-MiniLM-L6-v2' — if you used something
    else during build_chromadb.py, swap it here.
    """
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2"
        )
    return _embedding_model


# ── Cache the vectorstore so we don't reconnect every call ──
_vectorstore = None

def get_vectorstore():
    """
    Connect to the existing persisted ChromaDB.
    Does NOT re-embed anything — just opens the existing DB.
    """
    global _vectorstore
    if _vectorstore is None:
        embedding_fn = get_embedding_function()
        _vectorstore = Chroma(
            collection_name=COLLECTION_NAME,
            persist_directory=CHROMA_PATH,
            embedding_function=embedding_fn,
        )
    return _vectorstore


def get_retriever(k: int = 10, domain_filter: str = None):
    """
    Returns a LangChain retriever backed by the threat DB.

    Args:
        k: Number of documents to retrieve per query
        domain_filter: Optional — filter to a specific domain
                       e.g. "earthquake", "pandemic", "flood", etc.
    """
    vectorstore = get_vectorstore()

    search_kwargs = {"k": k}

    if domain_filter:
        search_kwargs["filter"] = {"domain": domain_filter}

    return vectorstore.as_retriever(search_kwargs=search_kwargs)


def query_threats(query: str, n: int = 10, domain: str = None) -> list[dict]:
    """
    Direct query function — returns docs with metadata.
    Useful for testing and for the cascade chain.

    Args:
        query: Natural language query (semantic search)
        n: Number of results
        domain: Optional domain filter

    Returns:
        List of {"content": str, "metadata": dict} dicts
    """
    vectorstore = get_vectorstore()

    filter_dict = {"domain": domain} if domain else None

    results = vectorstore.similarity_search(
        query=query,
        k=n,
        filter=filter_dict,
    )

    return [
        {
            "content": doc.page_content,
            "metadata": doc.metadata,
        }
        for doc in results
    ]


def multi_domain_query(query: str, n_per_domain: int = 3) -> list[dict]:
    """
    Query across multiple domains separately, then merge.
    This ensures you get cross-domain context even if one domain
    dominates the semantic similarity.

    Returns combined results from all domains.
    """
    domains = ["earthquake", "pandemic", "flood", "wildfire", "eruption", "solar"]
    all_results = []

    for domain in domains:
        try:
            results = query_threats(query, n=n_per_domain, domain=domain)
            all_results.extend(results)
        except Exception:
            # Domain might have no matching docs — skip
            continue

    return all_results


# ──────────────────────────────────────────────────────────────
# Quick test
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Connecting to ChromaDB...")
    vs = get_vectorstore()
    count = vs._collection.count()
    print(f"Collection '{COLLECTION_NAME}' has {count:,} documents\n")

    print("Testing semantic search: 'earthquake near Boston'")
    results = query_threats("earthquake near Boston", n=3)
    for r in results:
        print(f"  [{r['metadata'].get('domain', '?')}] {r['content'][:120]}...")
        print(f"    metadata: {r['metadata']}\n")

    print("Testing multi-domain query: 'infrastructure damage after natural disaster'")
    results = multi_domain_query("infrastructure damage after natural disaster", n_per_domain=2)
    for r in results:
        print(f"  [{r['metadata'].get('domain', '?')}] {r['content'][:120]}...")
