"""Teste de fumaça da interface com o filtro de valor da ação (API simulada, sem internet).
Uso: xvfb-run -a python tests/ui_smoke_price.py [pasta_para_screenshots]"""
import json
import os
import sys
import tempfile
import time
from tkinter import filedialog, messagebox

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["ANALISADOR_ACOES_HOME"] = tempfile.mkdtemp()          # não mexe nas configurações reais
SD = os.path.join(ROOT, "sample_data")
shots = sys.argv[1] if len(sys.argv) > 1 else None

popups = []
for name in ("showinfo", "showwarning", "showerror"):
    setattr(messagebox, name, lambda t, m, _n=name, **k: popups.append((_n, t, m)))

from analisador_acoes.core import price_service  # noqa: E402
from analisador_acoes.ui.app import App  # noqa: E402

calls = []
mode = {"status": 200}


def fake_fetch(url, token, timeout):
    sym = url.split("symbols=")[1]
    calls.append((sym, token))
    if mode["status"] != 200:
        return mode["status"], b"{}"
    price = 1.5 + (sum(map(ord, sym)) % 12)                       # 1,50 .. 12,50 (determinístico)
    return 200, json.dumps({"results": [{"data": {"symbol": sym, "regularMarketPrice": price}}]}).encode()


price_service._default_fetch = fake_fetch


def pump(app, cond, timeout=15):
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
main_nb = [w for w in app.winfo_children() if w.winfo_class() == "TNotebook"][0]
rank_tab, cmp_tab = main_nb.winfo_children()[0], main_nb.winfo_children()[1]

# 1) Testar chave
app.var_token.set("CHAVE-TESTE")
app.test_key()
assert pump(app, lambda: any(p[0] == "showinfo" for p in popups)), "teste da chave não respondeu"
print("Testar chave:", popups[-1][2])
assert calls[0][1] == "CHAVE-TESTE"

# 2) Filtro ligado sem chave -> erro amigável
app.var_token.set("")
app.var_use_price.set(True)
rank_tab.pick["Compra"].var.set(os.path.join(SD, "2pct_compra.csv"))
rank_tab.pick["Venda"].var.set(os.path.join(SD, "2pct_venda.csv"))
n = len(popups); rank_tab.analyze()
print("Sem chave:", popups[-1][2][:70])
assert len(popups) == n + 1 and popups[-1][0] == "showerror"

# 3) Análise com filtro >= 4,00
app.var_token.set("CHAVE-TESTE"); app.var_min_price.set("4,00")
calls.clear(); rank_tab.analyze()
assert pump(app, lambda: len(rank_tab.results) == 2), "análise com preço não terminou"
pc = rank_tab.panes["Compra"]
rows = [pc.table.tree.item(i)["values"] for i in pc.table.tree.get_children()]
print("Compra linha 1:", rows[0])
res = rank_tab.results["Compra"][1]
print("Resumo:", pc.summary.cget("text").replace("\n", " || "))
assert all(r.record.ticker in res.prices and res.prices[r.record.ticker] >= 4.0 for r in res.ranked)
assert res.price_low > 0
assert rows[0][2].startswith("R$ ")
tickers_called = {c[0] for c in calls}
print("Consultas à API:", len(calls), "(únicas:", len(tickers_called), ")")
assert len(calls) == len(tickers_called)                          # compra e venda não repetem consulta
assert not ({"WINFUT", "WDOFUT"} & tickers_called)                # futuros/volume baixo nem são consultados
snap(app, "aba1_preco.png")

# 4) Segunda execução usa o cache (sem novas chamadas)
calls.clear(); rank_tab.analyze()
pump(app, lambda: not app._busy and len(rank_tab.results) == 2); app.update()
time.sleep(0.3); app.update()
print("Chamadas na 2ª execução (cache):", len(calls)); assert len(calls) == 0

# 5) Chave inválida (401): não monta ranking pela metade
app.var_refresh.set(True); mode["status"] = 401
before = rank_tab.results["Compra"][1]
n = len(popups); rank_tab.analyze()
assert pump(app, lambda: len(popups) > n)
print("401:", popups[-1][1], "|", popups[-1][2].replace("\n", " ")[:110])
assert rank_tab.results["Compra"][1] is before
mode["status"] = 200; app.var_refresh.set(False)

# 6) Comparativo com filtro de preço
main_nb.select(1); app.update()
pane = cmp_tab.winfo_children()[0].winfo_children()[0]
pane.pick_a.var.set(os.path.join(SD, "2pct_compra.csv")); pane.pick_b.var.set(os.path.join(SD, "1pct_compra.csv"))
calls.clear(); pane.run()
assert pump(app, lambda: pane.result is not None), "comparativo não terminou"
r = pane.result
print("Comparativo:", len(r.matches), "matches | descartados por preço:", r.dropped_price, "| chamadas:", len(calls))
assert all(m.price is not None and m.price >= 4.0 for m in r.matches)
first = pane.table.tree.item(pane.table.tree.get_children()[0])["values"]
print("Linha 1:", first[:4])
snap(app, "aba2_preco.png")

# 7) Persistência das configurações
app._on_close() if False else app.persist_settings()
from analisador_acoes.core.settings import load_settings
print("Salvo:", {k: (v if k != "brapi_token" else "***") for k, v in load_settings().items()})
app.destroy()
print("UI PRECO OK")
