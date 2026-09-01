"""Switchable, non-production RAG strategy evaluation framework."""

from packages.rag_lab.chunking import build_chunker
from packages.rag_lab.embeddings import FastEmbedAdapter
from packages.rag_lab.profiles import CANDIDATES, ExperimentProfile, build_profile

__all__ = [
    "CANDIDATES",
    "ExperimentProfile",
    "FastEmbedAdapter",
    "build_chunker",
    "build_profile",
]
