"""
Pitboss v4 - Semantic Matching Module

Provides semantic similarity for heading matching using sentence-transformers.
Falls back to fuzzy string matching if sentence-transformers is unavailable.

Usage:
    from deterministic.semantic_match import semantic_similarity, SEMANTIC_AVAILABLE

    if SEMANTIC_AVAILABLE:
        score = semantic_similarity("Registration Process", "Register to Get Started")
        # Returns cosine similarity [0, 1]
    else:
        # Use fuzzy string matching fallback
"""

from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Semantic similarity threshold for heading matches
# 0.45 catches most reworded headings while avoiding wrong pairings
# (validated on HellSpin brief: 20/23 correct at 0.45, zero wrong matches)
SEMANTIC_THRESHOLD = 0.45

# Model to use (small, fast, good for short text)
MODEL_NAME = "all-MiniLM-L6-v2"

# =============================================================================
# SYNONYM TABLE
# =============================================================================
# Domain-specific slang/synonyms the model can't know.
# Minimal - only for cases that fail semantic matching.
# Format: frozenset of equivalent terms (lowercase, stemmed)
SYNONYMS = [
    # Regional: AU/NZ "pokies" = US/UK "slots"
    frozenset({"slots", "pokies", "slot"}),
    # Semantic gap: model scores 0.337, below threshold
    frozenset({"live", "real-time", "realtime"}),
    # Semantic gap: model scores 0.319, below threshold
    frozenset({"withdrawal", "payout", "cashout", "cash-out"}),
]


def _normalize_for_synonym(text: str) -> set[str]:
    """Extract lowercase words for synonym matching."""
    return set(text.lower().split())


def _has_synonym_match(text1: str, text2: str) -> bool:
    """Check if texts share a synonym relationship."""
    words1 = _normalize_for_synonym(text1)
    words2 = _normalize_for_synonym(text2)

    for syn_set in SYNONYMS:
        # Check if text1 has any word from this synonym set
        match1 = words1 & syn_set
        # Check if text2 has any word from this synonym set
        match2 = words2 & syn_set
        # If both have matches (even different ones), they're synonymous
        if match1 and match2:
            return True
    return False

# =============================================================================
# LAZY MODEL LOADING
# =============================================================================

_model = None
_model_load_attempted = False
SEMANTIC_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    SEMANTIC_AVAILABLE = True
except ImportError:
    SentenceTransformer = None
    np = None
    logger.info("sentence-transformers not available; using fuzzy string matching fallback")


def _get_model():
    """Lazy load the sentence transformer model."""
    global _model, _model_load_attempted

    if not SEMANTIC_AVAILABLE:
        return None

    if _model is not None:
        return _model

    if _model_load_attempted:
        return None

    _model_load_attempted = True

    try:
        logger.info(f"Loading sentence transformer model: {MODEL_NAME}")
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("Model loaded successfully")
        return _model
    except Exception as e:
        logger.warning(f"Failed to load sentence transformer model: {e}")
        return None


def _cosine_similarity(vec1, vec2) -> float:
    """Calculate cosine similarity between two vectors."""
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(dot_product / (norm1 * norm2))


# =============================================================================
# PUBLIC API
# =============================================================================

def semantic_similarity(text1: str, text2: str) -> Optional[float]:
    """
    Calculate semantic similarity between two text strings.

    Args:
        text1: First text string
        text2: Second text string

    Returns:
        Cosine similarity score [0, 1], or None if semantic matching unavailable
    """
    model = _get_model()
    if model is None:
        return None

    try:
        embeddings = model.encode([text1, text2])
        return _cosine_similarity(embeddings[0], embeddings[1])
    except Exception as e:
        logger.warning(f"Semantic similarity calculation failed: {e}")
        return None


def fuzzy_word_overlap(text1: str, text2: str) -> float:
    """
    Calculate fuzzy word overlap ratio (fallback method).

    Returns the proportion of words from the shorter text
    that appear in the longer text.

    Args:
        text1: First text string
        text2: Second text string

    Returns:
        Overlap ratio [0, 1]
    """
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())

    if not words1 or not words2:
        return 0.0

    # Use smaller set as reference
    smaller = words1 if len(words1) <= len(words2) else words2
    larger = words2 if len(words1) <= len(words2) else words1

    overlap = len(smaller & larger)
    return overlap / len(smaller) if smaller else 0.0


def heading_matches(
    heading_text: str,
    brief_section_title: str,
    semantic_threshold: float = SEMANTIC_THRESHOLD,
    fuzzy_threshold: float = 0.5,
) -> tuple[bool, float, str]:
    """
    Check if a heading matches a brief section title.

    Uses semantic matching if available, falls back to fuzzy word overlap.
    Synonym table provides a boost for domain-specific slang.

    Args:
        heading_text: The article heading text
        brief_section_title: The brief's required section title
        semantic_threshold: Threshold for semantic match (default 0.45)
        fuzzy_threshold: Threshold for fuzzy match fallback (default 0.5)

    Returns:
        Tuple of (matches: bool, score: float, method: str)
        - matches: Whether the heading matches
        - score: Similarity score [0, 1]
        - method: "semantic", "synonym", or "fuzzy"
    """
    # Check synonym table first - provides automatic match for domain slang
    if _has_synonym_match(heading_text, brief_section_title):
        # Synonym match - return high score to indicate strong match
        return (True, 1.0, "synonym")

    # Try semantic matching
    semantic_score = semantic_similarity(heading_text, brief_section_title)

    if semantic_score is not None:
        matches = semantic_score >= semantic_threshold
        return (matches, semantic_score, "semantic")

    # Fall back to fuzzy matching
    fuzzy_score = fuzzy_word_overlap(heading_text, brief_section_title)
    matches = fuzzy_score >= fuzzy_threshold
    return (matches, fuzzy_score, "fuzzy")
