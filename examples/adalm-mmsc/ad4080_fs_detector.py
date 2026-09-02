# Copyright (C) 2025 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD
#
# AD4080 Sample-Rate Detector -- polished dashboard edition.
#
# This is a redesigned GUI for the ADALM-MMSC DSP curriculum, applying the same
# principles as sinc_folding_explorer.py to the #07 sample-rate detector
# (ad4080_detect_fs.py).  The original file is left untouched.
#
#     +-----------------------------------------------------------+
#     | ADI logo | AD4080 Sample-Rate Detector                    |
#     +-----------------------------------------------------------+
#     |  M2K generates a known tone -> AD4080 samples it -> the   |
#     |  FFT peak bin back-computes the ADC sample rate.          |
#     +----------------+---------------------------+--------------+
#     |  CONTROLS      |   TIME + FFT (dominant)   |  LIVE        |
#     |  - M2K freq    |   peak bin marked         |  METRICS     |
#     |  - Buffer size |                           |  ADC reports |
#     |  - Interp on/off                           |  Measured fs |
#     |  - Reset/Pause |                           |  Error %     |
#     +----------------+---------------------------+--------------+
#     |  Explanation panel (why integer bins misread fs)          |
#     +-----------------------------------------------------------+
#
# INTEGRATED source+sink.  Unlike the original (which had NO M2K code and just
# said "apply a 100 kHz tone" externally), this GUI drives the M2K itself: the
# "M2K source frequency" control is the tone it commands, so there is no separate
# generator to run and no mystery "assumed" frequency -- the assumption IS the
# command.  The M2K plays from its 7.5 MHz crystal and the AD4080 samples on a
# clock set by the on-board S2 hex knob (80 MHz crystal / divider; see below), so
# back-computing fs from the commanded tone is a genuine cross-check, not a
# tautology.
#
# The teaching point of #07 survives: integer-bin peak detection is coarse -- a
# 100 kHz tone in an 8192-pt buffer at 40 MHz has its true peak at bin 20.48,
# argmax rounds to 20, and fs back-computes to 40.96 MHz (+2.4%).  This GUI makes
# that visible and lets the user *fix* it live with parabolic interpolation.
#
# Fixes baked in vs the original (ad4080_detect_fs.py):
#   * F-07-01 -- optional parabolic (quadratic) interpolation on the peak bin, so
#     the measured fs error drops from ~2.4% to well under 0.1%.  Toggle live.
#   * F-07-02 -- the acquisition loop lives in a worker thread the GUI can stop
#     cleanly; no unbounded `while True` blocking the process.
#   * F-07-03 -- the tone frequency is a control (and a CLI arg) that the M2K
#     actually generates, not a hardcoded 100000 assumed to be present.
#   * F-07-05 -- no-signal is detected and reported ("No input tone detected"),
#     never an OverflowError: DC/near-DC peaks and flat (std~0) captures are
#     guarded before the fs division.
#
# WHY MEASURE fs AT ALL -- the driver can't tell you the truth.  On this eval
# board (drawing 02-087156-01-e, sheet 3 "CLOCK GENERATOR") the AD4080 CNV clock
# is generated ENTIRELY IN HARDWARE: an 80 MHz crystal (Y14) feeds a CD74AC163
# counter whose divider is chosen by the S2 hex rotary knob (PT65503):
#
#       S2:  14 -> 40 MHz (default)   10 -> 13.33     6 -> 8.00     2 -> 5.71
#            13 -> 26.66              9 -> 11.42      5 -> 7.27     1 -> 5.33
#            12 -> 20.00             8 -> 10.00      4 -> 6.66     0 -> 5.00
#            11 -> 16.00             7 ->  8.88      3 -> 6.15    15 -> NO CLOCK
#       (fs = 80 MHz / (16 - S2))
#
# The S2 position is NOT wired back to the ADC or the MAX32690, so pyadi has no
# register to read it: `sampling_frequency` and `sampling_frequency_available`
# are HARDCODED to 40000000 and never move -- not with S2, and not with
# filter_type/oversampling_ratio either (all 31 combos still report 40 MHz on
# this firmware; sinc modes decimate the DATA rate to 40/OSR but the attribute
# still says 40 MHz).  So the driver's reported rate is only correct when
# S2 = 14 and filter = none.  Whenever it isn't, the tone-measured fs is the ONLY
# source of truth -- which is the whole reason example #07 exists.
#
# This GUI therefore treats the measured fs as the answer, snaps it to the S2
# table to name the knob position, and shows the driver's 40 MHz merely as the
# rate "the driver assumes (can't read S2)" -- never as a red error.  The true
# data rate is 80 MHz/(16-S2)/OSR; the tone must sit below half of THAT (and
# below the M2K Nyquist 3.75 MHz) or it aliases and the math is meaningless.
#
# Usage:
#   python ad4080_fs_detector.py --simulate                       # no hardware
#   python ad4080_fs_detector.py -u serial:COM4,230400            # live bench
#   python ad4080_fs_detector.py -u serial:COM4,230400 -m ip:192.168.2.1
#   python ad4080_fs_detector.py -u serial:COM4,230400 --theme light

import argparse
import queue
import time
import threading
import tkinter as tk
from threading import Thread
from tkinter import ttk

import numpy as np

from mmsc_gui_theme import MMSCTheme


# ===========================================================================
#  DSP: peak detection with optional sub-bin interpolation
# ===========================================================================
def detect_fs(mag_spec, n, f_in, interpolate=True, dc_guard=3, min_prom_db=6.0):
    """Back-compute the sample rate from an FFT magnitude spectrum.

    Returns (fs, peak_bin_float, status) where status is "" on success or a
    human-readable reason on failure (no crash -- fixes F-07-05).

    * mag_spec : one-sided magnitude spectrum in dB
    * n        : length of the original time record
    * f_in     : assumed input tone frequency (Hz) -- fixes F-07-03
    * interpolate : parabolic peak interpolation -- fixes F-07-01
    * dc_guard : ignore the first few bins so DC doesn't win (part of F-07-05)
    * min_prom_db : peak must stand this far above the median floor to count as
                    a tone; a flat / dead-rail spectrum has ~0 prominence, so this
                    (not just bin==0) is what actually catches F-07-05.
    """
    if mag_spec is None or len(mag_spec) <= dc_guard + 1:
        return None, None, "No spectrum"

    # Exclude the DC neighborhood so a flat/DC input can't peak at bin 0.
    search = mag_spec.copy()
    search[:dc_guard] = -np.inf
    max_bin = int(np.argmax(search))

    if max_bin <= 0:
        return None, None, "No input tone detected — check the source / wiring"

    # Prominence guard (F-07-05): a dead rail / no tone yields a flat spectrum
    # whose peak barely clears the floor. Bail before dividing to compute fs.
    finite = mag_spec[np.isfinite(mag_spec)]
    floor = float(np.median(finite)) if len(finite) else -np.inf
    if mag_spec[max_bin] - floor < min_prom_db:
        return None, None, "No input tone detected — check the source / wiring"

    bin_f = float(max_bin)
    if interpolate and 0 < max_bin < len(mag_spec) - 1:
        # Quadratic (parabolic) interpolation on the log-magnitude peak.
        a = mag_spec[max_bin - 1]
        b = mag_spec[max_bin]
        c = mag_spec[max_bin + 1]
        denom = (a - 2.0 * b + c)
        if denom != 0:
            delta = 0.5 * (a - c) / denom      # in [-0.5, +0.5]
            bin_f = max_bin + float(np.clip(delta, -0.5, 0.5))

    if bin_f <= 0:
        return None, bin_f, "Peak at DC — no tone"

    fs = f_in * n / bin_f
    return fs, bin_f, ""


# ===========================================================================
#  S2 clock knob: fs = 80 MHz / (16 - S2).  See the CLOCK GENERATOR block on
#  sheet 3 of drawing 02-087156-01-e.  This table is the board's ground truth;
#  pyadi cannot read S2, so we infer it from the measured rate.
# ===========================================================================
CLOCK_XTAL = 80_000_000.0
# {S2 position: fs in Hz}.  15 = NO CLOCK (omitted).  Values match the silkscreen.
S2_TABLE = {n: CLOCK_XTAL / (16 - n) for n in range(0, 15)}


def snap_to_s2(fs_measured, tol=0.02):
    """Map a measured *modulator* rate to the nearest S2 knob position.

    Returns (s2, fs_table, within_tol).  `fs_measured` must already be the CNV
    modulator rate, i.e. any sinc/OSR decimation multiplied back out, because the
    S2 divider sits before the digital filter.  within_tol is True when the
    measurement lands within `tol` (fractional) of a table entry -- that's the
    self-check that the reading is trustworthy.
    """
    if not fs_measured or fs_measured <= 0:
        return None, None, False
    best = min(S2_TABLE.items(), key=lambda kv: abs(kv[1] - fs_measured))
    s2, fs_table = best
    within = abs(fs_table - fs_measured) / fs_table <= tol
    return s2, fs_table, within


# ===========================================================================
#  Hardware / simulation worker thread
# ===========================================================================
class DetectorWorker(Thread):
    """Owns the AD4080 (or simulates it) and streams captures to the GUI.

    command_q : GUI -> worker  (f_in / buffer-size / pause changes)
    result_q  : worker -> GUI  (latest {time, mag_spec, std, status})
    """

    # M2K analog-output (source) parameters -- mirror m2k_gen_100k.py /
    # m2k_source_ad4080_sink.py: 7.5 MHz DAC rate, ~0.9 V differential.
    FS_OUT = 7_500_000          # M2K DAC sample rate (Nyquist 3.75 MHz)
    AMPL = 0.9                  # volts per leg

    def __init__(self, cfg, command_q, result_q):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.command_q = command_q
        self.result_q = result_q
        self.running = True
        self.paused = False
        self._f_in = cfg["f_in"]
        self._nbuf = cfg["nbuf"]
        self._fs_true = cfg["fs_true"]   # simulated S2 clock rate (live-settable)
        self.rng = np.random.default_rng(0)

    def stop(self):
        self.running = False

    # AD4080 code scaling for the simulation -- match what the live bench shows.
    # A ~0.9 V differential tone reads std ~66000 codes on hardware; a cosine of
    # amplitude A has std = A/sqrt(2), so A ~= 93000 gives std ~= 66000.
    SIM_AMP_CODES = 93000.0     # peak code amplitude of the simulated tone
    SIM_NOISE_CODES = 180.0     # broadband noise floor (codes RMS)
    SIM_FULLSCALE = 524287.0    # 2**19 - 1 (dead-rail value)

    def _m2k_cycles_n(self, f_in):
        """Integer-cycle (cycles, n) the M2K uses for a seamless cyclic buffer.

        Seamless cyclic playback needs the buffer to hold a whole number of
        cycles; we pick ~one buffer's worth of samples, round to a whole cycle
        count, then size n to match. Shared by the buffer builder and the sim so
        both model the SAME quantized tone the DAC actually plays.
        """
        f_in = max(1.0, float(f_in))
        target_len = 8192
        cycles = max(1, int(round(target_len * f_in / self.FS_OUT)))
        n = int(round(cycles * self.FS_OUT / f_in))
        return cycles, n

    def _m2k_gen_freq(self, f_in):
        """The frequency the M2K *actually* plays (integer-cycle quantized).

        A cyclic buffer of `n` samples holding `cycles` whole cycles replays at
        cycles*FS_OUT/n -- close to f_in but quantized. This tiny offset is real
        on the bench, so the sim uses it too instead of the exact f_in.
        """
        cycles, n = self._m2k_cycles_n(f_in)
        return cycles * self.FS_OUT / n

    def _m2k_buffer(self, f_in):
        """Build the cyclic cosine buffer the M2K DAC plays."""
        cycles, n = self._m2k_cycles_n(f_in)
        t = np.arange(n) / self.FS_OUT
        return self.AMPL * np.cos(2 * np.pi * f_in * t)

    def _drain_commands(self):
        try:
            while True:
                cmd, val = self.command_q.get_nowait()
                if cmd == "f_in":
                    self._f_in = val
                elif cmd == "nbuf":
                    self._nbuf = val
                elif cmd == "pause":
                    self.paused = val
                elif cmd == "nosignal":
                    self.cfg["sim_nosignal"] = val
                elif cmd == "fs_true":
                    self._fs_true = val
        except queue.Empty:
            pass

    def _emit(self, **kw):
        try:
            while True:
                self.result_q.get_nowait()
        except queue.Empty:
            pass
        self.result_q.put(kw)

    @staticmethod
    def _spectrum(data):
        data_win = (data - np.average(data)) * np.blackman(len(data))
        mag = np.abs(np.fft.fft(data_win) / len(data_win))[: len(data_win) // 2]
        mag_db = 20 * np.log10(mag + 1e-12)
        return mag_db

    def _open_ad4080(self):
        """Open the AD4080 context and apply the rx timeout. Raises on failure.

        Factored out so the initial connect AND the post-wedge reconnect share
        one path. A stopped-clock wedge (S2=15) kills the board's firmware until
        the USB is replugged; reopening the context is the only way back, and it
        can't be done in-place -- the old context object is dead.
        """
        from adi import ad4080
        adc = ad4080(uri=self.cfg["uri"], device_name="ad4080")
        rx_timeout_ms = int(self.cfg.get("rx_timeout_ms", 5000) or 0)
        if rx_timeout_ms > 0:
            try:
                adc._ctx.set_timeout(rx_timeout_ms)
            except Exception:
                pass
        return adc

    def _reconnect_ad4080(self, adc):
        """Tear down a wedged AD4080 context and poll until the board is back.

        Returns a fresh, opened adc once the user replugs the USB, or None if
        the worker was asked to stop first. The M2K handle is untouched (it's a
        separate USB device, unaffected by the AD4080 clock).
        """
        # Release the dead context so the OS frees the COM port for re-enumeration.
        try:
            adc.rx_destroy_buffer()
        except Exception:
            pass
        try:
            adc._ctx.set_timeout(0)
        except Exception:
            pass
        try:
            del adc
        except Exception:
            pass

        while self.running:
            self._drain_commands()      # keep Pause/Reset responsive while waiting
            self._emit(
                status="Board unresponsive — the no-clock capture wedged the "
                       "AD4080 firmware. UNPLUG then REPLUG the AD4080 USB; it "
                       "will auto-reconnect. (If Windows assigns a new COM port, "
                       "restart with -u serial:COMx.)",
                data=np.zeros(self._nbuf), mag_spec=None, std=0.0, fs_true=None)
            try:
                new_adc = self._open_ad4080()
            except Exception:
                time.sleep(1.0)         # port not back yet -> keep polling
                continue
            self._emit(status="Reconnected to AD4080. Resuming…",
                       data=np.zeros(self._nbuf), mag_spec=None, std=0.0,
                       fs_true=None)
            return new_adc
        return None

    def _rx_with_watchdog(self, adc, timeout_s):
        """adc.rx() but guaranteed to return within ~timeout_s.

        On the Windows serial backend, Context.set_timeout() does NOT interrupt
        a stuck iio.Buffer.refill() -- if the CNV clock stops (S2=15, pulled
        jumper) rx() blocks forever inside libiio and no Python-level guard can
        catch it. The ONLY thing that unblocks a hung refill is
        iio.Buffer.cancel() called from ANOTHER thread. So we arm a watchdog
        timer that cancels the in-flight buffer on deadline; the cancelled
        refill then raises inside rx(), which we re-raise as a timeout the main
        loop's except-block turns into the "no clock" message.
        """
        fired = {"cancelled": False}

        def _cancel():
            fired["cancelled"] = True
            buf = getattr(adc, "_rxbuf", None)
            # _rxbuf may be a live iio.Buffer (has .cancel) or [] / None.
            if buf is not None and hasattr(buf, "cancel"):
                try:
                    buf.cancel()
                except Exception:
                    pass

        wd = threading.Timer(timeout_s, _cancel)
        wd.daemon = True
        wd.start()
        try:
            data = np.asarray(adc.rx(), dtype=float)
        except Exception as exc:
            if fired["cancelled"]:
                raise TimeoutError(
                    f"rx() cancelled after {timeout_s:.1f}s (clock stopped?)"
                ) from exc
            raise
        finally:
            wd.cancel()
        if fired["cancelled"]:
            # rx() returned but the watchdog had already fired -- treat as a
            # timeout so the buffer gets rebuilt (a cancelled buffer is dead).
            raise TimeoutError(
                f"rx() cancelled after {timeout_s:.1f}s (clock stopped?)")
        return data

    def run(self):
        if self.cfg["simulate"]:
            self._run_sim()
        else:
            self._run_hardware()

    # -- simulation --------------------------------------------------------
    def _run_sim(self):
        """Model the SAME source->sink chain as the live path, in software.

        Mirrors _run_hardware as closely as possible so the GUI behaves the same
        with or without hardware:
          * the "M2K" plays an integer-cycle-quantized tone (_m2k_gen_freq), not
            a perfect f_in -- so the tiny bench frequency offset is present;
          * the "AD4080" samples that tone at fs_true (the S2 clock rate) with
            realistic code amplitude (std ~66000) and a noise floor;
          * a dead-rail (no-signal) case reads constant full-scale, std ~ 0;
          * the same status-line style, an M2K re-tune settle pause, and the
            stale-first-buffer discard after a buffer-size change.
        cfg["fs_true"] stands in for the S2-selected sample rate.
        """
        cfg = self.cfg
        # Emulate the two connect steps the live path shows.
        self._emit(status="Connecting to M2K (source)… [SIM]",
                   data=np.zeros(self._nbuf), mag_spec=None, std=0.0,
                   fs_true=None)
        time.sleep(0.1)
        fs_true = self._fs_true
        s2, fs_tab, _ = snap_to_s2(fs_true)
        knob = f"S2={s2}" if s2 is not None else "?"
        self._emit(status=f"Connected [SIM {knob}]  fs = {fs_true/1e6:.4f} MHz",
                   data=np.zeros(self._nbuf), mag_spec=None, std=0.0,
                   fs_true=fs_true)

        applied_nbuf = None
        applied_fin = None
        applied_fs = fs_true
        while self.running:
            self._drain_commands()
            if self.paused:
                time.sleep(0.05)
                continue

            # "S2 knob turned": the user selected a new hardware clock rate.
            # Recompute the true fs + inferred knob label, and settle like a
            # real clock change would.
            fs_true = self._fs_true
            if fs_true != applied_fs:
                applied_fs = fs_true
                if fs_true <= 0:
                    knob = "S2=15"
                    self._emit(
                        status="Clock set to [SIM S2=15]  NO CLOCK — "
                               "ADC receives no CNV edges",
                        data=np.zeros(self._nbuf), mag_spec=None, std=0.0,
                        fs_true=None)
                else:
                    s2, fs_tab, _ = snap_to_s2(fs_true)
                    knob = f"S2={s2}" if s2 is not None else "?"
                    self._emit(
                        status=f"Clock set to [SIM {knob}]  fs = {fs_true/1e6:.4f} MHz",
                        data=np.zeros(self._nbuf), mag_spec=None, std=0.0,
                        fs_true=fs_true)
                time.sleep(0.15)

            # "M2K re-tune": same settle pause as the hardware push path.
            if self._f_in != applied_fin:
                applied_fin = self._f_in
                time.sleep(0.15)

            # "Buffer-size change": discard one frame like the stale-first-buffer
            # behavior on hardware, so the GUI's re-arm timing feels the same.
            n = self._nbuf
            if n != applied_nbuf:
                applied_nbuf = n
                time.sleep(0.02)

            if fs_true <= 0:
                # S2=15: no CNV clock -> the ADC never converts. No spectrum,
                # no fs to recover; the whole point of this position.
                self._emit(
                    status="[SIM S2=15] NO CLOCK — no conversions; "
                           "turn S2 to 0–14 to sample",
                    data=np.zeros(n), mag_spec=None, std=0.0, fs_true=None)
                time.sleep(0.25)
                continue

            if cfg.get("sim_nosignal"):
                # Dead-rail: constant full-scale, std ~ 0 (the no-signal case).
                data = np.full(n, self.SIM_FULLSCALE)
            else:
                # The M2K plays the integer-cycle-quantized tone; the AD4080
                # samples it at fs_true. Two independent rates, same as bench.
                f_gen = self._m2k_gen_freq(self._f_in)
                t = np.arange(n) / fs_true
                data = self.SIM_AMP_CODES * np.cos(2 * np.pi * f_gen * t)
                data += self.rng.standard_normal(n) * self.SIM_NOISE_CODES

            std = float(np.std(data))
            mag = self._spectrum(data)
            note = "  [check wiring: flat input]" if std < 1.0 else ""
            self._emit(
                status=f"Driving {self._f_in/1e3:.1f} kHz  →  [SIM {knob}]  "
                       f"std={std:.0f} codes{note}",
                data=data, mag_spec=mag, std=std, fs_true=fs_true)
            time.sleep(0.25)

    # -- live hardware -----------------------------------------------------
    def _run_hardware(self):
        """Drive the M2K source AND read the AD4080 sink from one thread.

        The GUI's "input frequency" control is now the tone this thread commands
        the M2K to generate -- not a blind assumption. Because the M2K plays from
        its own 7.5 MHz crystal and the AD4080 samples on its own 40 MHz crystal
        (two independent clocks), back-computing fs from the commanded tone is a
        genuine cross-check of the ADC clock, not a tautology.
        """
        cfg = self.cfg
        import libm2k
        from adi import ad4080

        # --- open the M2K source ---
        self._emit(status="Connecting to M2K (source)…",
                   data=np.zeros(self._nbuf), mag_spec=None, std=0.0,
                   fs_true=None)
        m2k = libm2k.m2kOpen(cfg["m2k_uri"]) if cfg.get("m2k_uri") \
            else libm2k.m2kOpen()
        if m2k is None:
            self._emit(status="ERROR: M2K not found (is it connected / free?)",
                       data=np.zeros(self._nbuf), mag_spec=None, std=0.0,
                       fs_true=None)
            return
        try:
            m2k.calibrateDAC()
        except Exception:
            pass
        aout = m2k.getAnalogOut()
        aout.setSampleRate(0, self.FS_OUT)
        aout.setSampleRate(1, self.FS_OUT)
        aout.enableChannel(0, True)
        aout.enableChannel(1, True)   # AD4080 input is DIFFERENTIAL -> drive both
        aout.setCyclic(True)

        # --- open the AD4080 sink ---
        # Blocking rx() defenses. If the sample clock stops -- S2=15 ("no clock")
        # on the board, a pulled clock jumper, or a wedged MAX32690 -- rx() blocks
        # forever inside libiio's Buffer.refill() and the daemon worker wedges
        # INSIDE the call. A blocking call never throws, so the per-iteration
        # try/except can't catch it. TWO host-side defenses:
        #   1. Context.set_timeout() -- helps on backends that honor it, but on
        #      the Windows serial backend it does NOT interrupt a stuck refill
        #      (confirmed on-bench: S2->15 hung with only this in place).
        #   2. _rx_with_watchdog() -- a Timer thread calls Buffer.cancel() on
        #      deadline, which is the ONLY thing that unblocks a hung refill.
        # BUT: unblocking the HOST doesn't revive the BOARD. On-bench, S2=15
        # wedges the AD4080 firmware itself -- the context stays dead until the
        # USB is physically replugged. So a run of timeouts triggers a full
        # teardown + reconnect-poll (see _reconnect_ad4080), not just a retry.
        self._emit(status="Connecting to AD4080 (sink)…",
                   data=np.zeros(self._nbuf), mag_spec=None, std=0.0,
                   fs_true=None)
        rx_timeout_ms = int(cfg.get("rx_timeout_ms", 5000) or 0)
        try:
            adc = self._open_ad4080()
        except Exception as exc:
            libm2k.contextClose(m2k)
            self._emit(status=f"ERROR: AD4080 not found ({exc})",
                       data=np.zeros(self._nbuf), mag_spec=None, std=0.0,
                       fs_true=None)
            return   # older libiio without set_timeout -> keep default
        # Watchdog deadline (s): a hair above set_timeout so the C-level timeout
        # gets first crack on backends that honor it; the watchdog is the
        # backstop. Floor of 3 s if timeouts are disabled.
        wd_timeout_s = (rx_timeout_ms / 1000.0 + 0.5) if rx_timeout_ms > 0 else 3.0

        # Do NOT force filter_type. fs is a deliberate hardware selection
        # (filter_type x oversampling_ratio -> sampling_frequency); we READ it.
        def _read_cfg():
            try:
                filt = str(adc.filter_type)
            except Exception:
                filt = "?"
            try:
                osr = int(float(adc.oversampling_ratio))
            except Exception:
                osr = None
            try:
                fs = float(adc.sampling_frequency)
            except Exception:
                fs = None
            return filt, osr, fs

        filt0, osr0, fs_true = _read_cfg()
        cfg0 = filt0 if filt0 == "none" else f"{filt0}/OSR{osr0}"
        self._emit(status=f"Connected  [{cfg0}]  fs = "
                          f"{fs_true/1e6:.4f} MHz" if fs_true else "Connected",
                   data=np.zeros(self._nbuf), mag_spec=None, std=0.0,
                   fs_true=fs_true, filt=filt0, osr=osr0)

        applied_nbuf = None   # force a buffer (re)build on the first pass
        last_good_nbuf = None  # last size that actually allocated + captured
        applied_fin = None    # force an M2K push on the first pass
        fail_streak = 0       # consecutive capture failures -> board wedge detector
        # One failure is a transient; a run of them means the board firmware is
        # wedged (S2=15) or the USB link dropped, and it won't come back without
        # a replug. NOTE: match on the STREAK, not on specific errno numbers --
        # a stopped clock surfaces differently per backend (Linux errno 110
        # "timed out"; the watchdog's TimeoutError; Windows serial errno 121
        # "semaphore timeout"/link failure). Chasing errnos missed 121 and
        # looped "Capture retry" forever; counting any sustained failure works.
        WEDGE_AFTER = 2

        try:
            while self.running:
                self._drain_commands()
                if self.paused:
                    time.sleep(0.05)
                    continue

                # Each iteration is wrapped so a transient hardware hiccup (a
                # timed-out rx() after a big buffer realloc over serial, etc.)
                # reports to the GUI and the loop RETRIES -- rather than throwing
                # out of this daemon worker, which would leave the GUI frozen with
                # no error (that was the "dead on buffer-size change" symptom).
                try:
                    # (Re)push the M2K tone when the commanded frequency changes.
                    # NOTE: do NOT call aout.stop() before the push -- on a cyclic
                    # output a fresh push replaces the running waveform in place,
                    # but stop() disables the channels and a subsequent push comes
                    # out at ~1/50th amplitude unless re-enabled (same family as
                    # the reset()-ordering DAC-disable bug, F-15-07).
                    if self._f_in != applied_fin:
                        wf = self._m2k_buffer(self._f_in)
                        aout.push([wf, -wf])   # antiphase differential (W1/W2)
                        applied_fin = self._f_in
                        time.sleep(0.15)       # let the DAC settle

                    # A buffer-size change only takes effect after the cached
                    # buffer is destroyed: pyadi's _rx_buffered_data allocates
                    # only `if not self._rxbuf`, so reassigning rx_buffer_size
                    # alone is ignored until rx_destroy_buffer() nulls it.
                    if self._nbuf != applied_nbuf:
                        adc.rx_destroy_buffer()
                        adc.rx_buffer_size = self._nbuf
                        applied_nbuf = self._nbuf
                        # First refill after (re)init returns a stale buffer ->
                        # read once and discard before trusting the data
                        # (F-06-06/F-15-08; cf. ad4080_m2k_filter_sweep.py
                        # lines 111-112). Watchdog-guarded: a stopped clock
                        # hangs this FIRST refill, before the real capture.
                        self._rx_with_watchdog(adc, wd_timeout_s)

                    data = self._rx_with_watchdog(adc, wd_timeout_s)
                    last_good_nbuf = self._nbuf   # this size works
                    fail_streak = 0               # a good capture clears the wedge
                except Exception as exc:
                    # A capture failed. Reset the rx buffer so the next pass
                    # rebuilds cleanly, keep the worker alive, and decide whether
                    # this is (a) a too-big-buffer alloc we can recover by
                    # shrinking N, or (b) a wedged board that needs a USB replug.
                    try:
                        adc.rx_destroy_buffer()
                    except Exception:
                        pass
                    failed = self._nbuf
                    exc_txt = str(exc).lower()

                    # (a) RECOVERABLE: a bigger buffer than this transport can
                    # allocate (e.g. 32768 -> OSError 997) fails ONLY at the new
                    # size; a smaller size that worked before still will. Shrink
                    # back and DON'T count it as a wedge. Gate on having a proven
                    # smaller size so a first-pass failure can't masquerade as this.
                    is_alloc = ("errno 997" in exc_txt or "-997" in exc_txt
                                or "cannot allocate" in exc_txt
                                or "out of memory" in exc_txt)
                    if is_alloc and last_good_nbuf and last_good_nbuf != failed:
                        self._nbuf = last_good_nbuf
                        applied_nbuf = None
                        self._emit(
                            status=f"N={failed} failed to allocate ({exc}); "
                                   f"fell back to N={last_good_nbuf}",
                            data=np.zeros(self._nbuf), mag_spec=None, std=0.0,
                            fs_true=None)
                        time.sleep(0.2)
                        continue

                    # (b) EVERYTHING ELSE is treated as a possible board wedge.
                    # Do NOT match specific errno numbers -- a stopped clock /
                    # dropped link surfaces as errno 110 (Linux), the watchdog's
                    # TimeoutError, OR Windows serial errno 121 ("semaphore
                    # timeout"). One is a transient; a STREAK means the firmware
                    # is wedged and only a replug revives it -> stop hammering the
                    # dead port and hand off to the reconnect poll.
                    fail_streak += 1
                    if fail_streak >= WEDGE_AFTER:
                        adc = self._reconnect_ad4080(adc)
                        if adc is None:
                            return   # worker stopped while waiting to replug
                        fail_streak = 0
                        applied_nbuf = None   # rebuild buffer on fresh context
                        applied_fin = None    # re-push M2K tone after reconnect
                        continue
                    # First failure of a streak: show the likely cause and retry
                    # once before escalating to the replug prompt.
                    applied_nbuf = None
                    self._emit(
                        status=f"No data (capture failed, N={failed}): CNV clock may "
                               f"be stopped — check S2 knob (15 = no clock). "
                               f"[{exc}]",
                        data=np.zeros(self._nbuf), mag_spec=None, std=0.0,
                        fs_true=None)
                    time.sleep(0.2)
                    continue

                std = float(np.std(data))
                mag = self._spectrum(data)
                filt, osr, fs_true = _read_cfg()
                cfg_str = filt if filt == "none" else f"{filt}/OSR{osr}"
                # A flat rail (std ~ 0) is the differential dead-rail signature
                # (F-07-05) OR a stopped clock returning a held/stale buffer.
                note = ("  [flat input: check wiring OR CNV clock (S2 knob)]"
                        if std < 1.0 else "")
                self._emit(
                    status=f"Driving {self._f_in/1e3:.1f} kHz  →  [{cfg_str}]  "
                           f"std={std:.0f} codes{note}",
                    data=data, mag_spec=mag, std=std, fs_true=fs_true,
                    filt=filt, osr=osr)
        finally:
            # adc is None if the worker stopped while polling for a USB replug
            # (_reconnect_ad4080 already released the dead context in that case).
            if adc is not None:
                # Restore the context timeout before releasing. libiio exposes no
                # get_timeout, so we can't save/restore the prior value; reset to
                # 0 (backend default = block indefinitely) so we don't leave a
                # short timeout on a context another tool might reuse.
                if rx_timeout_ms > 0:
                    try:
                        adc._ctx.set_timeout(0)
                    except Exception:
                        pass
                try:
                    adc.rx_destroy_buffer()
                except Exception:
                    pass
                try:
                    del adc
                except Exception:
                    pass
            try:
                aout.stop()
            except Exception:
                pass
            try:
                libm2k.contextClose(m2k)
            except Exception:
                pass
            self._emit(status="Devices released (M2K + AD4080)",
                       data=np.zeros(self._nbuf), mag_spec=None, std=0.0,
                       fs_true=fs_true)


# ===========================================================================
#  The GUI application
# ===========================================================================
class FsDetectorApp:
    # 32768 is intentionally omitted: on the AD4080 serial backend the iio
    # buffer allocation for 32768 samples fails hard (OSError 997) -- 16384 is
    # the largest single buffer this transport can allocate. Measured on-bench:
    # 8192 ~0.85 s, 16384 ~1.69 s per capture; 32768 never allocates.
    NBUF_OPTIONS = [1024, 2048, 4096, 8192, 16384]

    def __init__(self, root, cfg):
        self.root = root
        self.cfg = cfg
        self.theme = MMSCTheme(cfg["theme"])
        self.command_q = queue.Queue()
        self.result_q = queue.Queue()
        self.latest = None
        self.f_in = cfg["f_in"]
        self.nbuf = cfg["nbuf"]
        self.interp = tk.BooleanVar(value=True)
        self.show_time = tk.BooleanVar(value=True)

        root.title("ADALM-MMSC · AD4080 Sample-Rate Detector")
        root.geometry("1280x820")
        root.minsize(1080, 720)
        self.theme.apply(root)

        self._build_layout()

        self.worker = DetectorWorker(cfg, self.command_q, self.result_q)
        self.worker.start()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll()

    # -- layout ------------------------------------------------------------
    def _build_layout(self):
        t = self.theme
        mode = "SIMULATION" if self.cfg["simulate"] else "LIVE HARDWARE"
        t.build_header(
            self.root, "AD4080 Sample-Rate Detector",
            subtitle=f"ADALM-MMSC DSP Curriculum   ·   {mode}",
        ).pack(fill="x")
        t.build_banner(
            self.root,
            "The M2K sends a known tone; the FFT peak bin back-computes the true "
            "sample rate — then snaps it to the S2 clock knob. The driver can't "
            "read S2 (it always says 40 MHz), so the measured rate is the truth.",
        ).pack(fill="x")

        body = ttk.Frame(self.root, style="TFrame")
        body.pack(fill="both", expand=True, padx=10, pady=(6, 4))
        body.columnconfigure(0, weight=0, minsize=290)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=0, minsize=250)
        body.rowconfigure(0, weight=1)

        self._build_controls(body)
        self._build_plots(body)
        self._build_metrics(body)
        self._build_explanation(self.root)

    def _build_controls(self, parent):
        t = self.theme
        panel = tk.Frame(parent, bg=t["panel"])
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        wrap, b = t.section(panel, "Controls")
        wrap.pack(fill="both", expand=True)

        # --- M2K source frequency (the GUI commands this tone) F-07-03 ---
        src = "M2K source frequency" if not self.cfg["simulate"] \
            else "Input frequency (simulated)"
        tk.Label(b, text=src, bg=t["panel"],
                 fg=t["text"], font=t.f_body).pack(anchor="w")
        self.freq_val = tk.StringVar(value=f"{self.f_in/1e3:.1f} kHz")
        tk.Label(b, textvariable=self.freq_val, bg=t["panel"],
                 fg=t["accent"], font=(t.mono, 13, "bold")).pack(anchor="w")
        # M2K Nyquist is FS_OUT/2 = 3.75 MHz; keep the slider well inside it.
        self.freq_scale = ttk.Scale(
            b, from_=1000, to=1_000_000, orient="horizontal",
            style="MMSC.Horizontal.TScale", command=self._on_freq,
        )
        self.freq_scale.set(self.f_in)
        self.freq_scale.pack(fill="x", pady=(2, 2))
        hint = ("the M2K generates exactly this tone into the AD4080"
                if not self.cfg["simulate"]
                else "the simulated tone is exactly here")
        tk.Label(b, text=hint,
                 bg=t["panel"], fg=t["text_dim"], font=t.f_small).pack(
            anchor="w", pady=(0, 10))

        # --- buffer size ---
        tk.Label(b, text="FFT buffer size (N)", bg=t["panel"],
                 fg=t["text"], font=t.f_body).pack(anchor="w")
        self.nbuf_combo = ttk.Combobox(
            b, values=[str(x) for x in self.NBUF_OPTIONS],
            state="readonly", style="TCombobox",
        )
        self.nbuf_combo.set(str(self.nbuf))
        self.nbuf_combo.bind("<<ComboboxSelected>>", self._on_nbuf)
        self.nbuf_combo.pack(fill="x", pady=(2, 10))

        # --- interpolation toggle (the star feature) ---
        ttk.Checkbutton(
            b, text="Parabolic peak interpolation",
            variable=self.interp, command=self._on_interp,
        ).pack(anchor="w", pady=(2, 2))
        tk.Label(b, text="off = integer bin (coarse); on = sub-bin (accurate)",
                 bg=t["panel"], fg=t["text_dim"], font=t.f_small).pack(
            anchor="w", pady=(0, 10))

        # --- simulate-only: the S2 hardware clock knob ---
        # On the bench, fs is set by the S2 hex rotary switch (80 MHz/(16-N)),
        # which pyadi cannot read. In sim we expose it so the user can "turn the
        # knob" and watch the detector recover fs, instead of passing --fs_true.
        if self.cfg["simulate"]:
            tk.Frame(b, bg=t["border"], height=1).pack(fill="x", pady=(2, 8))
            tk.Label(b, text="S2 clock knob (hardware)", bg=t["panel"],
                     fg=t["text"], font=t.f_body).pack(anchor="w")
            # Ordered like the real hex switch: S2=15 (no clock) at the top,
            # then high fs at S2=14 down to S2=0.
            self._s2_order = [15] + list(range(14, -1, -1))
            self._s2_labels = {}
            for n in self._s2_order:
                if n == 15:
                    self._s2_labels[n] = "S2=15  →  NO CLOCK"
                else:
                    self._s2_labels[n] = f"S2={n}  →  {S2_TABLE[n]/1e6:.3f} MHz"
            self._s2_by_label = {v: k for k, v in self._s2_labels.items()}
            # fs the knob commands; S2=15 = 0.0 (no CNV clock -> no conversions).
            self._s2_fs = dict(S2_TABLE)
            self._s2_fs[15] = 0.0
            # Default to whichever knob position matches cfg["fs_true"].
            s2_default, _, _ = snap_to_s2(self.cfg["fs_true"])
            if s2_default is None:
                s2_default = 14
            self.s2_combo = ttk.Combobox(
                b, values=[self._s2_labels[n] for n in self._s2_order],
                state="readonly", style="TCombobox",
            )
            self.s2_combo.set(self._s2_labels[s2_default])
            self.s2_combo.bind("<<ComboboxSelected>>", self._on_s2knob)
            self.s2_combo.pack(fill="x", pady=(2, 2))
            tk.Label(b, text="turn the knob; the detector re-measures fs from the tone",
                     bg=t["panel"], fg=t["text_dim"], font=t.f_small).pack(
                anchor="w", pady=(0, 10))

        # --- simulate-only: inject a no-signal (dead-rail) case (F-07-05) ---
        if self.cfg["simulate"]:
            self.nosig = tk.BooleanVar(value=False)
            ttk.Checkbutton(
                b, text="Simulate no signal (dead rail)",
                variable=self.nosig, command=self._on_nosignal,
            ).pack(anchor="w", pady=(2, 10))

        # --- buttons ---
        btns = tk.Frame(b, bg=t["panel"])
        btns.pack(fill="x", pady=(4, 2))
        self.pause_btn = ttk.Button(btns, text="⏸  Pause", style="Ghost.TButton",
                                    command=self._on_pause)
        self.pause_btn.pack(fill="x", pady=3)
        ttk.Button(btns, text="⟳  Reset", style="Accent.TButton",
                   command=self._on_reset).pack(fill="x", pady=3)

        ttk.Checkbutton(b, text="Show time-domain strip",
                        variable=self.show_time,
                        command=self._toggle_time).pack(anchor="w", pady=(12, 0))

        self.status_var = tk.StringVar(value="Starting…")
        tk.Frame(b, bg=t["border"], height=1).pack(fill="x", pady=(12, 8))
        tk.Label(b, textvariable=self.status_var, bg=t["panel"],
                 fg=t["text_dim"], font=t.f_small, wraplength=250,
                 justify="left").pack(anchor="w")

    def _build_plots(self, parent):
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from matplotlib.figure import Figure

        t = self.theme
        holder = tk.Frame(parent, bg=t["panel"])
        holder.grid(row=0, column=1, sticky="nsew")
        self.fig = Figure(figsize=(7.2, 6.2), dpi=100)
        t.style_figure(self.fig)
        gs = self.fig.add_gridspec(6, 1, hspace=1.1)
        self.ax_fft = self.fig.add_subplot(gs[0:4, 0])
        self.ax_time = self.fig.add_subplot(gs[4:6, 0])
        t.style_axes(self.ax_fft, title="FFT magnitude — peak bin sets fs",
                     xlabel="FFT bin", ylabel="Magnitude (dB)")
        t.style_axes(self.ax_time, title="Time domain",
                     xlabel="Sample", ylabel="Code")
        self.fig.subplots_adjust(left=0.11, right=0.98, top=0.95, bottom=0.09)
        self.canvas = FigureCanvasTkAgg(self.fig, master=holder)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def _build_metrics(self, parent):
        t = self.theme
        panel = tk.Frame(parent, bg=t["panel"])
        panel.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        wrap, b = t.section(panel, "Live Measurements")
        wrap.pack(fill="both", expand=True)
        self.m_det = t.metric(b, "Measured fs (from tone)", accent=t["accent"])
        self.m_s2 = t.metric(b, "S2 clock knob (inferred)", accent=t["good"])
        self.m_err = t.metric(b, "Error vs S2 truth")
        self.m_bin = t.metric(b, "Peak bin")
        self.m_true_bin = t.metric(b, "True (fractional) bin")
        self.m_res = t.metric(b, "Bin resolution")
        self.m_std = t.metric(b, "Input std (codes)")

    def _build_explanation(self, parent):
        t = self.theme
        strip = tk.Frame(parent, bg=t["panel_alt"])
        strip.pack(fill="x", side="bottom")
        self.explain_var = tk.StringVar(
            value="Measured fs = f_in · N / peak_bin, where f_in is the tone the "
                  "M2K generates. The measured rate reveals the S2 clock knob — "
                  "which pyadi can't read, so it always reports 40 MHz.")
        tk.Label(strip, textvariable=self.explain_var, bg=t["panel_alt"],
                 fg=t["text"], font=t.f_body, anchor="w", justify="left",
                 wraplength=1220).pack(fill="x", padx=14, pady=8)

    # -- control callbacks -------------------------------------------------
    def _on_freq(self, _v):
        self.f_in = int(float(self.freq_scale.get()))
        self.freq_val.set(f"{self.f_in/1e3:.1f} kHz")
        self.command_q.put(("f_in", self.f_in))

    def _on_nbuf(self, _e):
        self.nbuf = int(self.nbuf_combo.get())
        self.command_q.put(("nbuf", self.nbuf))

    def _on_interp(self):
        pass  # read live in _render

    def _on_nosignal(self):
        self.command_q.put(("nosignal", self.nosig.get()))

    def _on_s2knob(self, _e):
        s2 = self._s2_by_label[self.s2_combo.get()]
        self.command_q.put(("fs_true", self._s2_fs[s2]))

    def _on_pause(self):
        self.worker.paused = not self.worker.paused
        self.command_q.put(("pause", self.worker.paused))
        self.pause_btn.configure(text="▶  Resume" if self.worker.paused
                                 else "⏸  Pause")

    def _on_reset(self):
        self.freq_scale.set(self.cfg["f_in"])
        self._on_freq(None)
        self.nbuf_combo.set(str(self.cfg["nbuf"]))
        self._on_nbuf(None)
        self.interp.set(True)
        if self.cfg["simulate"]:
            s2_default, _, _ = snap_to_s2(self.cfg["fs_true"])
            if s2_default is None:
                s2_default = 14
            self.s2_combo.set(self._s2_labels[s2_default])
            self._on_s2knob(None)
            self.nosig.set(False)
            self._on_nosignal()
        if self.worker.paused:
            self._on_pause()

    def _toggle_time(self):
        self.ax_time.set_visible(self.show_time.get())
        self.canvas.draw_idle()

    # -- refresh loop ------------------------------------------------------
    def _poll(self):
        try:
            self.latest = self.result_q.get_nowait()
        except queue.Empty:
            pass
        if self.latest is not None:
            # A render exception must not kill the after() chain (that would
            # freeze the window silently); report it in the status bar instead.
            try:
                self._render(self.latest)
            except Exception as exc:
                self.status_var.set(f"Render error: {exc}")
        self.root.after(90, self._poll)

    def _render(self, frame):
        t = self.theme
        self.status_var.set(frame.get("status", ""))
        data = frame.get("data")
        mag = frame.get("mag_spec")
        std = frame.get("std", 0.0)
        fs_true = frame.get("fs_true")
        filt = frame.get("filt")
        osr = frame.get("osr")
        n = len(data) if data is not None else self.nbuf

        # OSR only decimates when a sinc filter is engaged; the S2 divider sits
        # before the filter, so modulator_rate = data_rate * OSR. (Read-only, used
        # to un-decimate the measured rate before snapping to the S2 table.)
        osr_eff = osr if (filt and filt != "none" and osr) else 1

        # ---- time-domain strip ----
        self.ax_time.clear()
        t.style_axes(self.ax_time, title="Time domain", xlabel="Sample",
                     ylabel="Code")
        if data is not None and len(data):
            # show only the first ~4 cycles so the sine is legible
            if fs_true and self.f_in:
                cyc = int(max(1, 4 * fs_true / self.f_in))
                show = data[: min(len(data), cyc)]
            else:
                show = data[: min(len(data), 400)]
            self.ax_time.plot(show, color=t["trace_rx"], linewidth=0.9)
        self.ax_time.set_visible(self.show_time.get())

        # ---- FFT ----
        ax = self.ax_fft
        ax.clear()
        t.style_axes(ax, title="FFT magnitude — peak bin sets fs",
                     xlabel="FFT bin", ylabel="Magnitude (dB)")

        metrics = dict(err="--", det="--", s2="--", pbin="--",
                       tbin="--", res="--")
        if mag is not None and len(mag):
            bins = np.arange(len(mag))
            ax.plot(bins, mag, color=t["trace_rx"], linewidth=1.2,
                    label="FFT magnitude")
            ax.set_xlim(0, len(mag))
            fs, bin_f, err = detect_fs(mag, n, self.f_in,
                                       interpolate=self.interp.get())

            if err:
                # F-07-05: no crash, clear message.
                ax.text(0.5, 0.5, err, transform=ax.transAxes,
                        color=t["bad"], ha="center", va="center",
                        fontsize=12, fontweight="bold")
                self.explain_var.set(
                    "No usable tone in the spectrum — the original script would "
                    "divide by bin 0 and raise OverflowError here (F-07-05). This "
                    "build reports it instead.")
            else:
                int_bin = int(round(bin_f))
                # marker at the integer argmax bin (what the raw method uses)
                ax.axvline(int_bin, color=t["marker_alias"], linewidth=1.4,
                           linestyle="--", label=f"argmax bin {int_bin}")
                # marker at the interpolated / true peak
                ax.axvline(bin_f, color=t["marker_gen"], linewidth=2.0,
                           label=f"peak bin {bin_f:.2f}")
                # zoom x to the peak neighborhood for clarity
                lo = max(0, int_bin - 25)
                hi = min(len(mag), int_bin + 25)
                ax.set_xlim(lo, hi)

                # `fs` is the DATA rate the tone was sampled at. The S2 divider
                # sits before the sinc filter, so the modulator (CNV) rate the
                # knob actually sets is fs * OSR -- snap THAT to the S2 table.
                fs_mod = fs * osr_eff
                metrics["det"] = (f"{fs/1e6:.4f} MHz"
                                  if osr_eff == 1
                                  else f"{fs/1e6:.4f} MHz  (×{osr_eff} → "
                                       f"{fs_mod/1e6:.3f})")
                metrics["pbin"] = f"{int_bin}"
                metrics["tbin"] = f"{bin_f:.3f}"

                # ---- snap the modulator rate to the S2 knob table ----
                s2, fs_tab, ok = snap_to_s2(fs_mod)
                # Coarse integer-bin detection has a worst-case error of
                # 0.5/true_bin; at high fs / small N the tone occupies so few
                # bins that this exceeds the 2% snap tolerance -- the reading is
                # then too coarse to CONFIRM the knob, which is exactly #07's
                # lesson (turn interpolation on / raise N). Distinguish that
                # "too coarse" case from a genuinely unexpected rate.
                if s2 is not None and ok:
                    metrics["s2"] = f"S2={s2}  →  {fs_tab/1e6:.2f} MHz"
                    # Error is measured-vs-S2-truth: the knob's exact rate is the
                    # ground truth, so this % is purely the peak-detection error
                    # and collapses when interpolation is on.
                    err_pct = 100.0 * (fs_mod - fs_tab) / fs_tab
                    metrics["err"] = f"{err_pct:+.3f} %"
                elif s2 is not None:
                    # nearest candidate + whether coarse resolution is the cause
                    true_bin_cand = self.f_in * n / (fs_tab / osr_eff)
                    coarse = (not self.interp.get()) or true_bin_cand < 25
                    if coarse:
                        metrics["s2"] = f"S2={s2}? (too coarse to confirm)"
                        metrics["err"] = "enable interpolation / raise N"
                    else:
                        metrics["s2"] = (f"~S2={s2}? ({fs_mod/1e6:.3f} MHz, "
                                         f"off-table)")
                        metrics["err"] = "off-table"

                # Ideal (fractional) bin at the true rate + bin resolution.
                fs_ref = fs_tab if (s2 is not None) else fs
                true_bin = self.f_in * n / (fs_ref / osr_eff)
                metrics["tbin"] = f"{bin_f:.3f}  (ideal {true_bin:.3f})"
                metrics["res"] = f"{fs/n/1e3:.2f} kHz/bin"
                self._update_explanation(bin_f, true_bin, fs, fs_mod,
                                         s2, fs_tab, ok, osr_eff,
                                         fs_true, self.interp.get())

            leg = ax.legend(loc="upper right", fontsize=8, framealpha=0.85)
            if leg:
                leg.get_frame().set_facecolor(t["panel"])
                for txt in leg.get_texts():
                    txt.set_color(t["text"])

        # ---- metrics panel ----
        self.m_det.set(metrics["det"])
        self.m_s2.set(metrics["s2"])
        self.m_err.set(metrics["err"])
        self.m_bin.set(metrics["pbin"])
        self.m_true_bin.set(metrics["tbin"])
        self.m_res.set(metrics["res"])
        self.m_std.set(f"{std:.0f}")

        self.canvas.draw_idle()

    def _update_explanation(self, bin_f, true_bin, fs, fs_mod, s2, fs_tab, ok,
                            osr_eff, fs_driver, interp):
        # Two stories to tell: (1) interpolation accuracy, (2) what the measured
        # rate reveals about the S2 knob vs the driver's hardcoded 40 MHz.
        if not interp:
            self.explain_var.set(
                f"Interpolation OFF: argmax returns only an integer bin "
                f"({int(round(bin_f))}), but the true peak is at {true_bin:.3f}. "
                f"That rounding skews the measured rate — turn interpolation on "
                f"to fix it, then read the S2 knob below.")
            return

        dec = (f" (data rate {fs/1e6:.4f} MHz ×{osr_eff} OSR)"
               if osr_eff != 1 else "")
        if s2 is not None and ok:
            drift = 100.0 * (fs_driver - fs_tab) / fs_tab
            if abs(drift) < 0.5:
                msg = (f"Measured fs ≈ {fs_mod/1e6:.3f} MHz{dec} → S2 knob is at "
                       f"position {s2}. That matches the driver's {fs_driver/1e6:.0f} "
                       f"MHz, so the board is at its default clock (S2=14).")
            else:
                msg = (f"Measured fs ≈ {fs_mod/1e6:.3f} MHz{dec} → S2 knob is at "
                       f"position {s2} (80 MHz÷{16-s2}). The driver still reports "
                       f"{fs_driver/1e6:.0f} MHz because it CAN'T read S2 — the "
                       f"measurement is the truth, the 40 MHz is a stale assumption. "
                       f"This is exactly why #07 measures fs from a known tone.")
        elif s2 is not None and true_bin < 25:
            # Interp is on but N is too small: the tone occupies <25 bins, so even
            # sub-bin interpolation can't pin it within 2%. This is #07's lesson.
            msg = (f"Measured fs ≈ {fs_mod/1e6:.3f} MHz{dec}. The tone lands in only "
                   f"~{true_bin:.1f} bins at this N, so the peak is too coarse to "
                   f"confirm S2={s2} within 2% — raise the FFT buffer size (more "
                   f"bins per tone) to sharpen it. This is the resolution limit #07 "
                   f"is about.")
        else:
            msg = (f"Measured fs ≈ {fs_mod/1e6:.3f} MHz{dec} doesn't match any S2 "
                   f"knob value (80 MHz / N). Check the tone is below Nyquist and "
                   f"the wiring is differential — otherwise it may be aliasing.")
        self.explain_var.set(msg)

    # -- shutdown ----------------------------------------------------------
    def _on_close(self):
        self.worker.stop()
        self.root.after(300, self.root.destroy)


# ===========================================================================
#  Entry point
# ===========================================================================
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="AD4080 Sample-Rate Detector — a polished ADI dashboard that "
                    "shows how FFT peak-bin quantization limits fs detection.")
    p.add_argument("-u", "--ad4080_uri", default="serial:COM4,230400",
                   help="LibIIO context URI of the EVAL-AD4080ARDZ (sink)")
    p.add_argument("-m", "--m2k_uri", default="",
                   help="LibIIO context URI of the ADALM2000 source "
                        "(default: empty -> first M2K found via m2kOpen()).")
    p.add_argument("-f", "--test_freq", type=float, default=100000.0,
                   help="Tone (Hz) the M2K generates into the AD4080 (F-07-03). "
                        "Must be < M2K Nyquist 3.75 MHz and < ADC Nyquist.")
    p.add_argument("-n", "--nbuf", type=int, default=8192,
                   choices=FsDetectorApp.NBUF_OPTIONS,
                   help="FFT buffer size / rx_buffer_size.")
    p.add_argument("--fs_true", type=float, default=40e6,
                   help="Simulated true sample rate (Hz) for --simulate.")
    p.add_argument("--rx_timeout_ms", type=int, default=5000,
                   help="LibIIO context timeout (ms) for live captures. A stalled "
                        "CNV clock (e.g. S2=15 'no clock' on hardware) makes rx() "
                        "block forever; this bounds it so the GUI recovers instead "
                        "of freezing. 0 = backend default (blocks indefinitely).")
    p.add_argument("--simulate", action="store_true",
                   help="Run with a synthetic device — no hardware needed.")
    p.add_argument("--theme", choices=["dark", "light"], default="dark",
                   help="Dashboard theme.")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    cfg = {
        "simulate": args.simulate,
        "uri": args.ad4080_uri,
        "m2k_uri": args.m2k_uri,
        "f_in": args.test_freq,
        "nbuf": args.nbuf,
        "fs_true": args.fs_true,
        "rx_timeout_ms": args.rx_timeout_ms,
        "theme": args.theme,
        "sim_nosignal": False,
    }
    root = tk.Tk()
    FsDetectorApp(root, cfg)
    root.mainloop()


if __name__ == "__main__":
    main()
