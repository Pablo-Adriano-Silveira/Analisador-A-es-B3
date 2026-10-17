"""Aba 1 — Ranking de Compra e Venda."""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, Optional, Tuple

from ..core.csv_loader import load_csv
from ..core.exporter import export_csv, export_xlsx
from ..core.analysis import gather_prices
from ..core.formatting import fmt_dec, fmt_int
from ..core.models import DataError, LoadResult
from ..core.ranking import RankingResult, rank_records
from ..core.tables import (EXCLUDED_COLUMNS, RANKING_COLUMNS, excluded_rows, ranking_rows)
from .tasks import run_in_background
from .widgets import DataTable, FilePicker
from . import theme

SIDES = ("Compra", "Venda")


class _SidePane(ttk.Frame):
    """Resumo + avisos + tabela de um dos lados (compra ou venda)."""

    def __init__(self, parent, side: str, tab: "RankingTab"):
        super().__init__(parent, padding=8)
        self.side, self.tab = side, tab
        self.summary = ttk.Label(self, text="Selecione o arquivo e clique em Analisar.",
                                 style="Summary.TLabel", justify="left", wraplength=1100)
        self.summary.grid(row=0, column=0, sticky="ew")
        self.warn = ttk.Label(self, text="", style="Warn.TLabel", justify="left", wraplength=1100)
        self.warn.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self.btn_excl = ttk.Button(self, text="Ver ações excluídas…", command=self.show_excluded,
                                   state="disabled")
        self.btn_excl.grid(row=0, column=1, rowspan=2, sticky="e", padx=(8, 0))
        self.table = DataTable(self, RANKING_COLUMNS)
        self.table.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

    def show_result(self, load: LoadResult, res: RankingResult):
        cfg = res.config
        lines = [
            f"Arquivo: {os.path.basename(load.path)}   |   Linhas lidas: {fmt_int(load.total_rows)}   |   "
            f"Ações analisadas: {fmt_int(res.total)}",
            f"Volume > {fmt_int(cfg.min_volume)}: {fmt_int(res.volume_ok)} aprovadas   |   "
            f"Excluídas por volume: {fmt_int(len(res.excluded_volume))}   |   "
            f"Excluídas por mín. de {cfg.min_ops} operações / sem Gain: {fmt_int(len(res.excluded_filters))}",
            f"Elegíveis ao ranking: {fmt_int(res.eligible)}   |   Exibidas: {fmt_int(len(res.rows))}",
        ]
        if cfg.min_price is not None:
            lines.insert(2, f"Valor da ação ≥ R$ {fmt_dec(cfg.min_price)}: reprovadas por valor abaixo do mínimo: "
                            f"{fmt_int(res.price_low)}   |   sem cotação: {fmt_int(res.price_missing)}")
        self.summary.config(text="\n".join(lines))
        warns = list(load.warnings)
        if res.eligible < cfg.top_n:
            warns.append(f"Atenção: apenas {res.eligible} ação(ões) elegível(is) — menos que as {cfg.top_n} "
                         "solicitadas. A lista não foi completada com ações que não atendem aos filtros.")
        self.warn.config(text="\n".join(warns))
        self.table.set_rows(ranking_rows(res))
        self.btn_excl.config(state="normal")

    def show_error(self, msg: str):
        self.summary.config(text="Não foi possível analisar este arquivo.")
        self.warn.config(text=msg)
        self.table.clear()
        self.btn_excl.config(state="disabled")

    def show_excluded(self):
        got = self.tab.results.get(self.side)
        if not got:
            return
        win = tk.Toplevel(self)
        win.title(f"Ações excluídas — {self.side}")
        win.geometry("760x480")
        win.configure(bg=theme.BG)
        t = DataTable(win, EXCLUDED_COLUMNS)
        t.pack(fill="both", expand=True, padx=8, pady=8)
        t.set_rows(excluded_rows(got[1]))


class RankingTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        self.results: Dict[str, Tuple[LoadResult, RankingResult]] = {}

        box = ttk.Frame(self, style="Card.TFrame", padding=10)
        box.pack(fill="x")
        self.pick = {
            "Compra": FilePicker(box, "Arquivo de Compra:", card=True),
            "Venda": FilePicker(box, "Arquivo de Venda:", card=True),
        }
        self.pick["Compra"].grid(row=0, column=0, sticky="ew", pady=2)
        self.pick["Venda"].grid(row=1, column=0, sticky="ew", pady=2)
        box.columnconfigure(0, weight=1)

        bar = ttk.Frame(box, style="CardInner.TFrame")
        bar.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.btn_run = ttk.Button(bar, text="Analisar", style="Accent.TButton", command=self.analyze)
        self.btn_run.pack(side="left")
        self.btn_csv = ttk.Button(bar, text="Exportar CSV", command=self.export_csv, state="disabled")
        self.btn_csv.pack(side="left", padx=(16, 4))
        self.btn_xlsx = ttk.Button(bar, text="Exportar Excel", command=self.export_xlsx, state="disabled")
        self.btn_xlsx.pack(side="left")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, pady=(10, 0))
        self.panes: Dict[str, _SidePane] = {}
        for side in SIDES:
            pane = _SidePane(self.nb, side, self)
            self.panes[side] = pane
            self.nb.add(pane, text=f"  {side}  ")

    # ------------------------------------------------------------------ análise
    def analyze(self):
        paths = {s: self.pick[s].get() for s in SIDES if self.pick[s].get()}
        if not paths:
            messagebox.showwarning("Nenhum arquivo", "Selecione pelo menos um arquivo (compra e/ou venda).")
            return
        try:
            cfg = self.app.get_config()
            price_opts = self.app.price_options()
        except ValueError as exc:
            messagebox.showerror("Parâmetros inválidos", str(exc))
            return

        def work():
            loads, out = {}, {}
            for side, path in paths.items():
                try:
                    loads[side] = load_csv(path)
                except DataError as exc:
                    out[side] = ("err", str(exc))
            prices = None
            if price_opts and loads:
                prices = gather_prices(
                    [ld.records for ld in loads.values()], cfg, price_opts.token, price_opts.refresh,
                    progress=lambda d, t: self.app.report_progress(f"Buscando preços online… {d}/{t}"),
                    notify=self.app.report_progress)
            for side, load in loads.items():
                out[side] = ("ok", load, rank_records(load.records, cfg, prices))
            return out

        self.app.set_busy(True, "Analisando arquivos…")
        run_in_background(self, work, self._done, self._failed)

    def _done(self, out):
        self.app.set_busy(False)
        errors = []
        for side in SIDES:
            if side not in out:
                continue
            item = out[side]
            if item[0] == "ok":
                self.results[side] = (item[1], item[2])
                self.panes[side].show_result(item[1], item[2])
            else:
                self.results.pop(side, None)
                self.panes[side].show_error(item[1])
                errors.append(f"{side}: {item[1]}")
        has = bool(self.results)
        for b in (self.btn_csv, self.btn_xlsx):
            b.config(state="normal" if has else "disabled")
        if errors:
            self.app.set_status("Erro ao ler arquivo(s).", error=True)
            messagebox.showerror("Arquivo inválido", "\n\n".join(errors))
        else:
            self.app.set_status("Análise concluída.")

    def _failed(self, exc):
        self.app.set_busy(False)
        if isinstance(exc, DataError):
            self.app.set_status("Falha ao obter os preços.", error=True)
            messagebox.showerror("Falha ao obter os preços", str(exc))
            return
        self.app.set_status("Erro inesperado.", error=True)
        messagebox.showerror("Erro inesperado", f"{type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------ exportação
    def export_csv(self):
        if not self.results:
            return
        path = filedialog.asksaveasfilename(title="Exportar rankings (CSV)", defaultextension=".csv",
                                            initialfile="ranking.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        base, ext = os.path.splitext(path)
        written = []
        try:
            for side, (_load, res) in self.results.items():
                target = f"{base}_{side.lower()}{ext or '.csv'}"
                export_csv(target, RANKING_COLUMNS, ranking_rows(res))
                written.append(target)
        except DataError as exc:
            messagebox.showerror("Falha ao exportar", str(exc))
            return
        messagebox.showinfo("Exportação concluída", "Arquivos gerados:\n" + "\n".join(written))

    def export_xlsx(self):
        if not self.results:
            return
        path = filedialog.asksaveasfilename(title="Exportar rankings (Excel)", defaultextension=".xlsx",
                                            initialfile="ranking.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        sheets, summary = [], []
        for side, (load, res) in self.results.items():
            sheets.append((side, RANKING_COLUMNS, ranking_rows(res)))
            c = res.config
            summary += [
                (f"[{side}] Arquivo", os.path.basename(load.path)),
                (f"[{side}] Ações analisadas", res.total),
                (f"[{side}] Aprovadas no filtro de volume (> {fmt_int(c.min_volume)})", res.volume_ok),
                (f"[{side}] Excluídas por volume", len(res.excluded_volume)),
                (f"[{side}] Excluídas por mín. de {c.min_ops} operações / sem Gain", len(res.excluded_filters)),
                *(([(f"[{side}] Reprovadas por valor da ação (< R$ {fmt_dec(c.min_price)})", res.price_low),
                    (f"[{side}] Sem cotação", res.price_missing)]) if c.min_price is not None else []),
                (f"[{side}] Elegíveis", res.eligible),
                (f"[{side}] Exibidas", len(res.rows)),
            ]
        summary.append(("Pontuação", "70% taxa ajustada (Wilson 95%) + 20% Qtd Gain + 10% Qtd Loss (menos é melhor)"))
        try:
            export_xlsx(path, sheets, summary)
        except DataError as exc:
            messagebox.showerror("Falha ao exportar", str(exc))
            return
        messagebox.showinfo("Exportação concluída", f"Arquivo gerado:\n{path}")
