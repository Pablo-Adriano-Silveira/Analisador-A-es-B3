"""Leitura robusta dos CSVs.

Pontos tratados:
  * codificação (UTF-8 com/sem BOM, cai para cp1252/latin-1);
  * delimitador (vírgula, ponto e vírgula, tab ou barra vertical);
  * nomes de colunas com acento/maiúsculas/pontuação diferentes;
  * coluna inicial sem nome (índice do pandas) é ignorada;
  * números no padrão brasileiro ("1.234,5") ou internacional ("1234.5");
  * Méd. Volume Leilão com ponto como separador de milhar ("29.869.975");
  * valores ausentes NUNCA viram zero: a linha é rejeitada e listada;
  * tickers duplicados: mantém a linha com mais operações e avisa.
"""
from __future__ import annotations

import csv
import io
import math
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

from .models import DataError, LoadResult, Record

# Colunas necessárias -> nomes aceitos (já normalizados por normalize_header)
ALIASES: Dict[str, set] = {
    "ticker": {"ativo", "ticker", "papel", "codigo", "acao"},
    "qtd_gain": {"qtd gain", "qtde gain", "qtd gains", "quantidade gain"},
    "qtd_loss": {"qtd loss", "qtde loss", "qtd losses", "quantidade loss"},
    "taxa": {"taxa de acerto", "taxa acerto", "acerto"},
    "volume": {"med volume leilao", "media volume leilao", "volume medio leilao",
               "med volume de leilao", "media de volume leilao"},
}
DISPLAY_NAMES = {
    "ticker": "Ativo", "qtd_gain": "Qtd Gain", "qtd_loss": "Qtd Loss",
    "taxa": "Taxa de Acerto", "volume": "Méd. Volume Leilão",
}
# Divergência máxima tolerada entre a taxa do arquivo e Gain/(Gain+Loss), em pontos percentuais
TAXA_TOLERANCE = 0.5


# ----------------------------------------------------------------------------- helpers de texto
def normalize_header(name: str) -> str:
    """'Méd. Volume Leilão' -> 'med volume leilao' (sem acento, minúsculo, sem pontuação)."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-zA-Z0-9]+", " ", s).strip().lower()
    return s


def normalize_ticker(value: str) -> str:
    """Remove espaços (inclusive invisíveis) e põe em maiúsculas, sem mudar a identidade do ticker."""
    s = (value or "").replace("\u00a0", " ").replace("\ufeff", "")
    return re.sub(r"\s+", "", s).upper()


def _clean_number(text: str) -> str:
    s = (text or "").replace("\u00a0", "").replace(" ", "").replace("\ufeff", "")
    s = re.sub(r"^R\$", "", s)
    return s.replace("%", "")


def parse_decimal(text: str) -> Optional[float]:
    """Converte número em formato BR ('92,85') ou internacional ('92.85'). None se vazio/inválido."""
    s = _clean_number(text)
    if not s:
        return None
    if "," in s and "." in s:
        # o ÚLTIMO separador é o decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def parse_count(text: str) -> Optional[int]:
    """Quantidade inteira não negativa ('13', '13.0'). None se vazio, negativo ou fracionário."""
    v = parse_decimal(text)
    if v is None or v < 0 or abs(v - round(v)) > 1e-9:
        return None
    return int(round(v))


def parse_volume(text: str) -> Optional[float]:
    """Volume médio. Regras (documentadas no README):
      * só dígitos                      -> número direto ('314513');
      * grupos de 3 dígitos com pontos  -> milhar BR ('29.869.975', '58.448' = 58448);
      * contém vírgula                  -> padrão BR com decimal ('1.234,5');
      * outro caso com ponto            -> decimal internacional ('572.4').
    """
    s = _clean_number(text)
    if not s:
        return None
    if re.fullmatch(r"\d+", s):
        v = float(s)
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        v = float(s.replace(".", ""))
    else:
        v = parse_decimal(s)
    if v is None or v < 0:
        return None
    return v


# ----------------------------------------------------------------------------- leitura do arquivo
def _decode(raw: bytes) -> Tuple[str, str]:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise DataError("Não foi possível decodificar o arquivo (codificação desconhecida).")


def _detect_delimiter(text: str) -> str:
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    counts = {d: first.count(d) for d in (",", ";", "\t", "|")}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def load_csv(path: str) -> LoadResult:
    """Lê e valida um CSV. Levanta DataError com mensagem clara se o arquivo for inutilizável.
    Nunca altera o arquivo original (abre apenas para leitura)."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise DataError(f"Não foi possível abrir o arquivo:\n{path}\n({exc.strerror or exc})") from exc

    if not raw.strip():
        raise DataError("O arquivo está vazio.")
    if b"\x00" in raw[:2048]:
        raise DataError("O arquivo não parece ser um CSV de texto.")

    text, encoding = _decode(raw)
    delimiter = _detect_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)

    header = next((row for row in reader if any(c.strip() for c in row)), None)
    if header is None:
        raise DataError("O arquivo está vazio.")

    # Mapeia cada coluna necessária para o índice dela no cabeçalho
    norm = [normalize_header(h) for h in header]
    idx: Dict[str, int] = {}
    for key, names in ALIASES.items():
        for i, h in enumerate(norm):
            if h in names:
                idx[key] = i
                break
    missing = [DISPLAY_NAMES[k] for k in ALIASES if k not in idx]
    if missing:
        found = ", ".join(f'"{h}"' for h in header if h.strip()) or "(nenhuma)"
        raise DataError(
            "O arquivo não contém as colunas necessárias: " + ", ".join(missing) + ".\n"
            f"Colunas encontradas: {found}."
        )
    used = set(idx.values())
    extra = [h.strip() for i, h in enumerate(header) if i not in used and h.strip()]

    result = LoadResult(path=path, records=[], total_rows=0, extra_columns=extra,
                        encoding=encoding, delimiter=delimiter)
    by_ticker: Dict[str, List[Record]] = {}
    need = max(idx.values())
    taxa_mismatch: List[str] = []

    for row in reader:
        if not any(c.strip() for c in row):
            continue  # linha totalmente vazia
        result.total_rows += 1
        line = reader.line_num
        if len(row) <= need:
            result.invalid_rows.append((line, "", "linha incompleta (faltam colunas)"))
            continue

        ticker = normalize_ticker(row[idx["ticker"]])
        if not ticker:
            result.invalid_rows.append((line, "", "ticker vazio"))
            continue
        gain = parse_count(row[idx["qtd_gain"]])
        loss = parse_count(row[idx["qtd_loss"]])
        taxa = parse_decimal(row[idx["taxa"]])
        vol = parse_volume(row[idx["volume"]])

        reason = None
        if gain is None:
            reason = "Qtd Gain ausente ou inválida"
        elif loss is None:
            reason = "Qtd Loss ausente ou inválida"
        elif taxa is None or not (0 <= taxa <= 100):
            reason = "Taxa de Acerto ausente ou fora de 0–100"
        elif vol is None:
            reason = "Méd. Volume Leilão ausente ou inválido"
        if reason:
            result.invalid_rows.append((line, ticker, reason))
            continue

        rec = Record(ticker, gain, loss, taxa, vol, line)
        by_ticker.setdefault(ticker, []).append(rec)

        # Consistência: Taxa deveria ser Gain/(Gain+Loss). Só avisa, não altera dados.
        expected = 100.0 * gain / rec.ops if rec.ops else 0.0
        if abs(expected - taxa) > TAXA_TOLERANCE:
            taxa_mismatch.append(ticker)

    # Duplicados: mantém a linha com mais operações (empate: a primeira) e registra o aviso
    for ticker, recs in by_ticker.items():
        if len(recs) > 1:
            result.duplicates.append((ticker, len(recs)))
        result.records.append(max(recs, key=lambda r: (r.ops, -r.line)))
    result.records.sort(key=lambda r: r.line)

    if not result.records:
        raise DataError("Nenhum registro válido foi encontrado no arquivo.")

    if result.invalid_rows:
        result.warnings.append(f"{len(result.invalid_rows)} linha(s) inválida(s) ignorada(s).")
    if result.duplicates:
        lst = ", ".join(f"{t} (x{n})" for t, n in result.duplicates[:8])
        more = "…" if len(result.duplicates) > 8 else ""
        result.warnings.append(
            f"Tickers duplicados: {lst}{more}. Mantida a linha com mais operações de cada um.")
    if taxa_mismatch:
        sample = ", ".join(taxa_mismatch[:6])
        result.warnings.append(
            f"{len(taxa_mismatch)} ticker(s) com Taxa de Acerto diferente de Gain/(Gain+Loss): {sample}. "
            "Os valores do arquivo foram mantidos; a pontuação usa Qtd Gain e Qtd Loss.")
    return result
