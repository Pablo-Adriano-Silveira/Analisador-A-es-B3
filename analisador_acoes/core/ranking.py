"""Classificação das ações (método aprovado).

Filtros (nesta ordem):
  1. Volume médio de leilão  >  min_volume  (estritamente maior; 80.000 exato é excluído)
  2. Operações (Qtd Gain + Qtd Loss)  >=  min_ops
  3. Qtd Gain >= 1

Pontuação 0-100 entre as ações elegíveis (cada componente vira um percentil 0-1):
  70%  Taxa de acerto ajustada pela amostra (limite inferior de Wilson, 95%)
  20%  Qtd Gain       (percentil: mais acertos é melhor)
  10%  Qtd Loss       (percentil invertido: menos perdas é melhor)

Desempate: Taxa de Acerto do arquivo (maior primeiro) e, por fim, ticker (ordem alfabética).
O volume entra apenas como filtro, não pesa na nota.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence

from .models import Record

REASON_VOLUME = "Volume abaixo do mínimo"
REASON_OPS = "Operações abaixo do mínimo"
REASON_GAIN = "Sem nenhum Gain"


@dataclass(frozen=True)
class ScoringConfig:
    min_volume: float = 80_000
    min_ops: int = 10
    top_n: int = 40
    w_taxa: float = 0.70
    w_gain: float = 0.20
    w_loss: float = 0.10
    z: float = 1.96          # 95% de confiança

    def validate(self) -> None:
        if self.min_volume < 0:
            raise ValueError("O volume mínimo não pode ser negativo.")
        if self.min_ops < 1:
            raise ValueError("O mínimo de operações deve ser pelo menos 1.")
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

    @property
    def volume_ok(self) -> int:
        return self.total - len(self.excluded_volume)

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


def rank_records(records: Sequence[Record], config: ScoringConfig) -> RankingResult:
    """Aplica filtros e calcula a pontuação de cada ação elegível."""
    config.validate()
    excluded_volume: List[Excluded] = []
    excluded_filters: List[Excluded] = []
    eligible: List[Record] = []

    for r in records:
        if not (r.volume > config.min_volume):
            excluded_volume.append(Excluded(r, REASON_VOLUME))
        elif r.ops < config.min_ops:
            excluded_filters.append(Excluded(r, REASON_OPS))
        elif r.qtd_gain < 1:
            excluded_filters.append(Excluded(r, REASON_GAIN))
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

    return RankingResult(config, len(records), excluded_volume, excluded_filters, ranked)
