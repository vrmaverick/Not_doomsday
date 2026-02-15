"""
retriever.py
============
Connects directly to ChromaDB (no LangChain wrapper — works with chromadb 1.5.0).
Provides semantic search across all 6 threat domains (176K docs).

Usage:
    from retriever import query_threats, multi_domain_query

    docs = query_threats("earthquake near coastal city with flooding", n=5)
"""

import os
import chromadb
from dotenv import load_dotenv

load_dotenv()

COLLECTION_NAME = "threat_data"

def _find_chroma_db() -> str:
    """Auto-detect where the chroma DB lives."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.environ.get("CHROMA_PATH", ""),
        os.path.join(script_dir, "chroma_db"),
        os.path.join(script_dir, "..", "chroma_db"),
        os.path.join(script_dir, "threat_db"),
        os.path.join(script_dir, "..", "threat_db"),
        os.path.join(os.getcwd(), "chroma_db"),
        os.path.join(os.getcwd(), "..", "chroma_db"),
        os.path.join(os.getcwd(), "threat_db"),
        os.path.join(os.getcwd(), "..", "threat_db"),
    ]
    for path in candidates:
        if path and os.path.isdir(path):
            print(f"[RETRIEVER] Found ChromaDB at: {os.path.abspath(path)}")
            return os.path.abspath(path)

    print("[RETRIEVER] WARNING: Could not find chroma_db/ or threat_db/!")
    print(f"[RETRIEVER] Set CHROMA_PATH in .env")
    return os.path.join(script_dir, "chroma_db")


# ── Cached singleton ──
_collection = None

def get_collection():
    """Get the ChromaDB collection (cached)."""
    global _collection
    if _collection is None:
        path = _find_chroma_db()
        client = chromadb.PersistentClient(path=path)
        _collection = client.get_collection(COLLECTION_NAME)
        print(f"[RETRIEVER] Collection '{COLLECTION_NAME}' has {_collection.count():,} documents")
    return _collection


def query_threats(query: str, n: int = 10, domain: str = None) -> list[dict]:
    """
    Semantic search against the threat DB.

    Args:
        query: Natural language query
        n: Number of results
        domain: Optional domain filter (earthquake, pandemic, flood, etc.)

    Returns:
        List of {"content": str, "metadata": dict}
    """
    col = get_collection()

    kwargs = {
        "query_texts": [query],
        "n_results": n if not domain else n * 3,  # over-fetch if filtering
    }

    results = col.query(**kwargs)

    docs = []
    for i in range(len(results["documents"][0])):
        meta = results["metadatas"][0][i] if results["metadatas"] else {}
        # Filter in Python — chromadb 1.5.0 where filter is bugged
        if domain and meta.get("domain") != domain:
            continue
        docs.append({
            "content": results["documents"][0][i],
            "metadata": meta,
        })
        if domain and len(docs) >= n:
            break

    return docs


def multi_domain_query(query: str, n_per_domain: int = 3) -> list[dict]:
    """
    Query each domain separately then merge.
    Prevents one domain from dominating results.
    """
    domains = ["earthquake", "pandemic", "flood", "wildfire", "eruption", "solar"]
    all_results = []
    seen = set()

    for domain in domains:
        try:
            results = query_threats(query, n=n_per_domain, domain=domain)
            for r in results:
                key = r["content"][:200]
                if key not in seen:
                    seen.add(key)
                    all_results.append(r)
        except Exception:
            continue

    return all_results


# ──────────────────────────────────────────────────────────────
# Quick test
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    col = get_collection()
    print()

    print("Testing semantic search: 'earthquake near Boston'")
    results = query_threats("earthquake near Boston", n=3)
    for r in results:
        print(f"  [{r['metadata'].get('domain', '?')}] {r['content'][:120]}...")
        print(f"    metadata: {r['metadata']}\n")

    print("Testing multi-domain query: 'infrastructure damage after natural disaster'")
    results = multi_domain_query("infrastructure damage after natural disaster", n_per_domain=2)
    for r in results:
        print(f"  [{r['metadata'].get('domain', '?')}] {r['content'][:120]}...")
