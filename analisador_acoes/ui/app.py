"""Janela principal."""
import sys
import tkinter as tk
from tkinter import ttk

from ..core.csv_loader import parse_count, parse_volume
from ..core.ranking import ScoringConfig
from . import theme
from .compare_tab import CompareTab
from .ranking_tab import RankingTab


class App(tk.Tk):
    def __init__(self):
        super().__init__()
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
        ttk.Label(self, text="Pontuação: 70% taxa de acerto ajustada pela amostra (Wilson 95%) · 20% Qtd Gain · "
                             "10% Qtd Loss (menos perdas é melhor). Volume e mín. de operações atuam como filtros.",
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
        return ScoringConfig(min_volume=vol, min_ops=ops, top_n=top)

    def set_busy(self, busy: bool, msg: str = ""):
        if busy:
            self.status.config(text=msg, style="Muted.TLabel")
            self.progress.start(12)
        else:
            self.progress.stop()

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
