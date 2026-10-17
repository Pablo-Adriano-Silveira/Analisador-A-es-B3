"""Classificação das ações (método aprovado).

Filtros (nesta ordem):
  1. Volume médio de leilão  >  min_volume  (estritamente maior; 80.000 exato é excluído)
  2. Operações (Qtd Gain + Qtd Loss)  >=  min_ops
  3. Qtd Gain >= 1
  4. (opcional) Valor da ação >= min_price  (preço vindo da API; sem cotação = excluída)

Pontuação 0-100 entre as ações elegíveis (cada componente vira um percentil 0-1):
  70%  Taxa de acerto ajustada pela amostra (limite inferior de Wilson, 95%)
  20%  Qtd Gain       (percentil: mais acertos é melhor)
  10%  Qtd Loss       (percentil invertido: menos perdas é melhor)

Desempate: Taxa de Acerto do arquivo (maior primeiro) e, por fim, ticker (ordem alfabética).
O volume entra apenas como filtro, não pesa na nota.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .models import Record

REASON_VOLUME = "Volume abaixo do mínimo"
REASON_OPS = "Operações abaixo do mínimo"
REASON_GAIN = "Sem nenhum Gain"
REASON_PRICE_LOW = "Valor da ação abaixo do mínimo"
REASON_NO_PRICE = "Sem cotação"


@dataclass(frozen=True)
class ScoringConfig:
    min_volume: float = 80_000
    min_ops: int = 10
    top_n: int = 40
    w_taxa: float = 0.70
    w_gain: float = 0.20
    w_loss: float = 0.10
    z: float = 1.96          # 95% de confiança
    min_price: Optional[float] = None   # R$; None = sem filtro de preço

    def validate(self) -> None:
        if self.min_volume < 0:
            raise ValueError("O volume mínimo não pode ser negativo.")
        if self.min_ops < 1:
            raise ValueError("O mínimo de operações deve ser pelo menos 1.")
        if self.min_price is not None and self.min_price < 0:
            raise ValueError("O valor mínimo da ação não pode ser negativo.")
        if self.top_n < 1:
            raise ValueError("A quantidade de ações do ranking deve ser pelo menos 1.")
        if abs(self.w_taxa + self.w_gain + self.w_loss - 1.0) > 1e-9:
            raise ValueError("Os pesos da pontuação devem somar 100%.")


@dataclass(frozen=True)
class Excluded:
    record: Record
    reason: str


@dataclass(frozen=True)
class RankedRow:
    pos: int
    record: Record
    wilson: float    # limite inferior de Wilson, em % (0-100)
    score: float     # pontuação final 0-100


@dataclass
class RankingResult:
    config: ScoringConfig
    total: int                        # registros válidos analisados
    excluded_volume: List[Excluded]
    excluded_filters: List[Excluded]  # passaram no volume, mas falharam em operações/gain
    ranked: List[RankedRow]           # TODOS os elegíveis, já ordenados
    excluded_price: List[Excluded] = field(default_factory=list)   # reprovadas por preço / sem cotação
    prices: Dict[str, float] = field(default_factory=dict)         # preços usados (R$)

    @property
    def volume_ok(self) -> int:
        return self.total - len(self.excluded_volume)

    @property
    def price_low(self) -> int:
        return sum(1 for e in self.excluded_price if e.reason == REASON_PRICE_LOW)

    @property
    def price_missing(self) -> int:
        return sum(1 for e in self.excluded_price if e.reason == REASON_NO_PRICE)

    @property
    def eligible(self) -> int:
        return len(self.ranked)

    @property
    def rows(self) -> List[RankedRow]:
        """As N melhores (N = config.top_n). Nunca completa com inelegíveis."""
        return self.ranked[: self.config.top_n]


def wilson_lower(successes: int, n: int, z: float = 1.96) -> float:
    """Limite inferior do intervalo de Wilson para a proporção de acertos (fração 0-1)."""
    if n <= 0:
        return 0.0
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = p + z2 / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return max(0.0, (centre - margin) / denom)


def _ranks(values: Sequence[float]):
    """Retorna (ranks médios, ranks mínimos), ambos começando em 1 (como pandas rank average/min)."""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    avg = [0.0] * n
    mn = [0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        a = (i + j) / 2 + 1
        for k in range(i, j + 1):
            avg[order[k]] = a
            mn[order[k]] = i + 1
        i = j + 1
    return avg, mn


def passes_basic_filters(r: Record, config: ScoringConfig) -> Optional[str]:
    """None se passa em volume, operações e gain; senão, o motivo da exclusão."""
    if not (r.volume > config.min_volume):
        return REASON_VOLUME
    if r.ops < config.min_ops:
        return REASON_OPS
    if r.qtd_gain < 1:
        return REASON_GAIN
    return None


def candidates(records: Sequence[Record], config: ScoringConfig) -> List[Record]:
    """Ações que já passam nos filtros sem preço (são as únicas para as quais vale buscar cotação)."""
    return [r for r in records if passes_basic_filters(r, config) is None]


def rank_records(records: Sequence[Record], config: ScoringConfig,
                 prices: Optional[Dict[str, float]] = None) -> RankingResult:
    """Aplica filtros e calcula a pontuação de cada ação elegível."""
    config.validate()
    prices = prices or {}
    excluded_volume: List[Excluded] = []
    excluded_filters: List[Excluded] = []
    excluded_price: List[Excluded] = []
    eligible: List[Record] = []

    for r in records:
        reason = passes_basic_filters(r, config)
        if reason == REASON_VOLUME:
            excluded_volume.append(Excluded(r, reason))
        elif reason is not None:
            excluded_filters.append(Excluded(r, reason))
        elif config.min_price is not None:
            p = prices.get(r.ticker)
            if p is None:
                excluded_price.append(Excluded(r, REASON_NO_PRICE))       # nunca presume o preço
            elif p < config.min_price - 1e-9:
                excluded_price.append(Excluded(r, REASON_PRICE_LOW))
            else:
                eligible.append(r)
        else:
            eligible.append(r)

    ranked: List[RankedRow] = []
    n = len(eligible)
    if n:
        wil = [wilson_lower(r.qtd_gain, r.ops, config.z) for r in eligible]
        wil_avg, _ = _ranks(wil)
        gain_avg, _ = _ranks([r.qtd_gain for r in eligible])
        _, loss_min = _ranks([r.qtd_loss for r in eligible])
        scored = []
        for i, r in enumerate(eligible):
            c_taxa = wil_avg[i] / n
            c_gain = gain_avg[i] / n
            c_loss = (n - loss_min[i] + 1) / n     # menos perdas -> mais perto de 1
            score = 100.0 * (config.w_taxa * c_taxa + config.w_gain * c_gain + config.w_loss * c_loss)
            scored.append((score, r, wil[i] * 100.0))
        # nota desc, taxa de acerto desc, ticker asc
        scored.sort(key=lambda t: (-t[0], -t[1].taxa, t[1].ticker))
        ranked = [RankedRow(pos + 1, r, w, s) for pos, (s, r, w) in enumerate(scored)]

    return RankingResult(config, len(records), excluded_volume, excluded_filters, ranked,
                         excluded_price, dict(prices))
