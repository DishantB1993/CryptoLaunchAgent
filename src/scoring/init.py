"""Compatibility module for scoring package initialization."""

from src.scoring.launch_score import SCORING_VERSION, candidate_tokens, is_base_token, score_token

__all__ = ["SCORING_VERSION", "candidate_tokens", "is_base_token", "score_token"]
