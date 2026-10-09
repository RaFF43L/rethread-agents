"""AI layer: providers, router/specialists graph, tools and prompts.

Kept import-free on purpose: `catalog` imports `ai.llm`, and an eager
`from ai.agent import ...` here would create a circular import.
"""
