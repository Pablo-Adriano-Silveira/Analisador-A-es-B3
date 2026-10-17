"""Formatação de números no padrão brasileiro para exibição."""
from __future__ import annotations

from typing import Any


def fmt_int(v: Any) -> str:
    return f"{int(round(v)):,}".replace(",", ".")


def fmt_dec(v: float, nd: int = 2) -> str:
    return f"{v:,.{nd}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def fmt_value(kind: str, v: Any) -> str:
    """Texto exibido na tabela. Valor ausente aparece como '—' (nunca como zero)."""
    if v is None:
        return "—"
    if kind == "int" or kind == "vol":
        return fmt_int(v)
    if kind == "pct":
        return fmt_dec(v, 2) + "%"
    if kind == "score":
        return fmt_dec(v, 2)
    if kind == "money":
        return "R$ " + fmt_dec(v, 2)
    if kind == "pp":
        return ("+" if v > 0 else "") + fmt_dec(v, 2) + " p.p."
    if kind == "bool":
        return "Sim" if v else "Não"
    return str(v)
