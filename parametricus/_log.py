"""
parametricus._log
=================
Logging central da biblioteca (Fase 1.2 do roadmap).

Segue o padrão de bibliotecas Python: o logger ``parametricus`` recebe um
``NullHandler`` — quem consome a biblioteca decide o destino dos logs.

Para ver os logs rapidamente (scripts, exemplos, REPL):

    import parametricus
    parametricus.enable_console_logging()          # INFO
    parametricus.enable_console_logging("DEBUG")   # detalhado

Níveis usados pela biblioteca:
    DEBUG   — detalhes de amostragem, cache (hits/misses), poda por bbox
    INFO    — rebuild concluído, exportações, estatísticas de malha
    WARNING — malha aberta, bbox degenerada, feature com erro
"""

from __future__ import annotations

import logging
from typing import Union

logger: logging.Logger = logging.getLogger("parametricus")
logger.addHandler(logging.NullHandler())

_console_handler: Union[logging.Handler, None] = None


def enable_console_logging(level: Union[int, str] = logging.INFO) -> None:
    """Anexa (uma única vez) um handler de console ao logger da biblioteca."""
    global _console_handler
    if isinstance(level, str):
        level = getattr(logging, level.upper())
    if _console_handler is None:
        _console_handler = logging.StreamHandler()
        _console_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(_console_handler)
    _console_handler.setLevel(level)
    if logger.level == logging.NOTSET or logger.level > level:
        logger.setLevel(level)


def disable_console_logging() -> None:
    """Remove o handler de console anexado por :func:`enable_console_logging`."""
    global _console_handler
    if _console_handler is not None:
        logger.removeHandler(_console_handler)
        _console_handler = None
