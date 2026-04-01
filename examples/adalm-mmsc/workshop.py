"""
Utility functions for the FTC 2024 workshop on converter infrastructure.
While an interesting read, these are mostly the things we deemed out-of-scope
for the workshop content. They generate signals to spec and do pretty plots,
both of which would otherwise pollute the example scripts with hundreds of
lines of code.
"""

import matplotlib.pyplot as pl  # type: ignore

pl.ion()
import signal
import sys

import genalyzer as gn  # type: ignore
import matplotlib  # type: ignore
import numpy as np  # type: ignore
from matplotlib.patches import Rectangle as MPRect  # type: ignore

# Override matplotlib and allow us to stop the program with Ctrl-C
_goodbye_called = False


def goodbye(*args):
    global _goodbye_called
    if _goodbye_called:
        return
    _goodbye_called = True
    print("Got Ctrl-C, terminating")
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    try:
        import matplotlib._pylab_helpers as pylab_helpers  # type: ignore

        for manager in list(pylab_helpers.Gcf.get_all_fig_managers()):
            try:
                if hasattr(manager, "canvas"):
                    manager.canvas.mpl_disconnect("close_event")  # type: ignore
            except Exception:
                pass
        pl.ioff()
        pl.close("all")
    except Exception:
        pass
    sys.exit(0)


signal.signal(signal.SIGINT, goodbye)


def time_points_from_freq(freq, fs=1, density=False):
    """Generate a real-valued time-domain waveform from a half-spectrum.
    If density=True, scales output by N*sqrt(fs/N) for noise density use.
    """
    N = len(freq)
    rnd_ph_pos = np.ones(N - 1, dtype=complex) * np.exp(
        1j * np.random.uniform(0.0, 2.0 * np.pi, N - 1)
    )
    rnd_ph_neg = np.flip(np.conjugate(rnd_ph_pos))
    rnd_ph_full = np.concatenate(([1], rnd_ph_pos, [1], rnd_ph_neg))

    r_spectrum_full = np.concatenate((freq, np.roll(np.flip(freq), 1)))
    r_spectrum_rnd_ph = r_spectrum_full * rnd_ph_full
    r_time_full = np.fft.ifft(r_spectrum_rnd_ph)

    rms_imag = np.std(np.imag(r_time_full))
    rms_real = np.std(np.real(r_time_full))
    if rms_imag > rms_real * 1e-6:
        print("RMS imaginary component should be close to zero, and it's a bit high...")

    if density:
        r_time_full *= N * np.sqrt(fs / N)
    return np.real(r_time_full)


def fourier_analysis(
    waveform,
    sampling_rate,
    fundamental,
    ssb_fund=4,
    ssb_rest=4,
    navg=2,
    nfft=None,
    window=gn.Window.BLACKMAN_HARRIS,
    code_fmt=gn.CodeFormat.TWOS_COMPLEMENT,
    rfft_scale=gn.RfftScale.NATIVE,
    fund_ampl=10 ** (-3 / 20),
):
    """Run genalyzer Fourier analysis on a waveform and plot the FFT."""
    if nfft is None:
        nfft = len(waveform) // navg
    assert len(waveform) == navg * nfft

    waveform = waveform - np.average(waveform)
    fft_cplx = gn.rfft(np.array(waveform), navg, nfft, window, code_fmt, rfft_scale)
    freq_axis = gn.freq_axis(nfft, gn.FreqAxisType.REAL, sampling_rate)
    fft_db = gn.db(fft_cplx)

    key = "fa"
    gn.mgr_remove(key)
    gn.fa_create(key)
    gn.fa_analysis_band(key, "fdata*0.0", "fdata*1.0")
    gn.fa_fixed_tone(key, "A", gn.FaCompTag.SIGNAL, fundamental, ssb_fund)
    gn.fa_hd(key, 4)
    gn.fa_ssb(key, gn.FaSsb.DEFAULT, ssb_rest)
    gn.fa_ssb(key, gn.FaSsb.DC, -1)
    gn.fa_ssb(key, gn.FaSsb.SIGNAL, -1)
    gn.fa_ssb(key, gn.FaSsb.WO, -1)
    gn.fa_fsample(key, sampling_rate)
    print(gn.fa_preview(key, False))

    fft_results = gn.fft_analysis(key, fft_cplx, nfft)
    thd = 20 * np.log10(fft_results["thd_rss"] / fund_ampl)

    print("\nFourier Analysis Results:")
    for k in [
        "A:freq",
        "A:mag_dbfs",
        "A:phase",
        "2A:freq",
        "2A:mag_dbfs",
        "2A:phase",
        "3A:freq",
        "3A:mag_dbfs",
        "3A:phase",
        "4A:freq",
        "4A:mag_dbfs",
        "4A:phase",
    ]:
        print("{:20s}{:20.6f}".format(k, fft_results[k]))
    for k in ["wo:freq", "wo:mag_dbfs", "wo:phase", "snr", "fsnr"]:
        print("{:20s}{:20.6f}".format(k, fft_results[k]))
    print("{:20s}{:20.6f}".format("thd", thd))

    # Plot FFT
    fig = pl.figure(1)
    fig.canvas.mpl_connect("close_event", goodbye)
    fftax = pl.subplot2grid((1, 1), (0, 0), rowspan=2, colspan=2)
    pl.title("FFT")
    pl.plot(freq_axis, fft_db)
    pl.grid(True)
    pl.xlim(freq_axis[0], min(freq_axis[-1], 10 * fft_results["A:freq"]))  # DC - A10
    pl.ylim(-160.0, 20.0)
    annots = gn.fa_annotations(fft_results)

    for x, y, label in annots["labels"]:
        pl.annotate(label, xy=(x, y), ha="center", va="bottom")
    for box in annots["tone_boxes"]:
        fftax.add_patch(
            MPRect(
                (box[0], box[1]),
                box[2],
                box[3],
                ec="pink",
                fc="pink",
                fill=True,
                hatch="x",
            )
        )

    fig = pl.figure(2)
    fig.canvas.mpl_connect("close_event", goodbye)
    pl.plot(np.array(waveform))

    pl.tight_layout()
    pl.show()
    return fft_results


def generate_noise_band(center, width, fs, amplitude=1.0, duration_s=0.25):
    """Generate a bandlimited white-noise waveform centered at `center` Hz, `width` Hz wide.

    The base waveform is normalized to 1 V RMS, then scaled by `amplitude`.
    `duration_s` controls waveform duration (defaults to 0.25 s, i.e. < 1 s).
    """
    n_samples = max(256, int(fs * duration_s))
    if n_samples % 2 != 0:
        n_samples += 1

    nyq = n_samples // 2
    df = fs / n_samples
    noise_band_lo_hz = max(center - width / 2.0, 1.0)
    noise_band_hi_hz = min(center + width / 2.0, fs / 2.0)
    lo_bin = int(max(np.floor(noise_band_lo_hz / df), 1))
    hi_bin = int(min(np.ceil(noise_band_hi_hz / df), nyq))
    if hi_bin <= lo_bin:
        hi_bin = min(lo_bin + 1, nyq)
        lo_bin = max(1, hi_bin - 1)

    spectrum = np.concatenate(
        (
            np.zeros(lo_bin),
            np.ones(hi_bin - lo_bin),
            np.zeros(nyq - hi_bin),
        )
    )
    spectrum /= np.sqrt(max(1, hi_bin - lo_bin))
    spectrum *= amplitude
    time_points = time_points_from_freq(spectrum, fs=fs, density=True)
    if np.any((time_points <= -3.0) | (time_points >= 3.0)):
        print(
            "WARNING: generated time_points exceed ±3.0 V "
            f"(min={np.min(time_points):.3f} V, max={np.max(time_points):.3f} V)."
        )
    return time_points


def plot_waveform_and_fft(name, waveform, fs, fft=None, freq_range=None, fignum=None):
    """Plot a waveform and its FFT. Computes FFT via genalyzer if not provided."""
    times = np.arange(len(waveform)) / fs

    fig = pl.figure(fignum, figsize=(10, 10))
    fig.canvas.mpl_connect("close_event", goodbye)

    pl.clf()
    pl.subplot(2, 1, 1)
    pl.title(f"{name} waveform")
    pl.plot(times, waveform)
    pl.ylim(-5, 5)
    pl.grid(True)

    if fft is None:
        nfft = len(waveform)
        fft_cplx = gn.rfft(
            waveform.copy(),
            1,
            len(waveform),
            gn.Window.BLACKMAN_HARRIS,
            gn.CodeFormat.TWOS_COMPLEMENT,
            gn.RfftScale.NATIVE,
        )
        fft = gn.db(fft_cplx)
    else:
        nfft = (len(fft) - 1) * 2

    freq_axis = gn.freq_axis(nfft, gn.FreqAxisType.REAL, fs)

    pl.subplot(2, 1, 2)
    pl.title(f"{name} FFT")
    pl.plot(freq_axis, fft)
    pl.xlim(0, freq_range if freq_range is not None else fs / 2)
    pl.ylim(-110, 10)
    pl.grid(True)

    pl.pause(0.1)


def plot_sinc1_folded(decimation, fs_in):
    """Plot sinc1 response folded once around Nyquist."""
    freq_axis = gn.freq_axis(int(fs_in / 2 / decimation), gn.FreqAxisType.REAL, fs_in)
    for fold in range(2):
        sinc1 = np.sinc(fold + (-1) ** fold * freq_axis / fs_in)
        pl.plot(freq_axis, gn.db(np.complex128(sinc1)) - 25, "k--")


def plot_waveform_fft_sinc1_unfolded(waveform, fft, fs, generated_freq, decimation):
    """ Plot received waveform, plot FFT and a number of unfolded copies (up to
    nyquist*5), plot sinc1 response over the whole frequency range, annotate
    generated and aliased frequency. """

    fig = pl.figure(2, figsize=(10, 10))
    fig.canvas.mpl_connect("close_event", goodbye)

    times = np.arange(len(waveform)) / fs

    ax = pl.subplot(2, 1, 1)
    ax.clear()
    pl.title(f"Recorded waveform, {decimation=}, noise band center={generated_freq}")
    pl.plot(times, waveform)
    pl.ylim(-5, 5)
    pl.grid(True)

    # Compute frequency axis
    freq_axis = gn.freq_axis((len(fft) - 1) * 2, gn.FreqAxisType.REAL, fs)

    # Plot FFT
    ax = pl.subplot(2, 1, 2)
    ax.clear()
    pl.title(f"'Unfolded' FFT, {decimation=}, noise band center={generated_freq}")
    pl.xlim(0, fs / 2 * 5)
    pl.ylim(-110, 10)
    pl.grid(True)

    # Plot unfolded signal spectrum and theoretical sinc
    for fold in range(5):
        freqs = freq_axis + fold * (fs // 2 + 1)
        sinc1 = gn.db(np.complex128(np.sinc(freqs / fs))) - 10

        pl.plot(
            freqs,
            sinc1,
            "r--" if fold > 0 else "r",
            alpha=0.75 ** fold,  # Color fade
            label=f"Theoretical sinc1 response",
        )
        pl.plot(
            freqs,
            fft[:: (-1) ** fold],
            "b--" if fold > 0 else "b",
            alpha=0.75 ** fold,  # Color fade
            label=f"Unfolded signal FFT" if fold > 0 else "Signal FFT",
        )

    # x tick at nyquist
    pl.axvline(fs // 2, linestyle="--", color="k")

    # arrow at generated tone
    pl.annotate(
        "Generated",
        xy=(generated_freq, -10),
        xytext=(generated_freq, 0),
        arrowprops=dict(facecolor="black", shrink=0.05),
        horizontalalignment="center",
    )

    if generated_freq > fs // 2:
        fold = generated_freq // (fs // 2)
        if fold % 2 == 0:
            aliased_freq = generated_freq - (fs // 2) * fold
        else:
            aliased_freq = (fs // 2) * (fold + 1) - generated_freq
        pl.annotate(
            "Aliased",
            xy=(aliased_freq, -10),
            xytext=(aliased_freq, 0),
            arrowprops=dict(facecolor="black", shrink=0.05),
            horizontalalignment="center",
        )

    pl.draw()
    pl.pause(0.1)


def interactive_sinc_folding_ui(fs_in, npts, nfft, iiothread):
    plot_freq_range = fs_in / 2 * 5
    times = np.arange(npts) / fs_in
    freq_axis = gn.freq_axis(nfft, gn.FreqAxisType.REAL, fs_in)

    fig, (axw, axf, axs) = pl.subplots(
        3, 1, gridspec_kw={"height_ratios": [3, 6, 1]}, figsize=(9, 8),
    )
    fig.patch.set_facecolor("#f7f7f7")  # type: ignore

    pl.pause(0.01)

    axs.set_title("Transmit noise center frequency (Hz)", fontsize=10, pad=6)
    slider = matplotlib.widgets.Slider(  # type: ignore
        axs,
        "",  # no external text label; use the value text instead
        0,
        plot_freq_range,
        valinit=iiothread.selected_center_frequency,
        valstep=1000,
        initcolor="none",
    )

    # Format the value shown inside the slider as kHz
    slider.valtext.set_text(f"{iiothread.selected_center_frequency/1e3:.1f} kHz")

    tick_vals = np.linspace(0, plot_freq_range, 6)
    axs.set_xticks(tick_vals)
    axs.set_xticklabels([f"{v/1e3:.0f}k" for v in tick_vals], fontsize=8)

    def slider_changed(value):
        iiothread.selected_center_frequency = value
        slider.valtext.set_text(f"{value/1e3:.1f} kHz")

    slider.on_changed(slider_changed)

    filter_options = getattr(
        iiothread, "filter_options", ["sinc1", "sinc5", "sinc5+pf1"]
    )
    sel_filt = getattr(iiothread, "selected_filter_type", filter_options[0])
    active_idx = filter_options.index(sel_filt) if sel_filt in filter_options else 0
    ax_filt = fig.add_axes([0.125, 0.07, 0.25, 0.12])
    ax_filt.set_title("Filter type", fontsize=9, pad=3)
    rb_filter = matplotlib.widgets.RadioButtons(ax_filt, filter_options, active=active_idx)  # type: ignore

    def filter_changed(label):
        iiothread.selected_filter_type = label

    rb_filter.on_clicked(filter_changed)

    ax_nw = fig.add_axes([0.47, 0.12, 0.18, 0.065])
    tb_nw = matplotlib.widgets.TextBox(  # type: ignore
        ax_nw,
        "Noise width (Hz)",
        initial=str(getattr(iiothread, "selected_noise_width", 10000)),
    )

    def noise_width_changed(text):
        try:
            width = max(1, int(float(text)))
            iiothread.selected_noise_width = width
            nsd_db = float(iiothread.selected_nsd_db)
            nsd_ref = float(iiothread._nsd_ref_v_per_hz)
            iiothread.selected_nsd = nsd_ref * (10 ** (nsd_db / 20.0))
        except ValueError:
            pass

    tb_nw.on_submit(noise_width_changed)

    ax_na = fig.add_axes([0.75, 0.12, 0.15, 0.065])
    tb_na = matplotlib.widgets.TextBox(  # type: ignore
        ax_na,
        "NSD (µV/Hz)",
        initial=f"{getattr(iiothread, 'selected_nsd_db', 0.0):.1f}",
    )

    def noise_amplitude_changed(text):
        try:
            nsd_db = float(text)
            m2k_peak = iiothread._m2k_peak_v
            width = max(1, int(iiothread.selected_noise_width))
            max_nsd = m2k_peak / (3.0 * width)
            nsd_ref = float(iiothread._nsd_ref_v_per_hz)
            nsd = nsd_ref * (10 ** (nsd_db / 20.0))
            if nsd > max_nsd:
                print(
                    f"WARNING: NSD level {nsd_db:.1f} dB ({nsd*1e6:.1f} µV/Hz) exceeds the safe level for this width. The waveform limiter will keep M2K within range."
                )
            iiothread.selected_nsd_db = nsd_db
            iiothread.selected_nsd = nsd
        except ValueError:
            pass

    tb_na.on_submit(noise_amplitude_changed)

    fig.subplots_adjust(top=0.95, bottom=0.23, hspace=0.35)
    fig.canvas.draw()

    while pl.get_fignums():  # get_fignums will be falsey if window has been closed
        axw.clear()
        axw.set_title("Received waveform", fontsize=11)
        axw.set_xlim(0, npts / fs_in)
        axw.set_ylim(-5, 5)
        axw.grid(True, alpha=0.3)
        axw.text(
            0,
            4.5,
            f"Status: {iiothread.status_msg}",
            horizontalalignment="left",
            verticalalignment="center",
        )
        axw.plot(times, iiothread.data_in, color="#1f77b4")

        axf.clear()
        axf.set_title("Received FFT", fontsize=11)
        axf.set_xlim(0, plot_freq_range)
        axf.set_ylim(-100, 10)
        axf.grid(True, alpha=0.3)

        for fold in range(5):
            freqs = freq_axis + fold * (fs_in // 2 + 1)
            sinc1 = np.sinc(freqs / fs_in)
            sinc1 = gn.db(np.complex128(sinc1)) - 10  # Convert to dB and adjust

            axf.plot(
                freqs,
                sinc1,
                "r--" if fold > 0 else "r",
                alpha=0.75 ** fold,
                label="Theoretical sinc1 response" if fold == 0 else None,
            )
            axf.plot(
                freqs,
                iiothread.fft_db[:: (-1) ** fold],
                "b--" if fold > 0 else "b",
                alpha=0.75 ** fold,
                label="Measured (folded)" if fold == 0 else None,
            )

            if fold == 0:
                axf.annotate(
                    "Nyq. zone 1", xy=(fs_in // 4, -100), horizontalalignment="center"
                )
            else:
                axf.annotate(
                    f'"Nyq. zone " {fold+1}',
                    xy=(fs_in * (2 * fold + 1) // 4, -100),
                    horizontalalignment="center",
                )

        axf.axvline(fs_in // 2, linestyle="--", color="k")

        if iiothread.received_center_frequency is not None:
            fc = iiothread.received_center_frequency
            axf.annotate(
                "Generated",
                xy=(fc, 0),
                xytext=(fc, 10),
                arrowprops=dict(facecolor="black", shrink=0.05),
                horizontalalignment="center",
            )
            if fc > fs_in // 2:
                fold = fc // (fs_in // 2)
                fa = (
                    fc - (fs_in // 2) * fold
                    if fold % 2 == 0
                    else (fs_in // 2) * (fold + 1) - fc
                )
                axf.annotate(
                    "Aliased",
                    xy=(fa, 0),
                    xytext=(fa, 10),
                    arrowprops=dict(facecolor="black", shrink=0.05),
                    horizontalalignment="center",
                )

        handles, labels = axf.get_legend_handles_labels()
        if handles:
            axf.legend(loc="upper right", fontsize=8, frameon=True)

        fig.canvas.draw_idle()
        pl.pause(0.01)
