"""Comparativo entre duas configurações (ex.: 2% x 1%), sempre dentro do MESMO lado
(compra com compra, venda com venda — a interface nunca mistura os dois).

Regras:
  * chave = ticker normalizado; a posição no arquivo não é usada como identificador;
  * ticker duplicado já foi resolvido na leitura (uma linha por ticker);
  * regra de volume: o ticker só é elegível se o volume for > mínimo NOS DOIS arquivos
    (equivale a min(volume_A, volume_B) > mínimo); divergência de volume é sinalizada;
  * depois do volume, valem os mesmos filtros de operações do ranking, em cada arquivo;
  * opcional: limitar aos N melhores de cada ranking (0 = todos os elegíveis);
  * nenhum dado ausente é preenchido com zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .models import LoadResult
from .ranking import RankedRow, RankingResult, ScoringConfig, rank_records


@dataclass(frozen=True)
class MatchRow:
    ticker: str
    a: RankedRow            # configuração A (ex.: 2%)
    b: RankedRow            # configuração B (ex.: 1%)
    price: Optional[float] = None   # valor da ação (R$), quando consultado

    @property
    def volume_divergent(self) -> bool:
        return self.a.record.volume != self.b.record.volume

    @property
    def score_mean(self) -> float:
        return (self.a.score + self.b.score) / 2.0

    @property
    def score_min(self) -> float:
        return min(self.a.score, self.b.score)

    @property
    def delta_taxa(self) -> float:
        """Taxa de acerto de B menos a de A, em pontos percentuais."""
        return self.b.record.taxa - self.a.record.taxa

    @property
    def min_volume(self) -> float:
        return min(self.a.record.volume, self.b.record.volume)


@dataclass
class ComparisonResult:
    label_a: str
    label_b: str
    config: ScoringConfig
    limit_top_n: int
    total_a: int
    total_b: int
    n_both: int                 # tickers presentes nos dois arquivos
    only_a: List[str]
    only_b: List[str]
    dropped_volume: int         # nos dois arquivos, mas reprovados pela regra de volume
    dropped_filters: int        # reprovados em operações/gain em pelo menos um arquivo
    dropped_top_n: int          # fora do top N de pelo menos um ranking
    matches: List[MatchRow]
    ranking_a: RankingResult
    ranking_b: RankingResult
    volume_divergences: int     # tickers em ambos com volumes diferentes entre os arquivos
    notes: List[str]
    dropped_price: int = 0      # reprovados pelo valor mínimo da ação / sem cotação


# Opções de ordenação: nome na interface -> (função chave, decrescente?)
SORT_OPTIONS: Dict[str, Callable[[MatchRow], object]] = {
    "Nota média": lambda m: m.score_mean,
    "Pior nota das duas": lambda m: m.score_min,
    "Taxa de acerto (A)": lambda m: m.a.record.taxa,
    "Taxa de acerto (B)": lambda m: m.b.record.taxa,
    "Menor diferença de taxa": lambda m: -abs(m.delta_taxa),
    "Volume (menor dos dois)": lambda m: m.min_volume,
    "Ativo (A-Z)": lambda m: m.ticker,
}


def sort_matches(matches: List[MatchRow], option: str) -> List[MatchRow]:
    """Ordena sem recalcular nada. Todas as opções são 'maior primeiro', exceto Ativo (A-Z)."""
    key = SORT_OPTIONS.get(option, SORT_OPTIONS["Nota média"])
    if option == "Ativo (A-Z)":
        return sorted(matches, key=key)
    return sorted(matches, key=lambda m: (key(m), m.ticker), reverse=True)


def compare(load_a: LoadResult, load_b: LoadResult, config: ScoringConfig,
            label_a: str = "2%", label_b: str = "1%", limit_top_n: int = 0,
            prices: Optional[Dict[str, float]] = None) -> ComparisonResult:
    config.validate()
    rank_a = rank_records(load_a.records, config, prices)
    rank_b = rank_records(load_b.records, config, prices)
    filt_a = {e.record.ticker for e in rank_a.excluded_filters}
    filt_b = {e.record.ticker for e in rank_b.excluded_filters}

    rec_a = {r.ticker: r for r in load_a.records}
    rec_b = {r.ticker: r for r in load_b.records}
    pos_a = {row.record.ticker: row for row in rank_a.ranked}
    pos_b = {row.record.ticker: row for row in rank_b.ranked}

    both = sorted(set(rec_a) & set(rec_b))
    only_a = sorted(set(rec_a) - set(rec_b))
    only_b = sorted(set(rec_b) - set(rec_a))

    matches: List[MatchRow] = []
    dropped_volume = dropped_filters = dropped_price = dropped_top = divergences = 0
    for t in both:
        if rec_a[t].volume != rec_b[t].volume:
            divergences += 1
        if not (min(rec_a[t].volume, rec_b[t].volume) > config.min_volume):
            dropped_volume += 1
            continue
        if t not in pos_a or t not in pos_b:
            if t in filt_a or t in filt_b:
                dropped_filters += 1
            else:
                dropped_price += 1      # só sobra o filtro de valor da ação / sem cotação
            continue
        if limit_top_n > 0 and (pos_a[t].pos > limit_top_n or pos_b[t].pos > limit_top_n):
            dropped_top += 1
            continue
        matches.append(MatchRow(t, pos_a[t], pos_b[t], (prices or {}).get(t)))

    matches = sort_matches(matches, "Nota média")

    notes: List[str] = []
    ex_a, ex_b = set(load_a.extra_columns), set(load_b.extra_columns)
    if ex_a != ex_b:
        diff = sorted(ex_a ^ ex_b)
        notes.append("Colunas presentes em apenas um dos arquivos (não comparadas): " + ", ".join(diff) + ".")
    if divergences:
        notes.append(f"{divergences} ticker(s) com volume diferente entre os arquivos; "
                     "vale o menor dos dois para o filtro.")
    notes.append("Notas calculadas separadamente em cada arquivo (percentis dentro do próprio arquivo).")

    return ComparisonResult(
        label_a=label_a, label_b=label_b, config=config, limit_top_n=limit_top_n,
        total_a=len(rec_a), total_b=len(rec_b), n_both=len(both),
        only_a=only_a, only_b=only_b,
        dropped_volume=dropped_volume, dropped_filters=dropped_filters, dropped_top_n=dropped_top,
        matches=matches, ranking_a=rank_a, ranking_b=rank_b,
        volume_divergences=divergences, notes=notes, dropped_price=dropped_price,
    )
