"""Aba 2 — Comparativo de Arquivos (2% x 1%), compra e venda separados."""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

from ..core.comparison import SORT_OPTIONS, ComparisonResult, compare, sort_matches
from ..core.csv_loader import load_csv
from ..core.exporter import export_csv, export_xlsx
from ..core.models import DataError
from ..core.tables import comparison_columns, comparison_rows, comparison_summary
from .tasks import run_in_background
from .widgets import DataTable, FilePicker

LABEL_A, LABEL_B = "2%", "1%"


class _ComparePane(ttk.Frame):
    def __init__(self, parent, side: str, app):
        super().__init__(parent, padding=8)
        self.side, self.app = side, app
        self.result: Optional[ComparisonResult] = None
        self.columns = comparison_columns(LABEL_A, LABEL_B)

        box = ttk.Frame(self, style="Card.TFrame", padding=10)
        box.pack(fill="x")
        art = "Compra" if side == "Compra" else "Venda"
        self.pick_a = FilePicker(box, f"Arquivo de {art} — configuração de {LABEL_A}:", label_width=44, card=True)
        self.pick_b = FilePicker(box, f"Arquivo de {art} — configuração de {LABEL_B}:", label_width=44, card=True)
        self.pick_a.grid(row=0, column=0, sticky="ew", pady=2)
        self.pick_b.grid(row=1, column=0, sticky="ew", pady=2)
        box.columnconfigure(0, weight=1)

        opt = ttk.Frame(box, style="CardInner.TFrame")
        opt.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(opt, text="Limitar aos N melhores de cada arquivo (0 = todos os elegíveis):",
                  style="Card.TLabel").pack(side="left")
        self.var_limit = tk.StringVar(value="0")
        ttk.Spinbox(opt, from_=0, to=500, width=6, textvariable=self.var_limit).pack(side="left", padx=6)
        ttk.Label(opt, text="Ordenar por:", style="Card.TLabel").pack(side="left", padx=(16, 4))
        self.var_sort = tk.StringVar(value="Nota média")
        names = [n.replace("(A)", f"({LABEL_A})").replace("(B)", f"({LABEL_B})") for n in SORT_OPTIONS]
        self._sort_map = dict(zip(names, SORT_OPTIONS))
        cb = ttk.Combobox(opt, textvariable=self.var_sort, values=names, state="readonly", width=26)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda _e: self._refresh_table())

        bar = ttk.Frame(box, style="CardInner.TFrame")
        bar.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.btn_run = ttk.Button(bar, text="Comparar", style="Accent.TButton", command=self.run)
        self.btn_run.pack(side="left")
        self.btn_csv = ttk.Button(bar, text="Exportar CSV", command=self.export_csv, state="disabled")
        self.btn_csv.pack(side="left", padx=(16, 4))
        self.btn_xlsx = ttk.Button(bar, text="Exportar Excel", command=self.export_xlsx, state="disabled")
        self.btn_xlsx.pack(side="left")

        self.summary = ttk.Label(self, text="", style="Summary.TLabel", justify="left", wraplength=1100)
        self.summary.pack(fill="x", pady=(8, 0))
        self.notes = ttk.Label(self, text="", style="Warn.TLabel", justify="left", wraplength=1100)
        self.notes.pack(fill="x")
        self.table = DataTable(self, self.columns)
        self.table.pack(fill="both", expand=True, pady=(6, 0))

    # ------------------------------------------------------------------
    def run(self):
        pa, pb = self.pick_a.get(), self.pick_b.get()
        if not pa or not pb:
            messagebox.showwarning("Arquivos faltando",
                                   f"Selecione os dois arquivos de {self.side.lower()} ({LABEL_A} e {LABEL_B}).")
            return
        if os.path.abspath(pa) == os.path.abspath(pb):
            messagebox.showwarning("Mesmo arquivo", "Os dois campos apontam para o mesmo arquivo.")
            return
        try:
            cfg = self.app.get_config()
            limit = int(self.var_limit.get().strip() or "0")
            if limit < 0:
                raise ValueError
        except ValueError as exc:
            messagebox.showerror("Parâmetros inválidos",
                                 str(exc) or "O limite de melhores deve ser um número inteiro ≥ 0.")
            return

        def work():
            return compare(load_csv(pa), load_csv(pb), cfg, LABEL_A, LABEL_B, limit)

        self.app.set_busy(True, f"Comparando arquivos de {self.side.lower()}…")
        run_in_background(self, work, self._done, self._failed)

    def _done(self, res: ComparisonResult):
        self.app.set_busy(False)
        self.result = res
        s = " | ".join(f"{k}: {v}" for k, v in comparison_summary(res))
        self.summary.config(text=s)
        self.notes.config(text="\n".join(res.notes))
        self._refresh_table()
        for b in (self.btn_csv, self.btn_xlsx):
            b.config(state="normal")
        self.app.set_status(f"Comparativo de {self.side.lower()} concluído: {len(res.matches)} match(es).")

    def _failed(self, exc):
        self.app.set_busy(False)
        if isinstance(exc, DataError):
            self.app.set_status("Arquivo inválido.", error=True)
            messagebox.showerror("Arquivo inválido", str(exc))
        else:
            self.app.set_status("Erro inesperado.", error=True)
            messagebox.showerror("Erro inesperado", f"{type(exc).__name__}: {exc}")

    def _sorted_matches(self):
        if not self.result:
            return []
        option = self._sort_map.get(self.var_sort.get(), "Nota média")
        return sort_matches(self.result.matches, option)

    def _refresh_table(self):
        if self.result:
            self.table.set_rows(comparison_rows(self._sorted_matches()))

    # ------------------------------------------------------------------ exportação
    def export_csv(self):
        if not self.result:
            return
        path = filedialog.asksaveasfilename(title="Exportar comparativo (CSV)", defaultextension=".csv",
                                            initialfile=f"comparativo_{self.side.lower()}.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            export_csv(path, self.columns, comparison_rows(self._sorted_matches()))
        except DataError as exc:
            messagebox.showerror("Falha ao exportar", str(exc))
            return
        messagebox.showinfo("Exportação concluída", f"Arquivo gerado:\n{path}")

    def export_xlsx(self):
        if not self.result:
            return
        path = filedialog.asksaveasfilename(title="Exportar comparativo (Excel)", defaultextension=".xlsx",
                                            initialfile=f"comparativo_{self.side.lower()}.xlsx",
                                            filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        try:
            export_xlsx(path, [(f"Matches {self.side}", self.columns, comparison_rows(self._sorted_matches()))],
                        comparison_summary(self.result))
        except DataError as exc:
            messagebox.showerror("Falha ao exportar", str(exc))
            return
        messagebox.showinfo("Exportação concluída", f"Arquivo gerado:\n{path}")


class CompareTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        for side in ("Compra", "Venda"):
            nb.add(_ComparePane(nb, side, app), text=f"  {side}  ")
