import hashlib
import json
import re
import sqlite3
from typing import Any, Dict, List, Optional

import numpy as np

EMBEDDING_DIM = 128

# Canonical concept synonyms so semantic retrieval links related phrasings
CONCEPT_MAP = {
    "launch": ["launch", "release", "go-live", "ship", "rollout", "debut"],
    "deadline": ["deadline", "date", "timeline", "schedule", "due", "december", "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november"],
    "pricing": ["price", "pricing", "tier", "cost", "subscription", "billing"],
    "budget": ["budget", "spend", "allocation", "funding", "expense"],
    "security": ["security", "compliance", "soc2", "auth", "encryption", "audit"],
    "vendor": ["vendor", "provider", "supplier", "contract", "partner"],
}


def compute_embedding(text: str) -> List[float]:
    """
    Generate a deterministic 128-dim normalized semantic embedding vector using
    token hashing + bigrams + domain concept projection.
    Compatible with pgvector vector(128) / cosine similarity.
    """
    vec = np.zeros(EMBEDDING_DIM, dtype=np.float64)
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    if not tokens:
        return vec.tolist()

    # Unigram & bigram feature hashing
    features = list(tokens) + [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]
    for feat in features:
        h = int(hashlib.sha256(feat.encode("utf-8")).hexdigest(), 16)
        idx = h % EMBEDDING_DIM
        sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
        vec[idx] += sign

    # Domain concept boosting for high-recall cross-meeting semantic matching
    token_set = set(tokens)
    for concept_idx, (_, synonyms) in enumerate(CONCEPT_MAP.items()):
        if token_set.intersection(synonyms):
            vec[concept_idx] += 3.5

    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec = vec / norm
    return [round(float(x), 6) for x in vec]


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    a = np.asarray(vec_a, dtype=np.float64)
    b = np.asarray(vec_b, dtype=np.float64)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


class CrossMeetingMemoryAgent:
    """
    Agent 5: Cross-Meeting Decision Memory.
    Retrieves historical decisions and related meetings using vector cosine similarity
    combined with organization isolation and optional metadata filters.
    """

    def search_decisions(
        self,
        conn: sqlite3.Connection,
        organization_id: str,
        query: str,
        top_k: int = 5,
        exclude_meeting_id: Optional[str] = None,
        status_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query_vec = compute_embedding(query)
        sql = """
            SELECT d.*, m.title AS meeting_title, m.meeting_date AS meeting_date
            FROM decisions d
            JOIN meetings m ON d.meeting_id = m.id
            WHERE d.organization_id = ? AND d.is_deleted = 0
        """
        params: List[Any] = [organization_id]
        if exclude_meeting_id:
            sql += " AND d.meeting_id != ?"
            params.append(exclude_meeting_id)
        if status_filter:
            sql += " AND d.status = ?"
            params.append(status_filter)

        rows = conn.execute(sql, params).fetchall()
        scored: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            emb = json.loads(item.get("embedding_json") or "[]")
            if not emb:
                emb = compute_embedding(f"{item['subject']} {item['statement']}")
            sim = cosine_similarity(query_vec, emb)
            # Lexical subject overlap boost
            if item["subject"].lower() in query.lower() or query.lower() in item["subject"].lower():
                sim = min(1.0, sim + 0.25)
            item["similarity_score"] = round(sim, 4)
            scored.append(item)

        scored.sort(key=lambda x: x["similarity_score"], reverse=True)
        return scored[:top_k]
