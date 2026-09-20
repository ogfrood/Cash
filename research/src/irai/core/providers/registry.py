"""Registro de provedores. Um único ponto de escolha de fonte."""

from __future__ import annotations

from collections.abc import Callable

from irai.core.providers.base import DataProvider

_FACTORIES: dict[str, Callable[..., DataProvider]] = {}


def register(name: str, factory: Callable[..., DataProvider]) -> None:
    _FACTORIES[name] = factory


def available() -> list[str]:
    return sorted(_FACTORIES)


def get_provider(name: str, **kwargs: object) -> DataProvider:
    try:
        factory = _FACTORIES[name]
    except KeyError as exc:
        raise KeyError(
            f"Provedor {name!r} não registrado. Disponíveis: {', '.join(available())}"
        ) from exc
    return factory(**kwargs)


def _bootstrap() -> None:
    """Importa os provedores conhecidos. Falha de import vira ausência do
    provedor, não erro — `yfinance` é dependência opcional."""
    from irai.core.providers import synthetic  # noqa: F401

    try:
        from irai.core.providers import yfinance_provider  # noqa: F401
    except Exception:  # pragma: no cover - depende de dependência opcional
        pass


_bootstrap()
