# Copyright (C) 2025 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD
#
# Shared GUI look-and-feel framework for the ADALM-MMSC DSP curriculum.
#
# The goal (per the curriculum-review feedback) is that every interactive MMSC
# example -- Sinc Folding Explorer, Filter Explorer, FFT Explorer, Sampling
# Explorer, ... -- inherits ONE consistent ADI dashboard style instead of each
# script looking like a raw matplotlib debug window.
#
# Import this module and call:
#     theme = MMSCTheme("dark")          # or "light"
#     theme.apply(root)                  # style the Tk root + ttk widgets
#     theme.style_figure(fig)            # style an embedded matplotlib Figure
#     theme.style_axes(ax, title=...)    # style one Axes (grid, spines, colors)
#     header = theme.build_header(parent, "Sinc Folding Interactive Explorer")
#     card   = theme.build_metric_panel(parent, ["Generated Freq", ...])
#
# No binary assets are required: the "logo" is a drawn wordmark so the file is
# self-contained and portable across the curriculum repo.

import os
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# Pillow is used to load + cleanly resize the ADI logo PNG. It's optional: if it
# (or the PNG) is missing, build_header() falls back to a drawn wordmark so the
# module stays runnable with no assets.
try:
    from PIL import Image, ImageTk
except Exception:  # pragma: no cover - optional dependency
    Image = None
    ImageTk = None

# The bundled ADI logo lives next to this module.
_LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "adi_logo_acronym.png")

# ---------------------------------------------------------------------------
# Palettes
# ---------------------------------------------------------------------------
# ADI brand blue anchors both themes. Trace / marker colors are chosen for
# high contrast on a projector (dark) or in printed docs (light).

_DARK = {
    "name": "dark",
    "bg": "#0e1621",            # window background
    "panel": "#152232",         # side-panel / card background
    "panel_alt": "#1d2e42",     # alternating rows, entry fields
    "border": "#2a3d55",
    "text": "#e8eef6",          # primary text
    "text_dim": "#9fb2c9",      # secondary / labels
    "accent": "#00a1df",        # ADI blue (interactive / highlights)
    "accent_dark": "#0067b9",
    "good": "#3ecf8e",
    "warn": "#f2b134",
    "bad": "#ff5d5d",
    # plot
    "plot_bg": "#0b131d",
    "grid": "#24374e",
    "trace_rx": "#00a1df",      # measured spectrum
    "trace_theory": "#ff7a45",  # theoretical sinc1
    "marker_gen": "#3ecf8e",    # generated tone (green)
    "marker_alias": "#f2b134",  # aliased tone (amber)
    "nyquist": "#ff5d5d",       # Nyquist boundary lines (red)
    "zone_a": "#12233a",        # even Nyquist-zone shading
    "zone_b": "#182c46",        # odd  Nyquist-zone shading
    "ungen": "#3a1420",         # un-generatable region shading
}

_LIGHT = {
    "name": "light",
    "bg": "#eef2f7",
    "panel": "#ffffff",
    "panel_alt": "#f2f6fb",
    "border": "#cdd9e6",
    "text": "#12222f",
    "text_dim": "#5a6b7d",
    "accent": "#0067b9",
    "accent_dark": "#00477f",
    "good": "#1a9d5f",
    "warn": "#b9791a",
    "bad": "#c53434",
    "plot_bg": "#ffffff",
    "grid": "#d6e0ea",
    "trace_rx": "#0067b9",
    "trace_theory": "#d4571f",
    "marker_gen": "#1a9d5f",
    "marker_alias": "#b9791a",
    "nyquist": "#c53434",
    "zone_a": "#f4f8fc",
    "zone_b": "#e9f1f9",
    "ungen": "#fbeaea",
}

_PALETTES = {"dark": _DARK, "light": _LIGHT}


def _hex_to_rgb(hexstr):
    """'#00a1df' -> (0, 161, 223)."""
    h = hexstr.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class MMSCTheme:
    """Central style object shared by all MMSC interactive examples."""

    def __init__(self, name="dark"):
        self.c = _PALETTES.get(name, _DARK)
        # Font families fall back gracefully if Segoe UI isn't present.
        self.family = "Segoe UI"
        self.mono = "Consolas"
        self.f_title = (self.family, 16, "bold")
        self.f_h2 = (self.family, 11, "bold")
        self.f_body = (self.family, 10)
        self.f_small = (self.family, 9)
        self.f_metric = (self.mono, 15, "bold")
        self.f_metric_lbl = (self.family, 9)

    # -- color convenience -------------------------------------------------
    def __getitem__(self, key):
        return self.c[key]

    # -- Tk / ttk ----------------------------------------------------------
    def apply(self, root):
        """Style the Tk root window and register ttk widget styles."""
        c = self.c
        root.configure(bg=c["bg"])
        # Make the default fonts consistent app-wide.
        try:
            tkfont.nametofont("TkDefaultFont").configure(
                family=self.family, size=10
            )
            tkfont.nametofont("TkTextFont").configure(family=self.family, size=10)
        except tk.TclError:
            pass

        style = ttk.Style(root)
        # 'clam' honors custom colors on Windows; 'vista' ignores most of them.
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=c["bg"])
        style.configure("Panel.TFrame", background=c["panel"])
        style.configure("Card.TFrame", background=c["panel"],
                        relief="flat", borderwidth=0)

        style.configure("TLabel", background=c["bg"], foreground=c["text"],
                        font=self.f_body)
        style.configure("Panel.TLabel", background=c["panel"],
                        foreground=c["text"], font=self.f_body)
        style.configure("Dim.TLabel", background=c["panel"],
                        foreground=c["text_dim"], font=self.f_small)
        style.configure("H2.TLabel", background=c["panel"],
                        foreground=c["accent"], font=self.f_h2)
        style.configure("Title.TLabel", background=c["bg"],
                        foreground=c["text"], font=self.f_title)
        style.configure("Metric.TLabel", background=c["panel"],
                        foreground=c["text"], font=self.f_metric)
        style.configure("MetricLbl.TLabel", background=c["panel"],
                        foreground=c["text_dim"], font=self.f_metric_lbl)

        style.configure(
            "Accent.TButton", background=c["accent"], foreground="#ffffff",
            font=self.f_h2, borderwidth=0, focusthickness=0, padding=(14, 8),
        )
        style.map(
            "Accent.TButton",
            background=[("active", c["accent_dark"]), ("pressed", c["accent_dark"])],
        )
        style.configure(
            "Ghost.TButton", background=c["panel_alt"], foreground=c["text"],
            font=self.f_body, borderwidth=0, padding=(14, 8),
        )
        style.map("Ghost.TButton", background=[("active", c["border"])])

        style.configure(
            "TCombobox", fieldbackground=c["panel_alt"], background=c["panel_alt"],
            foreground=c["text"], arrowcolor=c["accent"], borderwidth=0,
            padding=6,
        )
        style.map("TCombobox", fieldbackground=[("readonly", c["panel_alt"])],
                  foreground=[("readonly", c["text"])])

        style.configure(
            "MMSC.Horizontal.TScale", background=c["panel"],
            troughcolor=c["panel_alt"], borderwidth=0,
        )
        return style

    # -- composite widgets -------------------------------------------------
    def build_header(self, parent, title, subtitle=None):
        """Top banner: ADI logo image + application title (+ subtitle).

        Loads the bundled adi_logo_acronym.png (via Pillow) scaled to the header
        height. Falls back to a drawn wordmark if the file or Pillow is missing.
        """
        c = self.c
        bar = tk.Frame(parent, bg=c["accent_dark"], height=64)
        bar.pack_propagate(False)

        if not self._place_logo_image(bar):
            self._draw_logo_fallback(bar)

        sep = tk.Frame(bar, bg="#ffffff", width=1, height=36)
        sep.pack(side="left", padx=14, pady=14)

        tk.Label(bar, text=title, bg=c["accent_dark"], fg="#ffffff",
                 font=self.f_title).pack(side="left", padx=(0, 10))
        if subtitle:
            tk.Label(bar, text=subtitle, bg=c["accent_dark"], fg="#d6ecfb",
                     font=self.f_body).pack(side="left")
        return bar

    def _place_logo_image(self, bar):
        """Render the bundled PNG logo into the header bar. Returns True on success."""
        if Image is None or not os.path.exists(_LOGO_PATH):
            return False
        try:
            img = Image.open(_LOGO_PATH).convert("RGBA")
            target_h = 40
            scale = target_h / img.height
            img = img.resize(
                (max(1, round(img.width * scale)), target_h),
                Image.LANCZOS,
            )
            # Composite onto the header color so any transparent / off-blue
            # edges blend into the bar instead of showing a seam.
            bg_rgb = _hex_to_rgb(self.c["accent_dark"])
            canvas = Image.new("RGBA", img.size, bg_rgb + (255,))
            canvas.alpha_composite(img)
            # Keep a reference on the theme so Tk doesn't garbage-collect it.
            self._logo_img = ImageTk.PhotoImage(canvas.convert("RGB"))
            tk.Label(bar, image=self._logo_img, bg=self.c["accent_dark"]).pack(
                side="left", padx=(16, 6), pady=12)
            return True
        except Exception:
            return False

    def _draw_logo_fallback(self, bar):
        """Drawn ADI wordmark used when the PNG/Pillow isn't available."""
        c = self.c
        logo = tk.Canvas(bar, width=54, height=64, bg=c["accent_dark"],
                         highlightthickness=0)
        logo.create_rectangle(16, 20, 26, 44, fill="#ffffff", outline="")
        logo.create_polygon(28, 44, 40, 20, 40, 44, fill="#ffffff", outline="")
        logo.pack(side="left")

        wm = tk.Frame(bar, bg=c["accent_dark"])
        wm.pack(side="left", pady=8)
        tk.Label(wm, text="ANALOG", bg=c["accent_dark"], fg="#ffffff",
                 font=(self.family, 13, "bold")).pack(anchor="w")
        tk.Label(wm, text="DEVICES", bg=c["accent_dark"], fg="#ffffff",
                 font=(self.family, 9)).pack(anchor="w")

    def build_banner(self, parent, text):
        """Curriculum guidance strip below the header.

        The label wraps DYNAMICALLY to the current window width (via a
        <Configure> binding) so no words are clipped at small / non-maximized
        sizes -- a fixed wraplength would only fit one window size.
        """
        c = self.c
        b = tk.Frame(parent, bg=c["panel_alt"])
        lbl = tk.Label(b, text="  ▶  " + text, bg=c["panel_alt"],
                       fg=c["accent"], font=self.f_h2, anchor="w",
                       justify="left")
        lbl.pack(fill="x", padx=6, pady=6)

        def _rewrap(event):
            # leave a little room for the horizontal padding
            lbl.configure(wraplength=max(200, event.width - 24))
        b.bind("<Configure>", _rewrap)
        return b

    def section(self, parent, title):
        """A titled side-panel section frame; returns the body frame."""
        c = self.c
        wrap = tk.Frame(parent, bg=c["panel"])
        head = tk.Frame(wrap, bg=c["panel"])
        head.pack(fill="x", padx=12, pady=(12, 4))
        tk.Label(head, text=title.upper(), bg=c["panel"], fg=c["accent"],
                 font=self.f_h2).pack(anchor="w")
        tk.Frame(wrap, bg=c["border"], height=1).pack(fill="x", padx=12)
        body = tk.Frame(wrap, bg=c["panel"])
        body.pack(fill="both", expand=True, padx=12, pady=8)
        return wrap, body

    def metric(self, parent, label, initial="--", accent=None):
        """A single live-metric card. Returns the value StringVar to update."""
        c = self.c
        card = tk.Frame(parent, bg=c["panel_alt"])
        card.pack(fill="x", pady=4)
        tk.Label(card, text=label.upper(), bg=c["panel_alt"], fg=c["text_dim"],
                 font=self.f_metric_lbl, anchor="w").pack(
            fill="x", padx=10, pady=(6, 0))
        var = tk.StringVar(value=initial)
        tk.Label(card, textvariable=var, bg=c["panel_alt"],
                 fg=accent or c["text"], font=self.f_metric, anchor="w").pack(
            fill="x", padx=10, pady=(0, 6))
        return var

    # -- matplotlib --------------------------------------------------------
    def style_figure(self, fig):
        fig.set_facecolor(self.c["panel"])

    def style_axes(self, ax, title=None, xlabel=None, ylabel=None):
        c = self.c
        ax.set_facecolor(c["plot_bg"])
        ax.grid(True, color=c["grid"], linewidth=0.6, alpha=0.9)
        for spine in ax.spines.values():
            spine.set_color(c["border"])
        ax.tick_params(colors=c["text_dim"], labelsize=8)
        if title:
            ax.set_title(title, color=c["text"], fontsize=11, fontweight="bold")
        if xlabel:
            ax.set_xlabel(xlabel, color=c["text_dim"], fontsize=9)
        if ylabel:
            ax.set_ylabel(ylabel, color=c["text_dim"], fontsize=9)
