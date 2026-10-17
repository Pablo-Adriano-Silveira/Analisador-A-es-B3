"""Preço atual da ação via brapi.dev (plano gratuito: 1 ticker por chamada, atraso de ~30 min).

Endpoint:  GET https://brapi.dev/api/v2/stocks/quote?symbols=PETR4
Cabeçalho: Authorization: Bearer <chave>
Resposta:  {"results": [{"data": {"symbol": "PETR4", "regularMarketPrice": 38.5, ...}}]}

Regras de segurança dos dados:
  * preço ausente/inválido NUNCA vira zero: o ticker fica "sem cotação";
  * consultas feitas UMA DE CADA VEZ (o brapi limita chamadas simultâneas; excesso gera 429);
  * 429: espera o tempo do cabeçalho Retry-After e tenta de novo (até 4 vezes); se persistir, interrompe;
  * erros de chave (401/403), limite persistente (429) e de rede interrompem a consulta inteira
    (não se monta ranking com preços pela metade);
  * apenas preços obtidos com sucesso entram no cache local (validade de 6 horas).
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, Optional, Tuple

from .settings import config_dir

API_URL = "https://brapi.dev/api/v2/stocks/quote"
CACHE_TTL_SECONDS = 6 * 3600
MAX_429_RETRIES = 4


class PriceError(Exception):
    """Falha que impede a consulta de preços (mensagem pronta para o usuário)."""


class AuthError(PriceError):
    pass


class QuotaError(PriceError):
    pass


class NetworkError(PriceError):
    pass


def _default_fetch(url: str, token: str, timeout: float):
    """Retorna (status, corpo, cabeçalhos em minúsculas)."""
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/json",
        "User-Agent": "AnalisadorAcoes/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:               # 4xx/5xx chegam aqui, com status
        try:
            body = exc.read()
        except Exception:                               # noqa: BLE001
            body = b""
        hdrs = {k.lower(): v for k, v in exc.headers.items()} if getattr(exc, "headers", None) else {}
        return exc.code, body, hdrs
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise NetworkError(f"Sem conexão com o brapi.dev ({reason}). Verifique a internet.") from exc


def parse_price(body: bytes, ticker: str) -> Optional[float]:
    """Extrai regularMarketPrice da resposta. None se faltar, for inválido ou for de outro ticker."""
    try:
        obj = json.loads(body.decode("utf-8"))
        results = obj.get("results")
        first = results[0] if isinstance(results, list) and results else None
        if not isinstance(first, dict):
            return None
        data = first.get("data") if isinstance(first.get("data"), dict) else first
        sym = data.get("symbol")
        if isinstance(sym, str) and sym.strip().upper() != ticker.upper():
            return None
        price = float(data.get("regularMarketPrice"))
    except (ValueError, TypeError, AttributeError, UnicodeDecodeError):
        return None
    return price if math.isfinite(price) and price > 0 else None


def _retry_after(headers: dict, attempt: int) -> float:
    """Segundos de espera após um 429: usa Retry-After se vier; senão, espera crescente (2s, 4s, 6s...)."""
    try:
        wait = float(headers.get("retry-after"))
    except (TypeError, ValueError):
        wait = 2.0 * attempt
    return min(max(wait, 0.5), 30.0)


class BrapiClient:
    def __init__(self, token: str, fetch: Optional[Callable] = None, timeout: float = 12.0,
                 sleep: Callable[[float], None] = time.sleep,
                 notify: Optional[Callable[[str], None]] = None):
        if not (token or "").strip():
            raise AuthError("Informe a chave da API do brapi.dev.")
        self.token = token.strip()
        self._fetch = fetch
        self.timeout = timeout
        self._sleep = sleep
        self.notify = notify          # recebe mensagens de espera (ex.: "aguardando 5s")

    def fetch(self, ticker: str) -> Optional[float]:
        """Preço do ticker; None se a API não tiver cotação. Levanta PriceError nos erros fatais."""
        url = f"{API_URL}?symbols={urllib.parse.quote(ticker)}"
        fetch = self._fetch or _default_fetch            # buscado na hora (permite substituir nos testes)
        limited = server_errors = 0
        while True:
            res = fetch(url, self.token, self.timeout)
            status, body = res[0], res[1]
            headers = res[2] if len(res) > 2 else {}
            if status == 200:
                return parse_price(body, ticker)
            if status == 401:
                raise AuthError("Chave da API inválida ou ausente (erro 401). Confira a chave no painel do brapi.dev.")
            if status == 403:
                raise AuthError("Acesso negado pela API (erro 403). A chave/plano não permite esta consulta.")
            if status == 429:
                limited += 1
                if limited > MAX_429_RETRIES:
                    raise QuotaError(
                        "O brapi.dev recusou a consulta (erro 429): cota mensal esgotada, limite de chamadas "
                        "simultâneas ou limite do plano. Aguarde alguns minutos e tente de novo, ou confira o "
                        "consumo no painel do brapi.dev.")
                wait = _retry_after(headers, limited)
                if self.notify:
                    self.notify(f"Limite da API (429): aguardando {wait:.0f}s e tentando de novo "
                                f"({limited}/{MAX_429_RETRIES})…")
                self._sleep(wait)
                continue
            if status == 404:
                return None
            if status >= 500:
                server_errors += 1
                if server_errors > 1:
                    return None
                self._sleep(0.5)
                continue
            return None


class PriceCache:
    """Cache em disco ticker -> (preço, instante). Só guarda consultas bem-sucedidas."""

    def __init__(self, path: Optional[str] = None, ttl: float = CACHE_TTL_SECONDS,
                 now: Callable[[], float] = time.time):
        self.path = path or os.path.join(config_dir(), "price_cache.json")
        self.ttl, self._now = ttl, now
        self._data: Dict[str, Tuple[float, float]] = {}
        try:
            with open(self.path, encoding="utf-8") as fh:
                raw = json.load(fh)
            for t, (p, ts) in raw.items():
                self._data[str(t)] = (float(p), float(ts))
        except (OSError, ValueError, TypeError):
            self._data = {}

    def get(self, ticker: str) -> Optional[float]:
        item = self._data.get(ticker)
        if item and self._now() - item[1] <= self.ttl:
            return item[0]
        return None

    def put(self, ticker: str, price: float) -> None:
        self._data[ticker] = (price, self._now())

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump({t: list(v) for t, v in self._data.items()}, fh)
        except OSError:
            pass


@dataclass
class PriceBatch:
    prices: Dict[str, float] = field(default_factory=dict)
    missing: Dict[str, str] = field(default_factory=dict)   # ticker -> motivo (sem cotação)
    fatal: Optional[str] = None                              # erro que interrompeu a consulta
    from_cache: int = 0
    fetched: int = 0


def fetch_prices(tickers: Iterable[str], client: BrapiClient, cache: PriceCache,
                 progress: Optional[Callable[[int, int], None]] = None,
                 workers: int = 1, refresh: bool = False) -> PriceBatch:
    """Consulta os preços (cache primeiro). Erros fatais abortam o restante das consultas."""
    tickers = sorted(set(tickers))
    batch = PriceBatch()
    todo = []
    for t in tickers:
        cached = None if refresh else cache.get(t)
        if cached is not None:
            batch.prices[t] = cached
            batch.from_cache += 1
        else:
            todo.append(t)
    total, done = len(tickers), batch.from_cache
    if progress:
        progress(done, total)

    abort = threading.Event()

    def job(t: str):
        if abort.is_set():
            return t, None, "skipped"
        try:
            return t, client.fetch(t), None
        except PriceError as exc:
            abort.set()
            return t, None, exc

    if todo:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            for fut in as_completed([ex.submit(job, t) for t in todo]):
                t, price, err = fut.result()
                done += 1
                if isinstance(err, PriceError):
                    batch.fatal = batch.fatal or str(err)
                elif err == "skipped":
                    pass
                elif price is None:
                    batch.missing[t] = "sem cotação na API"
                else:
                    batch.prices[t] = price
                    batch.fetched += 1
                    cache.put(t, price)
                if progress:
                    progress(done, total)
        cache.save()
    return batch
