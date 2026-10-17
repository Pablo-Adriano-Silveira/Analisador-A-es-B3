"""Componentes reutilizáveis: seletor de arquivo e tabela ordenável com rolagem."""
import os
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any, Dict, List, Optional, Sequence

from ..core.formatting import fmt_value
from ..core.tables import Column
from . import theme

_last_dir = {"path": ""}


class FilePicker(ttk.Frame):
    """Rótulo + campo (somente leitura) + botão 'Selecionar…'."""

    def __init__(self, parent, label: str, label_width: int = 26, **kw):
        super().__init__(parent, style="CardInner.TFrame" if kw.pop("card", False) else "TFrame", **kw)
        self.var = tk.StringVar()
        self._label = label
        ttk.Label(self, text=label, style="Card.TLabel", width=label_width, anchor="w").grid(row=0, column=0, sticky="w")
        self.entry = ttk.Entry(self, textvariable=self.var, state="readonly")
        self.entry.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(self, text="Selecionar…", command=self.choose).grid(row=0, column=2)
        ttk.Button(self, text="✕", width=3, command=lambda: self.var.set("")).grid(row=0, column=3, padx=(4, 0))
        self.columnconfigure(1, weight=1)

    def choose(self):
        path = filedialog.askopenfilename(
            title=self._label, initialdir=_last_dir["path"] or None,
            filetypes=[("Arquivos CSV", "*.csv"), ("Todos os arquivos", "*.*")])
        if path:
            _last_dir["path"] = os.path.dirname(path)
            self.var.set(path)

    def get(self) -> str:
        return self.var.get().strip()


class DataTable(ttk.Frame):
    """Tabela com rolagem vertical/horizontal, linhas zebradas e ordenação por clique no cabeçalho."""

    def __init__(self, parent, columns: Sequence[Column]):
        super().__init__(parent)
        self.columns = list(columns)
        self._rows: Dict[str, Dict[str, Any]] = {}
        self._sort_key: Optional[str] = None
        self._sort_desc = False

        ids = [c.key for c in self.columns]
        self.tree = ttk.Treeview(self, columns=ids, show="headings", selectmode="browse")
        vs = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hs = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.tree.tag_configure("odd", background=theme.ZEBRA)
        self._build_headings()

    def _build_headings(self):
        for c in self.columns:
            arrow = ""
            if c.key == self._sort_key:
                arrow = " ▼" if self._sort_desc else " ▲"
            self.tree.heading(c.key, text=c.title + arrow, command=lambda k=c.key: self._on_header(k))
            self.tree.column(c.key, width=c.width, minwidth=c.width, anchor=c.anchor, stretch=True)

    def set_columns(self, columns: Sequence[Column]):
        self.columns = list(columns)
        self.tree.configure(columns=[c.key for c in self.columns])
        self._sort_key = None
        self._build_headings()

    def set_rows(self, rows: List[Dict[str, Any]]):
        """Substitui o conteúdo. Mantém os valores brutos para ordenar numericamente."""
        self.tree.delete(*self.tree.get_children())
        self._rows = {}
        self._sort_key = None
        self._build_headings()
        for i, row in enumerate(rows):
            iid = str(i)
            self._rows[iid] = row
            self._insert(iid, row, i)

    def _insert(self, iid: str, row: Dict[str, Any], i: int):
        vals = [fmt_value(c.kind, row.get(c.key)) for c in self.columns]
        self.tree.insert("", "end", iid=iid, values=vals, tags=("odd",) if i % 2 else ())

    def _on_header(self, key: str):
        self._sort_desc = (not self._sort_desc) if self._sort_key == key else False
        self._sort_key = key
        # valores ausentes vão sempre para o fim
        present = sorted(((i, r) for i, r in self._rows.items() if r.get(key) is not None),
                         key=lambda t: t[1][key], reverse=self._sort_desc)
        absent = [(i, r) for i, r in self._rows.items() if r.get(key) is None]
        for pos, (iid, _row) in enumerate(present + absent):
            self.tree.move(iid, "", pos)
            self.tree.item(iid, tags=("odd",) if pos % 2 else ())
        self._build_headings()

    def clear(self):
        self.set_rows([])
