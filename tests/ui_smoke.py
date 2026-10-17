"""Teste de fumaça da interface (precisa de display; no Linux use: xvfb-run -a python tests/ui_smoke.py).
Simula o uso: seleciona arquivos, analisa, compara, ordena e exporta, sem abrir diálogos reais."""
import os
import sys
import tempfile
import time
import tkinter as tk
from tkinter import filedialog, messagebox

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
SD = os.path.join(ROOT, "sample_data")
shots = sys.argv[1] if len(sys.argv) > 1 else None

popups = []
for name in ("showinfo", "showwarning", "showerror"):
    setattr(messagebox, name, lambda t, m, _n=name, **k: popups.append((_n, t, m)))

from analisador_acoes.ui.app import App  # noqa: E402


def pump(app, cond, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        app.update()
        if cond():
            return True
        time.sleep(0.02)
    return False


def snap(app, name):
    if not shots:
        return
    try:
        from PIL import ImageGrab
        app.update(); time.sleep(0.3); app.update()
        x, y, w, h = app.winfo_rootx(), app.winfo_rooty(), app.winfo_width(), app.winfo_height()
        ImageGrab.grab(bbox=(x, y, x + w, y + h), xdisplay=os.environ.get("DISPLAY")).save(os.path.join(shots, name))
    except Exception as exc:  # noqa: BLE001
        print("sem screenshot:", exc)


app = App()
app.update()
nb = app.winfo_children()
main_nb = [w for w in app.winfo_children() if w.winfo_class() == "TNotebook"][0]
rank_tab, cmp_tab = main_nb.winfo_children()[0], main_nb.winfo_children()[1]

# ---- Aba 1
rank_tab.pick["Compra"].var.set(os.path.join(SD, "2pct_compra.csv"))
rank_tab.pick["Venda"].var.set(os.path.join(SD, "2pct_venda.csv"))
rank_tab.analyze()
assert pump(app, lambda: len(rank_tab.results) == 2), "análise não terminou"
pc = rank_tab.panes["Compra"]
assert len(pc.table.tree.get_children()) == 40
first = pc.table.tree.item(pc.table.tree.get_children()[0])["values"]
print("Compra linha 1:", first)
assert first[1] == "VTRU3"
print("Resumo:", pc.summary.cget("text").replace("\n", " || "))
pc.table._on_header("taxa")                       # ordenar por taxa
pc.table._on_header("taxa")                       # desc
top = pc.table.tree.item(pc.table.tree.get_children()[0])["values"]
print("Ordenado por taxa desc:", top[:3])
snap(app, "aba1_compra.png")
rank_tab.nb.select(1); app.update(); snap(app, "aba1_venda.png")

d = tempfile.mkdtemp()
filedialog.asksaveasfilename = lambda **k: os.path.join(d, "rk" + (".xlsx" if "xlsx" in k.get("defaultextension", "") else ".csv"))
rank_tab.export_csv(); rank_tab.export_xlsx()
print("Exportados:", sorted(os.listdir(d)))

# arquivo inválido
bad = os.path.join(d, "ruim.csv"); open(bad, "w").write("a,b\n1,2\n")
rank_tab.pick["Compra"].var.set(bad); rank_tab.pick["Venda"].var.set("")
rank_tab.analyze(); pump(app, lambda: any(p[0] == "showerror" for p in popups))
print("Erro amigável:", [p for p in popups if p[0] == "showerror"][-1][2][:120].replace("\n", " "))

# ---- Aba 2
main_nb.select(1); app.update()
cmp_nb = cmp_tab.winfo_children()[0]
pane = cmp_nb.winfo_children()[0]
pane.pick_a.var.set(os.path.join(SD, "2pct_compra.csv")); pane.pick_b.var.set(os.path.join(SD, "1pct_compra.csv"))
pane.run()
assert pump(app, lambda: pane.result is not None), "comparação não terminou"
print("Matches compra:", len(pane.result.matches), "| linhas na tabela:", len(pane.table.tree.get_children()))
pane.var_sort.set("Taxa de acerto (1%)"); pane._refresh_table()
print("Ordenado por taxa 1%:", pane.table.tree.item(pane.table.tree.get_children()[0])["values"][:5])
pane.var_sort.set("Nota média"); pane._refresh_table()
snap(app, "aba2_compra.png")
filedialog.asksaveasfilename = lambda **k: os.path.join(d, "cmp.csv")
pane.export_csv()
print("Comparativo CSV existe:", os.path.exists(os.path.join(d, "cmp.csv")))
# mesmo arquivo nos dois campos
pane.pick_b.var.set(pane.pick_a.get()); pane.run()
print("Aviso mesmo arquivo:", popups[-1][1])
app.destroy()
print("UI OK")
