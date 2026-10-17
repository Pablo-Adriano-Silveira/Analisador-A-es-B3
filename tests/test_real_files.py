"""Validação com os 4 CSVs reais (pasta sample_data). Confere filtro, ordenação, contagens e matches
contra uma leitura independente (módulo csv puro) dos arquivos de origem."""
import csv
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from analisador_acoes.core.comparison import compare  # noqa: E402
from analisador_acoes.core.csv_loader import load_csv  # noqa: E402
from analisador_acoes.core.ranking import ScoringConfig, rank_records  # noqa: E402

FILES = {k: os.path.join(ROOT, "sample_data", f"{k}.csv")
         for k in ("2pct_compra", "2pct_venda", "1pct_compra", "1pct_venda")}


def raw_rows(path):
    """Leitura independente: devolve {ticker: (gain, loss, taxa, volume)} sem usar o loader."""
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            out[r["Ativo"].strip()] = (int(r["Qtd Gain"]), int(r["Qtd Loss"]), float(r["Taxa de Acerto"]),
                                       int(r["Méd. Volume Leilão"].replace(".", "")))
    return out


@unittest.skipUnless(all(os.path.exists(p) for p in FILES.values()), "sample_data ausente")
class RealFiles(unittest.TestCase):
    def test_each_file(self):
        cfg = ScoringConfig()
        for key, path in FILES.items():
            with self.subTest(key):
                raw = raw_rows(path)
                load = load_csv(path)
                self.assertEqual(len(load.records), 200)
                self.assertEqual(load.invalid_rows, [])
                self.assertEqual(load.duplicates, [])
                for r in load.records:                       # valores idênticos à origem
                    g, l, t, v = raw[r.ticker]
                    self.assertEqual((r.qtd_gain, r.qtd_loss, r.volume), (g, l, v))
                    self.assertAlmostEqual(r.taxa, t)
                res = rank_records(load.records, cfg)
                # filtro de volume contra a leitura independente
                expect_excluded = {t for t, (_g, _l, _x, v) in raw.items() if v <= 80000}
                self.assertEqual({e.record.ticker for e in res.excluded_volume}, expect_excluded)
                self.assertEqual(len(expect_excluded), 10)
                self.assertEqual(res.volume_ok, 190)
                # ranking só tem elegíveis, ordenado, sem completar além do que existe
                for row in res.ranked:
                    g, l, _t, v = raw[row.record.ticker]
                    self.assertGreater(v, 80000)
                    self.assertGreaterEqual(g + l, 10)
                scores = [r.score for r in res.ranked]
                self.assertEqual(scores, sorted(scores, reverse=True))
                self.assertEqual(len(res.rows), min(40, res.eligible))
                self.assertFalse({"WINFUT", "WDOFUT"} & {r.record.ticker for r in res.ranked})
                self.assertEqual(res.total, len(res.excluded_volume) + len(res.excluded_filters) + len(res.excluded_price) + res.eligible)

    def test_compare_both_sides(self):
        cfg = ScoringConfig()
        for side in ("compra", "venda"):
            with self.subTest(side):
                a, b = load_csv(FILES[f"2pct_{side}"]), load_csv(FILES[f"1pct_{side}"])
                c = compare(a, b, cfg)
                ra, rb = raw_rows(FILES[f"2pct_{side}"]), raw_rows(FILES[f"1pct_{side}"])
                self.assertEqual(c.n_both, len(set(ra) & set(rb)))
                self.assertEqual(c.only_a, []); self.assertEqual(c.only_b, [])
                for m in c.matches:
                    self.assertEqual(m.a.record.taxa, ra[m.ticker][2])
                    self.assertEqual(m.b.record.taxa, rb[m.ticker][2])
                    self.assertGreater(min(ra[m.ticker][3], rb[m.ticker][3]), 80000)
                self.assertEqual(c.n_both, c.dropped_volume + c.dropped_filters + c.dropped_top_n + len(c.matches))
                self.assertEqual(c.volume_divergences, 0)


if __name__ == "__main__":
    unittest.main()
