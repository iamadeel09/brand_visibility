"""GEO Pulse AI backend: scanner, analyzer, truthguard and agent.

Public entry point: ``from backend.agent import run_analysis``.
"""

__all__ = ["run_analysis"]


def __getattr__(name):  # lazy so importing backend.analyzer stays lightweight
    if name == "run_analysis":
        from .agent import run_analysis

        return run_analysis
    raise AttributeError(name)
