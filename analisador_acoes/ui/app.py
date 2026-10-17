"""Janela principal."""
import sys
import tkinter as tk
from tkinter import ttk

from collections import namedtuple
from tkinter import messagebox

from ..core.analysis import resolve_token
from ..core.csv_loader import parse_count, parse_decimal, parse_volume
from ..core.price_service import BrapiClient, PriceError
from ..core.ranking import ScoringConfig
from ..core.settings import load_settings, save_settings
from . import theme
from .tasks import run_in_background
from .compare_tab import CompareTab
from .ranking_tab import RankingTab


PriceOptions = namedtuple("PriceOptions", "token refresh")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self._busy = False
        self._progress_msg = ""
        saved = load_settings()
        self.title("Analisador de Ações — Ranking de Compra e Venda")
        self.geometry("1320x820")
        self.minsize(1050, 650)
        theme.apply_theme(self)

        # Cabeçalho
        head = ttk.Frame(self, style="Header.TFrame", padding=(16, 10))
        head.pack(fill="x")
        ttk.Label(head, text="Analisador de Ações", style="Title.TLabel").pack(anchor="w")
        ttk.Label(head, text="Ranking estatístico de compra e venda · Comparativo entre configurações",
                  style="Subtitle.TLabel").pack(anchor="w")

        # Parâmetros compartilhados pelas duas abas
        par = ttk.Frame(self, padding=(12, 8, 12, 0))
        par.pack(fill="x")
        self.var_volume = tk.StringVar(value="80.000")
        self.var_ops = tk.StringVar(value="10")
        self.var_top = tk.StringVar(value="40")
        for text, var, w in (("Volume mínimo (Méd. Volume Leilão >):", self.var_volume, 11),
                             ("Mín. de operações:", self.var_ops, 5),
                             ("Qtd. no ranking:", self.var_top, 5)):
            ttk.Label(par, text=text).pack(side="left", padx=(0, 4))
            ttk.Entry(par, textvariable=var, width=w).pack(side="left", padx=(0, 16))
        # Valor da ação (online) — opcional; desligado = programa 100% offline
        pr = ttk.Frame(self, padding=(12, 8, 12, 0))
        pr.pack(fill="x")
        self.var_use_price = tk.BooleanVar(value=bool(saved.get("use_price", False)))
        self.var_min_price = tk.StringVar(value=str(saved.get("min_price", "4,00")))
        self.var_token = tk.StringVar(value=str(saved.get("brapi_token", "")))
        self.var_refresh = tk.BooleanVar(value=False)
        ttk.Checkbutton(pr, text="Filtrar pelo valor da ação (online) — valor mínimo R$:",
                        variable=self.var_use_price).pack(side="left")
        ttk.Entry(pr, textvariable=self.var_min_price, width=8).pack(side="left", padx=(4, 16))
        ttk.Label(pr, text="Chave API brapi.dev:").pack(side="left", padx=(0, 4))
        self.entry_token = ttk.Entry(pr, textvariable=self.var_token, width=26, show="•")
        self.entry_token.pack(side="left")
        self.var_show = tk.BooleanVar(value=False)
        ttk.Checkbutton(pr, text="mostrar", variable=self.var_show,
                        command=lambda: self.entry_token.config(show="" if self.var_show.get() else "•")
                        ).pack(side="left", padx=(4, 6))
        ttk.Button(pr, text="Testar chave", command=self.test_key).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(pr, text="Ignorar cache", variable=self.var_refresh).pack(side="left")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        ttk.Label(self, text="Pontuação: 70% taxa de acerto ajustada pela amostra (Wilson 95%) · 20% Qtd Gain · "
                             "10% Qtd Loss (menos perdas é melhor). Volume, operações e valor da ação atuam como filtros.",
                  style="Muted.TLabel").pack(anchor="w", padx=14, pady=(4, 0))

        # Abas principais
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=8)
        nb.add(RankingTab(nb, self), text="  Ranking de Compra e Venda  ")
        nb.add(CompareTab(nb, self), text="  Comparativo de Arquivos  ")

        # Rodapé
        foot = ttk.Frame(self, padding=(12, 0, 12, 8))
        foot.pack(fill="x")
        self.progress = ttk.Progressbar(foot, mode="indeterminate", length=140)
        self.status = ttk.Label(foot, text="Pronto.", style="Muted.TLabel")
        self.status.pack(side="left")
        self.progress.pack(side="right")
        ttk.Label(self, text="Ferramenta de análise estatística sobre dados históricos. Não é recomendação "
                             "de investimento nem garantia de desempenho futuro.",
                  style="Muted.TLabel").pack(side="bottom", pady=(0, 6))

    # ---- API usada pelas abas
    def get_config(self) -> ScoringConfig:
        vol = parse_volume(self.var_volume.get())
        ops = parse_count(self.var_ops.get())
        top = parse_count(self.var_top.get())
        if vol is None:
            raise ValueError("Volume mínimo inválido. Exemplo: 80.000")
        if ops is None or ops < 1:
            raise ValueError("Mínimo de operações inválido (use um inteiro ≥ 1).")
        if top is None or top < 1:
            raise ValueError("Quantidade no ranking inválida (use um inteiro ≥ 1).")
        min_price = None
        if self.var_use_price.get():
            min_price = parse_decimal(self.var_min_price.get())
            if min_price is None or min_price < 0:
                raise ValueError("Valor mínimo da ação inválido. Exemplo: 4,00")
        self.persist_settings()
        return ScoringConfig(min_volume=vol, min_ops=ops, top_n=top, min_price=min_price)

    def price_options(self):
        """None se o filtro de valor da ação está desligado; senão PriceOptions(token, refresh).
        Levanta ValueError se faltar a chave da API."""
        if not self.var_use_price.get():
            return None
        token = resolve_token(self.var_token.get())
        if not token:
            raise ValueError("Informe a chave da API do brapi.dev para filtrar pelo valor da ação "
                             "(ou desmarque o filtro).")
        return PriceOptions(token, bool(self.var_refresh.get()))

    def persist_settings(self):
        save_settings({"use_price": bool(self.var_use_price.get()),
                       "min_price": self.var_min_price.get().strip(),
                       "brapi_token": self.var_token.get().strip()})

    def _on_close(self):
        self.persist_settings()
        self.destroy()

    def test_key(self):
        token = resolve_token(self.var_token.get())
        if not token:
            messagebox.showwarning("Chave ausente", "Cole a chave da API do brapi.dev no campo ao lado.")
            return

        def work():
            return BrapiClient(token).fetch("PETR4")

        def done(price):
            self.set_busy(False)
            if price is None:
                messagebox.showwarning("Teste da chave", "A chave foi aceita, mas não veio cotação de PETR4.")
            else:
                self.set_status("Chave da API funcionando.")
                valor = f"{price:.2f}".replace(".", ",")
                messagebox.showinfo("Teste da chave", f"Chave OK. PETR4 está em R$ {valor}")

        def failed(exc):
            self.set_busy(False)
            msg = str(exc) if isinstance(exc, PriceError) else f"{type(exc).__name__}: {exc}"
            self.set_status("Falha ao testar a chave.", error=True)
            messagebox.showerror("Teste da chave", msg)

        self.set_busy(True, "Testando chave da API…")
        run_in_background(self, work, done, failed)

    def report_progress(self, msg: str):
        """Pode ser chamado de outra thread: só guarda o texto; a janela o exibe no próximo ciclo."""
        self._progress_msg = msg

    def set_busy(self, busy: bool, msg: str = ""):
        self._busy = busy
        if busy:
            self._progress_msg = msg
            self.status.config(text=msg, style="Muted.TLabel")
            self.progress.start(12)
            self.after(150, self._poll_progress)
        else:
            self.progress.stop()

    def _poll_progress(self):
        if self._busy:
            self.status.config(text=self._progress_msg, style="Muted.TLabel")
            self.after(150, self._poll_progress)

    def set_status(self, msg: str, error: bool = False):
        self.status.config(text=msg, style="Err.TLabel" if error else "Muted.TLabel")


def run():
    if sys.platform.startswith("win"):
        try:  # nitidez em telas com escala > 100%
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    App().mainloop()
