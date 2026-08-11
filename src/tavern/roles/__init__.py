"""LLM role wrappers.

Each role is a plain function that composes a specialised prompt around a
provider call. Roles have no shared state — the orchestrator wires them.
"""
