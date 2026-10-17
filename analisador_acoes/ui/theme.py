"""Tema visual (ttk 'clam' personalizado). Só usa a biblioteca padrão do Python (tkinter)."""
import sys
import tkinter as tk
from tkinter import ttk

BG = "#F3F5F9"
CARD = "#FFFFFF"
NAVY = "#0F2742"
ACCENT = "#1F6FEB"
ACCENT_DARK = "#1858BC"
TEXT = "#1B2432"
MUTED = "#5B6678"
BORDER = "#D5DBE6"
ZEBRA = "#F6F8FC"
OK = "#1E7B3A"
WARN = "#B45309"
ERR = "#B42318"

FONT = "Segoe UI"   # ajustado em apply_theme se a fonte não existir (ex.: Linux/macOS)


def apply_theme(root: tk.Tk) -> None:
    global FONT
    from tkinter import font as tkfont
    families = set(tkfont.families(root))
    FONT = next((f for f in ("Segoe UI", "Helvetica Neue", "Helvetica", "DejaVu Sans", "Arial") if f in families),
                tkfont.nametofont("TkDefaultFont").actual("family"))
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=BG)
    root.option_add("*Font", (FONT, 10))

    style.configure(".", background=BG, foreground=TEXT, font=(FONT, 10))
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD, relief="solid", borderwidth=1, bordercolor=BORDER)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Card.TLabel", background=CARD)
    style.configure("CardInner.TFrame", background=CARD, borderwidth=0)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(FONT, 9))
    style.configure("CardMuted.TLabel", background=CARD, foreground=MUTED, font=(FONT, 9))
    style.configure("Title.TLabel", background=NAVY, foreground="white", font=(FONT, 15, "bold"))
    style.configure("Subtitle.TLabel", background=NAVY, foreground="#B9C7DD", font=(FONT, 9))
    style.configure("Header.TFrame", background=NAVY)
    style.configure("Summary.TLabel", background=BG, foreground=TEXT, font=(FONT, 9))
    style.configure("Warn.TLabel", background=BG, foreground=WARN, font=(FONT, 9))
    style.configure("Err.TLabel", background=BG, foreground=ERR, font=(FONT, 9, "bold"))

    style.configure("TButton", padding=(12, 6), background="#E7ECF5", foreground=TEXT,
                    bordercolor=BORDER, focusthickness=0)
    style.map("TButton", background=[("active", "#D9E1F0"), ("disabled", "#EEF1F6")],
              foreground=[("disabled", "#9AA4B5")])
    style.configure("Accent.TButton", background=ACCENT, foreground="white",
                    font=(FONT, 10, "bold"), bordercolor=ACCENT)
    style.map("Accent.TButton", background=[("active", ACCENT_DARK), ("disabled", "#9DBCF0")],
              foreground=[("disabled", "#F0F4FC")])

    style.configure("TCheckbutton", background=BG, foreground=TEXT)
    style.configure("TEntry", fieldbackground="white", bordercolor=BORDER, padding=4)
    style.configure("TSpinbox", fieldbackground="white", bordercolor=BORDER, padding=3)
    style.configure("TCombobox", fieldbackground="white", bordercolor=BORDER, padding=3)

    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
    style.configure("TNotebook.Tab", padding=(18, 8), background="#DCE3EF", foreground=MUTED,
                    font=(FONT, 10, "bold"))
    style.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", ACCENT)])

    style.configure("Treeview", background="white", fieldbackground="white", foreground=TEXT,
                    rowheight=25, bordercolor=BORDER, font=(FONT, 10))
    style.configure("Treeview.Heading", background="#E3E9F4", foreground=NAVY,
                    font=(FONT, 9, "bold"), padding=(6, 6), relief="flat")
    style.map("Treeview.Heading", background=[("active", "#D3DCEC")])
    style.map("Treeview", background=[("selected", "#CFE0FB")], foreground=[("selected", TEXT)])

    style.configure("Horizontal.TProgressbar", troughcolor="#DCE3EF", background=ACCENT, thickness=6)
