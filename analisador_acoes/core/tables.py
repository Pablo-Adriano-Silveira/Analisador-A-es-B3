"""Definição das colunas/linhas das tabelas. Usada pela interface E pelos exportadores,
para que o que aparece na tela seja exatamente o que sai nos arquivos."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .comparison import ComparisonResult, MatchRow
from .ranking import RankingResult


@dataclass(frozen=True)
class Column:
    key: str
    title: str
    kind: str          # text | int | pct | vol | score | pp | bool | money
    width: int = 90
    anchor: str = "e"  # alinhamento na tela (w, center, e)


RANKING_COLUMNS: List[Column] = [
    Column("pos", "Pos.", "int", 60, "center"),
    Column("ticker", "Ativo", "text", 90, "w"),
    Column("price", "Valor Ação (R$)", "money", 125),
    Column("taxa", "Taxa de Acerto", "pct", 130),
    Column("gain", "Qtd Gain", "int", 80),
    Column("loss", "Qtd Loss", "int", 80),
    Column("ops", "Operações", "int", 90),
    Column("volume", "Méd. Volume Leilão", "vol", 165),
    Column("wilson", "Taxa ajustada (Wilson)", "pct", 185),
    Column("score", "Pontuação", "score", 100),
]


def ranking_rows(result: RankingResult) -> List[Dict[str, Any]]:
    out = []
    for r in result.rows:
        rec = r.record
        out.append({"pos": r.pos, "ticker": rec.ticker, "price": result.prices.get(rec.ticker), "taxa": rec.taxa, "gain": rec.qtd_gain,
                    "loss": rec.qtd_loss, "ops": rec.ops, "volume": rec.volume,
                    "wilson": r.wilson, "score": r.score})
    return out


EXCLUDED_COLUMNS: List[Column] = [
    Column("ticker", "Ativo", "text", 90, "w"),
    Column("price", "Valor Ação (R$)", "money", 125),
    Column("volume", "Méd. Volume Leilão", "vol", 165),
    Column("ops", "Operações", "int", 90),
    Column("gain", "Qtd Gain", "int", 80),
    Column("reason", "Motivo da exclusão", "text", 220, "w"),
]


def excluded_rows(result: RankingResult) -> List[Dict[str, Any]]:
    out = []
    for e in result.excluded_volume + result.excluded_filters + result.excluded_price:
        r = e.record
        out.append({"ticker": r.ticker, "price": result.prices.get(r.ticker), "volume": r.volume, "ops": r.ops,
                    "gain": r.qtd_gain, "reason": e.reason})
    return out


def comparison_columns(la: str, lb: str) -> List[Column]:
    return [
        Column("ticker", "Ativo", "text", 90, "w"),
        Column("price", "Valor Ação (R$)", "money", 125),
        Column("pos_a", f"Pos. {la}", "int", 70, "center"),
        Column("pos_b", f"Pos. {lb}", "int", 70, "center"),
        Column("taxa_a", f"Taxa {la}", "pct", 85),
        Column("taxa_b", f"Taxa {lb}", "pct", 85),
        Column("delta", f"Δ Taxa ({lb}−{la})", "pp", 140),
        Column("gain_a", f"Gain {la}", "int", 75),
        Column("gain_b", f"Gain {lb}", "int", 75),
        Column("loss_a", f"Loss {la}", "int", 75),
        Column("loss_b", f"Loss {lb}", "int", 75),
        Column("ops_a", f"Oper. {la}", "int", 80),
        Column("ops_b", f"Oper. {lb}", "int", 80),
        Column("vol_a", f"Volume {la}", "vol", 105),
        Column("vol_b", f"Volume {lb}", "vol", 105),
        Column("score_a", f"Nota {la}", "score", 80),
        Column("score_b", f"Nota {lb}", "score", 80),
        Column("score_mean", "Nota média", "score", 90),
        Column("score_min", "Pior nota", "score", 85),
        Column("vol_div", "Volume divergente", "bool", 145, "center"),
    ]


def comparison_rows(matches: List[MatchRow]) -> List[Dict[str, Any]]:
    out = []
    for m in matches:
        a, b = m.a.record, m.b.record
        out.append({
            "ticker": m.ticker, "price": m.price, "pos_a": m.a.pos, "pos_b": m.b.pos,
            "taxa_a": a.taxa, "taxa_b": b.taxa, "delta": m.delta_taxa,
            "gain_a": a.qtd_gain, "gain_b": b.qtd_gain, "loss_a": a.qtd_loss, "loss_b": b.qtd_loss,
            "ops_a": a.ops, "ops_b": b.ops, "vol_a": a.volume, "vol_b": b.volume,
            "score_a": m.a.score, "score_b": m.b.score,
            "score_mean": m.score_mean, "score_min": m.score_min, "vol_div": m.volume_divergent,
        })
    return out


def comparison_summary(c: ComparisonResult) -> List[tuple]:
    """Linhas (rótulo, valor) com a contagem do comparativo."""
    lim = f"{c.limit_top_n} melhores de cada" if c.limit_top_n > 0 else "todos os elegíveis"
    return [
        (f"Ativos no arquivo {c.label_a}", c.total_a),
        (f"Ativos no arquivo {c.label_b}", c.total_b),
        ("Presentes nos dois arquivos", c.n_both),
        (f"Somente em {c.label_a}", len(c.only_a)),
        (f"Somente em {c.label_b}", len(c.only_b)),
        ("Descartados pelo volume (nos dois arquivos)", c.dropped_volume),
        ("Descartados pelo mínimo de operações/gain", c.dropped_filters),
    ] + ([("Descartados pelo valor da ação (abaixo de R$ " + f"{c.config.min_price:.2f}".replace(".", ",") + " ou sem cotação)", c.dropped_price)]
         if c.config.min_price is not None else []) + [
        ("Descartados pelo limite de melhores", c.dropped_top_n),
        ("Critério de seleção", lim),
        ("Matches finais", len(c.matches)),
    ]
