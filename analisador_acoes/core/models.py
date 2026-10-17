"""Modelos de dados e exceções usados por todo o programa (sem dependência de interface)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


class DataError(Exception):
    """Erro de dados/arquivo com mensagem já pronta para ser mostrada ao usuário."""


@dataclass(frozen=True)
class Record:
    """Uma linha válida de um CSV, com apenas as 5 colunas usadas pela análise."""
    ticker: str
    qtd_gain: int
    qtd_loss: int
    taxa: float      # Taxa de Acerto como veio no arquivo (escala 0-100)
    volume: float    # Méd. Volume Leilão (quantidade, não valor financeiro)
    line: int        # número da linha no arquivo (para mensagens de erro)

    @property
    def ops(self) -> int:
        """Número de operações = Qtd Gain + Qtd Loss."""
        return self.qtd_gain + self.qtd_loss


@dataclass
class LoadResult:
    """Resultado da leitura de um CSV."""
    path: str
    records: List[Record]
    total_rows: int                                   # linhas de dados lidas (não vazias)
    invalid_rows: List[Tuple[int, str, str]] = field(default_factory=list)   # (linha, ticker, motivo)
    duplicates: List[Tuple[str, int]] = field(default_factory=list)          # (ticker, ocorrências)
    warnings: List[str] = field(default_factory=list)
    extra_columns: List[str] = field(default_factory=list)                   # colunas ignoradas
    encoding: str = "utf-8"
    delimiter: str = ","
