"""Mini Data Platform Agent package."""

from .cli import app
from .agent import answer_question

__all__ = ["app", "answer_question"]
