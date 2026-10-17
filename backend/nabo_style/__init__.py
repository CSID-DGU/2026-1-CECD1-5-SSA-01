"""NABO-style estimation prototype, kept separate from backend/erce.

Structure mirrors how NABO analysts work: scope each fiscal clause first,
decompose it into budget-item templates, fill common forecasts from a
reference table mined from earlier public estimates, and reuse whole
precedent packages before building costs from components.
"""
