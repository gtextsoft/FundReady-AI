"""Prompt-caching helpers.

Keeps token cost down by caching the stable prefix of long prompts (rubrics,
system instructions, benchmark context) across calls (DECISIONS.md D16).

Implemented in TASKS.md T2.1.
"""
