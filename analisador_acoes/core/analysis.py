"""Orquestra a busca de preços para as ações que realmente precisam de cotação."""
from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional, Sequence

from .models import DataError, Record
from .price_service import BrapiClient, PriceCache, PriceError, fetch_prices
from .ranking import ScoringConfig, candidates


def resolve_token(typed: str) -> str:
    """Chave digitada na tela ou, se vazia, variável de ambiente BRAPI_TOKEN."""
    return (typed or "").strip() or os.environ.get("BRAPI_TOKEN", "").strip()


def gather_prices(record_lists: Sequence[Sequence[Record]], config: ScoringConfig, token: str,
                  refresh: bool = False, progress: Optional[Callable[[int, int], None]] = None,
                  client: Optional[BrapiClient] = None,
                  cache: Optional[PriceCache] = None,
                  notify: Optional[Callable[[str], None]] = None) -> Dict[str, float]:
    """Busca o preço só dos tickers que passaram em volume/operações/gain (em qualquer arquivo).
    Levanta DataError se a consulta for interrompida (chave inválida, limite, sem internet)."""
    tickers = set()
    for recs in record_lists:
        tickers |= {r.ticker for r in candidates(recs, config)}
    try:
        client = client or BrapiClient(token, notify=notify)
    except PriceError as exc:
        raise DataError(str(exc)) from exc
    batch = fetch_prices(tickers, client, cache or PriceCache(), progress=progress, refresh=refresh)
    if batch.fatal:
        extra = (f" Os {batch.fetched} preços já obtidos ficaram no cache para a próxima tentativa."
                 if batch.fetched else "")
        raise DataError("Não foi possível obter os preços das ações.\n" + batch.fatal + extra)
    return batch.prices
