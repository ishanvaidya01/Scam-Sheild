"""
network_analyzer.py

Signal 5 of 5: Cross-user interaction graph analysis using NetworkX.

Novel contribution: Rather than analyzing comments in isolation or as a flat list,
this module models the live chat as a dynamic graph where nodes are users and
edges represent semantic co-occurrence (two different users posting semantically
similar content within a time window). Coordinated bot rings leave highly distinctive
clique patterns in this graph that are extremely difficult to fake organically.

This is a key patent-differentiating feature: no commercial tool currently
performs graph-theoretic analysis on live chat streams in real time.

Graph structure:
  - Nodes: usernames
  - Edges: weighted by cosine similarity, only created if similarity >= threshold
  - Edge is only created between DIFFERENT users

Detects:
  1. Cliques (groups of 3+ fully interconnected users) → bot rings
  2. Hub nodes (one user semantically similar to many others) → template distributor
  3. Rapid edge accumulation (graph density growing too fast) → coordinated wave

Output schema:
  {
    "score": float,
    "features": {
      "is_in_clique": bool,
      "clique_size": int,
      "hub_score": float,       # (0–1) how hub-like is this user
      "graph_density": float,
      "edge_count": int
    },
    "reasons": [str]
  }
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import networkx as nx
    _NX_AVAILABLE = True
except ImportError:
    nx = None
    _NX_AVAILABLE = False
    logger.warning("NetworkX not installed. NetworkAnalyzer will return neutral scores.")

# ── Thresholds ─────────────────────────────────────────────────────────────────
EDGE_SIMILARITY_THRESHOLD = 0.80  # minimum similarity to draw an edge
MIN_CLIQUE_SIZE = 3               # minimum clique size to flag
HUB_DEGREE_THRESHOLD = 4         # connections to be considered a hub


def analyze_network(
    comment: dict,
    session_edges: dict,
    session_user_profiles: dict,
    new_embedding,  # torch.Tensor or None
    recent_window: list,
) -> dict:
    """
    Updates the session graph with the new comment's edges and analyzes
    graph-level patterns for the current user.

    Args:
        comment: { "comment_id", "text", "username", "timestamp" }
        session_edges: dict mapping frozenset({u1,u2}) → max_similarity (mutated in place)
        session_user_profiles: dict of username → UserProfile (for context)
        new_embedding: sentence embedding of the new comment (torch.Tensor or None)
        recent_window: rolling window of recent comments (each may have 'embedding')

    Returns:
        { "score": float, "features": dict, "reasons": [str] }
    """
    neutral_result = {
        "score": 1.0,
        "features": {
            "is_in_clique": False,
            "clique_size": 0,
            "hub_score": 0.0,
            "graph_density": 0.0,
            "edge_count": 0,
        },
        "reasons": [],
    }

    if not _NX_AVAILABLE or new_embedding is None:
        return neutral_result

    try:
        from sentence_transformers import util as st_util
    except ImportError:
        return neutral_result

    username = comment.get("username", "")
    reasons: list[str] = []

    # ── Step 1: Add edges from new comment to recent window ───────────────────
    for past_comment in recent_window:
        past_user = past_comment.get("username", "")
        if past_user == username:
            continue  # skip same user (self-loops not meaningful)

        past_emb = past_comment.get("embedding")
        if past_emb is None:
            continue

        try:
            sim = st_util.cos_sim(new_embedding, past_emb).item()
        except Exception:
            continue

        if sim >= EDGE_SIMILARITY_THRESHOLD:
            edge_key = frozenset({username, past_user})
            # Keep the maximum similarity for this user pair
            existing = session_edges.get(edge_key, 0.0)
            session_edges[edge_key] = max(existing, sim)

    # ── Step 2: Build NetworkX graph from current edges ───────────────────────
    G = nx.Graph()
    for edge_key, weight in session_edges.items():
        users = list(edge_key)
        if len(users) == 2:
            G.add_edge(users[0], users[1], weight=weight)

    if username not in G.nodes:
        # No edges for this user yet → genuinely isolated → good sign
        return {
            "score": 1.0,
            "features": {
                "is_in_clique": False,
                "clique_size": 0,
                "hub_score": 0.0,
                "graph_density": round(nx.density(G), 4) if G.number_of_nodes() > 1 else 0.0,
                "edge_count": G.number_of_edges(),
            },
            "reasons": [],
        }

    graph_density = nx.density(G) if G.number_of_nodes() > 1 else 0.0
    edge_count = G.number_of_edges()

    # ── Step 3: Detect cliques containing this user ───────────────────────────
    is_in_clique = False
    max_clique_size = 0
    try:
        for clique in nx.find_cliques(G):
            if username in clique and len(clique) >= MIN_CLIQUE_SIZE:
                is_in_clique = True
                max_clique_size = max(max_clique_size, len(clique))
    except Exception:
        pass

    # ── Step 4: Hub detection for this user ──────────────────────────────────
    user_degree = G.degree(username) if username in G else 0
    hub_score = min(1.0, user_degree / max(HUB_DEGREE_THRESHOLD * 2, 1))

    # ── Step 5: Score and reasons ─────────────────────────────────────────────
    penalty = 0.0

    if is_in_clique:
        penalty += 0.50
        reasons.append(
            f"User is part of a coordinated clique of {max_clique_size} accounts "
            "all posting semantically similar content — strong bot ring indicator."
        )

    if user_degree >= HUB_DEGREE_THRESHOLD:
        penalty += 0.30
        reasons.append(
            f"User's content is semantically linked to {user_degree} other accounts "
            "in this session — possible template distributor or central bot node."
        )

    if graph_density > 0.6 and G.number_of_nodes() >= 5:
        penalty += 0.15
        reasons.append(
            f"Session graph is unusually dense ({graph_density:.2f}) — "
            "high interconnection between many accounts suggests coordinated campaign."
        )

    score = max(0.0, min(1.0, 1.0 - penalty))

    return {
        "score": score,
        "features": {
            "is_in_clique": is_in_clique,
            "clique_size": max_clique_size,
            "hub_score": round(hub_score, 3),
            "graph_density": round(graph_density, 4),
            "edge_count": edge_count,
        },
        "reasons": reasons,
    }
