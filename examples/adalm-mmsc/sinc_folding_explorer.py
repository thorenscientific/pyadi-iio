# Copyright (C) 2025 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD
#
# Sinc Folding Interactive Explorer -- polished dashboard edition.
#
# This is a redesigned GUI for the ADALM-MMSC DSP curriculum, based on
# curriculum-review feedback (Mark Thoren): the original
# sinc_folding_interactive.py works, but looks like a raw matplotlib debug
# window.  This version is a 3-panel interactive DSP learning tool:
#
#     +-----------------------------------------------------------+
#     | ADI logo | Sinc Folding Interactive Explorer              |
#     +-----------------------------------------------------------+
#     |  ▶ Move the slider to watch a tone fold across Nyquist... |
#     +----------------+---------------------------+--------------+
#     |  CONTROLS      |   FFT (dominant)          |  LIVE        |
#     |  - Noise freq  |   + small waveform strip  |  METRICS     |
#     |  - Fs selector |                           |  Generated   |
#     |  - Input freq  |                           |  Aliased     |
#     |  - Reset/Pause |                           |  Zone, ...   |
#     +----------------+---------------------------+--------------+
#     |  Explanation panel (contextual DSP help)                  |
#     +-----------------------------------------------------------+
#
# The original file is left untouched.  The DSP helpers (folding math, noise-band
# generation) are ported in here so this file does NOT inherit workshop.py's
# import-time pl.ion() side effect, and so it can run with --simulate on a laptop
# with no hardware (for workshops / customer demos).
#
# Fixes baked in vs the original:
#   * F-12-09 / F-02-07 -- the slider is clamped to what the M2K can actually
#     generate (fs_out/2 - width/2), and generate_noise_band() guards against a
#     negative-width band, so the "drag to max -> crash" bug cannot occur.
#   * F-12-01          -- -d/--decimation uses type=int (the original's int
#     choices reject every string argv), deduped and trimmed to real OSR values.
#
# Usage:
#   python sinc_folding_explorer.py --simulate                      # no hardware
#   python sinc_folding_explorer.py -a serial:COM4,230400           # live bench
#   python sinc_folding_explorer.py -a serial:COM4,230400 --theme light

import argparse
import queue
import sys
import time
import tkinter as tk
from threading import Thread
from tkinter import ttk

import numpy as np

from mmsc_gui_theme import MMSCTheme

# genalyzer is only needed for the live FFT path; keep it optional so --simulate
# runs on a machine without the DSP stack.
try:
    import genalyzer as gn
except Exception:  # pragma: no cover - optional dependency
    gn = None


# ===========================================================================
#  DSP helpers (ported so this file is self-contained and side-effect-free)
# ===========================================================================
def time_points_from_freq(freq, fs=1, density=False, rng=None):
    """Generate a real time series from a half-spectrum (random phases)."""
    rng = rng or np.random.default_rng()
    n = len(freq)
    rnd_ph_pos = np.exp(1j * rng.uniform(0.0, 2.0 * np.pi, n - 1))
    rnd_ph_neg = np.flip(np.conjugate(rnd_ph_pos))
    rnd_ph_full = np.concatenate(([1], rnd_ph_pos, [1], rnd_ph_neg))
    spectrum_full = np.concatenate((freq, np.roll(np.flip(freq), 1)))
    r_time = np.fft.ifft(spectrum_full * rnd_ph_full)
    if density:
        r_time *= n * np.sqrt(fs / n)
    return np.real(r_time)


def generate_noise_band(center, width, fs, rng=None):
    """White-noise band centered on `center`, `width` wide, at rate `fs`.

    Hardened vs workshop.generate_noise_band (F-02-07): the lower band edge is
    clamped BELOW the upper edge, so a center at/above Nyquist yields a valid
    (possibly clipped) band instead of a negative-length array -> ValueError.
    """
    hi = int(min(center + width // 2, fs // 2))
    lo = int(max(center - width // 2, 1))
    lo = min(lo, hi - 1)                       # guarantee at least 1 bin, never <0
    band = hi - lo
    spectrum = np.concatenate(
        (np.zeros(lo), np.ones(band), np.zeros(fs // 2 - hi))
    )
    spectrum /= np.sqrt(band)                  # normalize to ~1 V RMS
    return time_points_from_freq(spectrum, fs=fs, density=True, rng=rng)


def fold_frequency(fc, fs_in):
    """Return (aliased_freq, fold_count) for a tone at fc sampled at fs_in."""
    nyq = fs_in / 2
    if fc <= nyq:
        return fc, 0
    fold = int(fc // nyq)
    if fold % 2 == 0:
        fa = fc - nyq * fold
    else:
        fa = nyq * (fold + 1) - fc
    return fa, fold


# ===========================================================================
#  Hardware / simulation worker thread
# ===========================================================================
class SignalWorker(Thread):
    """Owns the M2K + AD4080 (or simulates them) and streams FFTs to the GUI.

    Communication with the GUI is via thread-safe primitives only:
      * command_q  : GUI -> worker  (center-freq / decimation changes, pause)
      * result_q   : worker -> GUI  (latest {waveform, fft_db, fc, status})
    """

    def __init__(self, cfg, command_q, result_q):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.command_q = command_q
        self.result_q = result_q
        self.running = True
        self.paused = False
        self._center = cfg["init_center"]
        self._decimation = cfg["decimation"]
        self.rng = np.random.default_rng(0)

    # -- lifecycle ---------------------------------------------------------
    def stop(self):
        self.running = False

    def _drain_commands(self):
        try:
            while True:
                cmd, val = self.command_q.get_nowait()
                if cmd == "center":
                    self._center = val
                elif cmd == "decimation":
                    self._decimation = val
                elif cmd == "pause":
                    self.paused = val
        except queue.Empty:
            pass

    def _emit(self, **kw):
        # Keep only the freshest frame; the GUI reads at its own cadence.
        try:
            while True:
                self.result_q.get_nowait()
        except queue.Empty:
            pass
        self.result_q.put(kw)

    def run(self):
        if self.cfg["simulate"]:
            self._run_sim()
        else:
            self._run_hardware()

    # -- simulation --------------------------------------------------------
    def _run_sim(self):
        cfg = self.cfg
        fs_out = cfg["fs_out"]
        nfft = cfg["nfft"]
        npts = cfg["npts"]
        self._emit(status="Simulated device ready", fc=None,
                   waveform=np.zeros(npts), fft_db=np.full(nfft // 2 + 1, -120.0))
        while self.running:
            self._drain_commands()
            if self.paused:
                time.sleep(0.05)
                continue
            fs_in = cfg["fs_pre"] / self._decimation
            fc = self._center
            fa, fold = fold_frequency(fc, fs_in)
            # Build a synthetic received spectrum: a band at the aliased freq,
            # shaped by the sinc1 rolloff at the *generated* frequency.
            half = nfft // 2 + 1
            faxis = np.linspace(0, fs_in / 2, half)
            band = 10000.0
            spec = -110 + 3 * self.rng.standard_normal(half)
            sinc_atten = 20 * np.log10(
                np.abs(np.sinc(fc / fs_in)) + 1e-6
            )
            peak = -12 + sinc_atten
            spec += peak * np.exp(-0.5 * ((faxis - fa) / (band / 2.355)) ** 2)
            # small time-domain preview
            t = np.arange(npts) / fs_in
            wav = (10 ** (peak / 20)) * np.sin(2 * np.pi * fa * t)
            wav += 0.01 * self.rng.standard_normal(npts)
            self._emit(status=f"Simulating fc = {fc/1e3:.1f} kHz",
                       fc=fc, waveform=wav, fft_db=spec)
            time.sleep(0.15)

    # -- live hardware -----------------------------------------------------
    def _run_hardware(self):
        cfg = self.cfg
        import libm2k
        import adi

        self._emit(status="Connecting to ADALM2000...", fc=None,
                   waveform=np.zeros(cfg["npts"]),
                   fft_db=np.full(cfg["nfft"] // 2 + 1, -120.0))
        m2k = libm2k.m2kOpen()
        if m2k is None:
            self._emit(status="ERROR: no ADALM2000 connected", fc=None,
                       waveform=np.zeros(cfg["npts"]),
                       fft_db=np.full(cfg["nfft"] // 2 + 1, -120.0))
            return
        aout = m2k.getAnalogOut()
        aout.reset()
        m2k.calibrateDAC()
        aout.setSampleRate(0, cfg["fs_out"])
        aout.setSampleRate(1, cfg["fs_out"])
        aout.enableChannel(0, True)
        aout.enableChannel(1, True)
        aout.setCyclic(True)

        self._emit(status="Connecting to AD4080...", fc=None,
                   waveform=np.zeros(cfg["npts"]),
                   fft_db=np.full(cfg["nfft"] // 2 + 1, -120.0))
        try:
            adc = adi.ad4080(cfg["ad4080_uri"])
        except Exception as exc:
            self._emit(status=f"ERROR: AD4080 not found ({exc})", fc=None,
                       waveform=np.zeros(cfg["npts"]),
                       fft_db=np.full(cfg["nfft"] // 2 + 1, -120.0))
            libm2k.contextClose(m2k)
            return

        adc.rx_buffer_size = cfg["npts"]
        adc.filter_type = "sinc1"
        adc.oversampling_ratio = self._decimation
        transmitting = None
        applied_decim = self._decimation

        window = gn.Window.BLACKMAN_HARRIS
        code_fmt = gn.CodeFormat.TWOS_COMPLEMENT
        rfft_scale = gn.RfftScale.NATIVE

        try:
            while self.running:
                self._drain_commands()
                if self.paused:
                    time.sleep(0.05)
                    continue

                if self._decimation != applied_decim:
                    adc.oversampling_ratio = self._decimation
                    applied_decim = self._decimation
                    transmitting = None  # force regen

                if transmitting != self._center:
                    self._emit(status=f"Generating {self._center/1e3:.1f} kHz band",
                               fc=transmitting, waveform=np.zeros(cfg["npts"]),
                               fft_db=np.full(cfg["nfft"] // 2 + 1, -120.0))
                    wav = generate_noise_band(self._center, 10000, cfg["fs_out"],
                                              rng=self.rng)
                    aout.push([wav, wav * -1.0])
                    transmitting = self._center

                din_raw = adc.rx()
                fc = transmitting
                scale = adc.channel[0].scale
                din = din_raw * scale / 1e3        # scale is in mV/code -> volts
                din -= np.average(din)
                fft_cplx = gn.rfft(din, cfg["navg"], cfg["nfft"], window,
                                   code_fmt, rfft_scale)
                fft_db = gn.db(fft_cplx)
                std = float(np.std(din_raw))
                note = "  [check wiring: flat input]" if std < 1.0 else ""
                self._emit(status=f"Receiving  RMS={np.std(din):.4f} V{note}",
                           fc=fc, waveform=din, fft_db=fft_db)
        finally:
            libm2k.contextClose(m2k)
            del adc
            self._emit(status="Device released", fc=None,
                       waveform=np.zeros(cfg["npts"]),
                       fft_db=np.full(cfg["nfft"] // 2 + 1, -120.0))


# ===========================================================================
#  The GUI application
# ===========================================================================
class SincFoldingExplorer:
    WIDTH_HZ = 10000  # noise-band width used by the generator

    def __init__(self, root, cfg):
        self.root = root
        self.cfg = cfg
        self.theme = MMSCTheme(cfg["theme"])
        self.command_q = queue.Queue()
        self.result_q = queue.Queue()
        self.fs_in = cfg["fs_pre"] / cfg["decimation"]
        self.latest = None
        self.show_waveform = tk.BooleanVar(value=True)

        root.title("ADALM-MMSC · Sinc Folding Interactive Explorer")
        root.geometry("1280x820")
        root.minsize(1080, 720)
        self.theme.apply(root)

        self._build_layout()

        # Start the worker
        self.worker = SignalWorker(cfg, self.command_q, self.result_q)
        self.worker.start()

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll()  # begin the GUI refresh loop

    # -- layout ------------------------------------------------------------
    def _build_layout(self):
        c = self.theme
        mode = "SIMULATION" if self.cfg["simulate"] else "LIVE HARDWARE"
        c.build_header(
            self.root, "Sinc Folding Interactive Explorer",
            subtitle=f"ADALM-MMSC DSP Curriculum   ·   {mode}",
        ).pack(fill="x")
        c.build_banner(
            self.root,
            "Move the frequency slider to observe how a tone beyond the Nyquist "
            "frequency folds (aliases) into lower Nyquist zones.",
        ).pack(fill="x")

        body = ttk.Frame(self.root, style="TFrame")
        body.pack(fill="both", expand=True, padx=10, pady=(6, 4))
        body.columnconfigure(0, weight=0, minsize=280)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=0, minsize=240)
        body.rowconfigure(0, weight=1)

        self._build_controls(body)
        self._build_plots(body)
        self._build_metrics(body)
        self._build_explanation(self.root)

    def _build_controls(self, parent):
        t = self.theme
        panel = tk.Frame(parent, bg=t["panel"])
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        wrap, body = t.section(panel, "Controls")
        wrap.pack(fill="both", expand=True)

        # --- noise center-frequency slider (clamped to generatable range) ---
        tk.Label(body, text="Noise center frequency", bg=t["panel"],
                 fg=t["text"], font=t.f_body).pack(anchor="w")
        self.freq_val = tk.StringVar()
        tk.Label(body, textvariable=self.freq_val, bg=t["panel"],
                 fg=t["accent"], font=(t.mono, 13, "bold")).pack(anchor="w")

        self.slider_max = self._max_center()
        self.freq_scale = ttk.Scale(
            body, from_=1000, to=self.slider_max, orient="horizontal",
            style="MMSC.Horizontal.TScale", command=self._on_slider,
        )
        self.freq_scale.set(min(self.cfg["init_center"], self.slider_max))
        self.freq_scale.pack(fill="x", pady=(2, 2))
        self.range_lbl = tk.Label(
            body, bg=t["panel"], fg=t["text_dim"], font=t.f_small,
            text=f"generatable: 1 kHz – {self.slider_max/1e3:.0f} kHz",
        )
        self.range_lbl.pack(anchor="w", pady=(0, 10))

        # --- sampling-rate (decimation) selector ---
        tk.Label(body, text="AD4080 sample rate (OSR)", bg=t["panel"],
                 fg=t["text"], font=t.f_body).pack(anchor="w")
        self.osr_options = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024]
        self.osr_var = tk.StringVar(value=str(self.cfg["decimation"]))
        osr_labels = [self._osr_label(o) for o in self.osr_options]
        self._osr_map = {self._osr_label(o): o for o in self.osr_options}
        self.osr_combo = ttk.Combobox(
            body, values=osr_labels, textvariable=tk.StringVar(),
            state="readonly", style="TCombobox",
        )
        self.osr_combo.set(self._osr_label(self.cfg["decimation"]))
        self.osr_combo.bind("<<ComboboxSelected>>", self._on_osr)
        self.osr_combo.pack(fill="x", pady=(2, 10))

        # --- input-frequency presets (quick-jump) ---
        tk.Label(body, text="Jump to input frequency", bg=t["panel"],
                 fg=t["text"], font=t.f_body).pack(anchor="w")
        self.preset_combo = ttk.Combobox(
            body, values=["30 kHz", "100 kHz", "200 kHz", "300 kHz"],
            state="readonly", style="TCombobox",
        )
        self.preset_combo.set("100 kHz")
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset)
        self.preset_combo.pack(fill="x", pady=(2, 12))

        # --- buttons ---
        btns = tk.Frame(body, bg=t["panel"])
        btns.pack(fill="x", pady=(4, 2))
        self.pause_btn = ttk.Button(btns, text="⏸  Pause", style="Ghost.TButton",
                                    command=self._on_pause)
        self.pause_btn.pack(fill="x", pady=3)
        ttk.Button(btns, text="⟳  Reset", style="Accent.TButton",
                   command=self._on_reset).pack(fill="x", pady=3)

        ttk.Checkbutton(
            body, text="Show waveform strip", variable=self.show_waveform,
            command=self._toggle_waveform,
        ).pack(anchor="w", pady=(12, 0))

        # status line
        self.status_var = tk.StringVar(value="Starting…")
        tk.Frame(body, bg=t["border"], height=1).pack(fill="x", pady=(12, 8))
        tk.Label(body, textvariable=self.status_var, bg=t["panel"],
                 fg=t["text_dim"], font=t.f_small, wraplength=240,
                 justify="left").pack(anchor="w")

    def _build_plots(self, parent):
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from matplotlib.figure import Figure

        t = self.theme
        holder = tk.Frame(parent, bg=t["panel"])
        holder.grid(row=0, column=1, sticky="nsew")

        # FFT dominant (height ratio 5), waveform strip small (ratio 1).
        self.fig = Figure(figsize=(7.2, 6.2), dpi=100)
        t.style_figure(self.fig)
        gs = self.fig.add_gridspec(6, 1, hspace=0.45)
        self.ax_fft = self.fig.add_subplot(gs[0:5, 0])
        self.ax_wav = self.fig.add_subplot(gs[5, 0])
        t.style_axes(self.ax_fft, title="Received Spectrum (FFT)",
                     xlabel="Frequency (Hz)", ylabel="Magnitude (dB)")
        t.style_axes(self.ax_wav, title="Received waveform",
                     ylabel="V")
        self.fig.subplots_adjust(left=0.09, right=0.98, top=0.95, bottom=0.10)

        self.canvas = FigureCanvasTkAgg(self.fig, master=holder)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def _build_metrics(self, parent):
        t = self.theme
        panel = tk.Frame(parent, bg=t["panel"])
        panel.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        wrap, body = t.section(panel, "Live Measurements")
        wrap.pack(fill="both", expand=True)

        self.m_gen = t.metric(body, "Generated frequency", accent=t["marker_gen"])
        self.m_alias = t.metric(body, "Aliased frequency", accent=t["marker_alias"])
        self.m_dist = t.metric(body, "Distance from Nyquist")
        self.m_fs = t.metric(body, "Sampling rate (fs_in)")
        self.m_nyq = t.metric(body, "Nyquist frequency", accent=t["nyquist"])
        self.m_zone = t.metric(body, "Nyquist zone / fold")
        self.m_peak = t.metric(body, "FFT peak magnitude")

    def _build_explanation(self, parent):
        t = self.theme
        strip = tk.Frame(parent, bg=t["panel_alt"])
        strip.pack(fill="x", side="bottom")
        self.explain_var = tk.StringVar(
            value="Below Nyquist: the tone appears where it was generated — no folding.")
        tk.Label(strip, textvariable=self.explain_var, bg=t["panel_alt"],
                 fg=t["text"], font=t.f_body, anchor="w", justify="left",
                 wraplength=1220).pack(fill="x", padx=14, pady=8)

    # -- helpers -----------------------------------------------------------
    def _max_center(self):
        """Largest center the M2K can generate: fs_out/2 - width/2 (F-12-09)."""
        return int(self.cfg["fs_out"] // 2 - self.WIDTH_HZ // 2)

    def _osr_label(self, osr):
        fs = self.cfg["fs_pre"] / osr
        return f"OSR {osr}   (fs = {fs/1e3:.1f} kHz)"

    # -- control callbacks -------------------------------------------------
    def _on_slider(self, _value):
        fc = int(float(self.freq_scale.get()))
        self.freq_val.set(f"{fc/1e3:.1f} kHz")
        self.command_q.put(("center", fc))

    def _on_osr(self, _evt):
        osr = self._osr_map[self.osr_combo.get()]
        self.fs_in = self.cfg["fs_pre"] / osr
        self.command_q.put(("decimation", osr))

    def _on_preset(self, _evt):
        khz = float(self.preset_combo.get().split()[0])
        fc = min(int(khz * 1000), self.slider_max)
        self.freq_scale.set(fc)
        self._on_slider(None)

    def _on_pause(self):
        self.worker.paused = not self.worker.paused
        self.command_q.put(("pause", self.worker.paused))
        self.pause_btn.configure(text="▶  Resume" if self.worker.paused
                                 else "⏸  Pause")

    def _on_reset(self):
        self.freq_scale.set(min(self.cfg["init_center"], self.slider_max))
        self._on_slider(None)
        self.osr_combo.set(self._osr_label(self.cfg["decimation"]))
        self._on_osr(None)
        if self.worker.paused:
            self._on_pause()

    def _toggle_waveform(self):
        self.ax_wav.set_visible(self.show_waveform.get())
        self.canvas.draw_idle()

    # -- refresh loop ------------------------------------------------------
    def _poll(self):
        try:
            self.latest = self.result_q.get_nowait()
        except queue.Empty:
            pass
        if self.latest is not None:
            self._render(self.latest)
        self.root.after(80, self._poll)

    def _render(self, frame):
        t = self.theme
        self.status_var.set(frame.get("status", ""))
        fs_in = self.fs_in
        nyq = fs_in / 2
        plot_max = nyq * 5

        # ---- waveform strip ----
        wav = frame["waveform"]
        self.ax_wav.clear()
        t.style_axes(self.ax_wav, title=None, ylabel="V")
        tvec = np.arange(len(wav)) / fs_in
        self.ax_wav.plot(tvec, wav, color=t["trace_rx"], linewidth=0.8)
        self.ax_wav.set_xlim(0, tvec[-1] if len(tvec) else 1)
        self.ax_wav.set_visible(self.show_waveform.get())

        # ---- FFT ----
        ax = self.ax_fft
        ax.clear()
        t.style_axes(ax, title="Received Spectrum (FFT)",
                     xlabel="Frequency (Hz)", ylabel="Magnitude (dB)")
        ax.set_xlim(0, plot_max)
        ax.set_ylim(-120, 10)

        # Nyquist-zone shading (alternating) + labels
        for zone in range(5):
            x0, x1 = zone * nyq, (zone + 1) * nyq
            ax.axvspan(x0, x1, color=t["zone_a"] if zone % 2 == 0 else t["zone_b"],
                       zorder=0)
            ax.text((x0 + x1) / 2, 5, f"Zone {zone + 1}", color=t["text_dim"],
                    ha="center", va="top", fontsize=8)
        for zone in range(1, 6):
            ax.axvline(zone * nyq, color=t["nyquist"], linestyle="--",
                       linewidth=0.8, alpha=0.7)

        # Measured spectrum, folded/unfolded across zones
        fft_db = frame["fft_db"]
        faxis = np.linspace(0, nyq, len(fft_db))
        for fold in range(5):
            freqs = faxis + fold * nyq
            trace = fft_db[:: (-1) ** fold]
            ax.plot(freqs, trace, color=t["trace_rx"],
                    linewidth=1.4 if fold == 0 else 1.0,
                    alpha=0.85 ** fold,
                    label="Measured spectrum" if fold == 0 else None)
            # theoretical sinc1 rolloff
            sinc = np.sinc(freqs / fs_in)
            sinc_db = 20 * np.log10(np.abs(sinc) + 1e-9) - 10
            ax.plot(freqs, sinc_db, color=t["trace_theory"],
                    linestyle="-" if fold == 0 else "--",
                    linewidth=1.0, alpha=0.8 ** fold,
                    label="Theoretical sinc1" if fold == 0 else None)

        # Markers for generated + aliased tones
        fc = frame.get("fc")
        metrics = dict(gen="--", alias="--", dist="--", zone="--", peak="--")
        if fc is not None:
            fa, fold = fold_frequency(fc, fs_in)
            if fc <= plot_max:
                ax.axvline(fc, color=t["marker_gen"], linewidth=2.0)
                ax.annotate("Generated", xy=(fc, 0), xytext=(fc, 8),
                            color=t["marker_gen"], ha="center", fontsize=9,
                            fontweight="bold",
                            arrowprops=dict(color=t["marker_gen"], shrink=0.05,
                                            width=2, headwidth=8))
            ax.axvline(fa, color=t["marker_alias"], linewidth=2.0)
            if fold > 0:
                ax.annotate("Aliased", xy=(fa, 0), xytext=(fa, 8),
                            color=t["marker_alias"], ha="center", fontsize=9,
                            fontweight="bold",
                            arrowprops=dict(color=t["marker_alias"], shrink=0.05,
                                            width=2, headwidth=8))
            metrics["gen"] = f"{fc/1e3:.1f} kHz"
            metrics["alias"] = f"{fa/1e3:.1f} kHz"
            metrics["dist"] = f"{(fc - nyq)/1e3:+.1f} kHz"
            metrics["zone"] = f"Zone {fold + 1}  ·  fold {fold}"
            metrics["peak"] = f"{np.max(fft_db):.1f} dB"
            self._update_explanation(fc, fa, fold, nyq)

        leg = ax.legend(loc="upper right", fontsize=8, framealpha=0.85)
        if leg:
            leg.get_frame().set_facecolor(t["panel"])
            for txt in leg.get_texts():
                txt.set_color(t["text"])

        # ---- metrics panel ----
        self.m_gen.set(metrics["gen"])
        self.m_alias.set(metrics["alias"])
        self.m_dist.set(metrics["dist"])
        self.m_fs.set(f"{fs_in/1e3:.1f} kHz")
        self.m_nyq.set(f"{nyq/1e3:.1f} kHz")
        self.m_zone.set(metrics["zone"])
        self.m_peak.set(metrics["peak"])

        self.canvas.draw_idle()

    def _update_explanation(self, fc, fa, fold, nyq):
        if fold == 0:
            msg = (f"{fc/1e3:.1f} kHz is BELOW the Nyquist frequency "
                   f"({nyq/1e3:.1f} kHz) — it appears at its true frequency, "
                   f"no aliasing.")
        else:
            direction = "reflects downward" if fold % 2 else "wraps down"
            msg = (f"{fc/1e3:.1f} kHz is in Nyquist zone {fold + 1}. Sampling at "
                   f"fs_in = {2*nyq/1e3:.1f} kHz cannot represent it, so it "
                   f"{direction} and appears aliased at {fa/1e3:.1f} kHz in zone 1.")
        self.explain_var.set(msg)

    # -- shutdown ----------------------------------------------------------
    def _on_close(self):
        self.worker.stop()
        # give the worker a moment to release hardware
        self.root.after(300, self.root.destroy)


# ===========================================================================
#  Entry point
# ===========================================================================
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Sinc Folding Interactive Explorer — a polished ADI "
                    "dashboard for exploring Nyquist folding / aliasing.")
    p.add_argument("-m", "--m2k_uri", default=None,
                   help="LibIIO context URI of the ADALM2000")
    p.add_argument("-a", "--ad4080_uri", default="serial:COM4,230400",
                   help="LibIIO context URI of the VAL-AD4080ARDZ")
    p.add_argument("-d", "--decimation", type=int, default=256,
                   choices=[2, 4, 8, 16, 32, 64, 128, 256, 512, 1024],
                   help="AD4080 sinc1 decimation / OSR (F-12-01: type=int).")
    p.add_argument("--simulate", action="store_true",
                   help="Run with a synthetic device — no hardware needed.")
    p.add_argument("--theme", choices=["dark", "light"], default="dark",
                   help="Dashboard theme.")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not args.simulate and gn is None:
        print("genalyzer not available — falling back to --simulate.")
        args.simulate = True

    cfg = {
        "simulate": args.simulate,
        "m2k_uri": args.m2k_uri,
        "ad4080_uri": args.ad4080_uri,
        "decimation": args.decimation,
        "theme": args.theme,
        "fs_pre": 40e6,          # AD4080 fixed pre-decimation rate
        "fs_out": 750000,        # M2K DAC rate
        "nfft": 512,
        "navg": 4,
        "npts": 4 * 512,
        "init_center": 40e6 / args.decimation + 5000,
    }

    root = tk.Tk()
    SincFoldingExplorer(root, cfg)
    root.mainloop()


if __name__ == "__main__":
    main()
