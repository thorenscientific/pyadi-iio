"""
Utility functions for the FTC 2024 workshop on converter infrastructure.
While an interesting read, these are mostly the things we deemed out-of-scope
for the workshop content. They generate signals to spec and do pretty plots,
both of which would otherwise pollute the example scripts with hundreds of
lines of code.
"""

import matplotlib.pyplot as pl

pl.ion()
import signal
import sys

import genalyzer as gn
import matplotlib
import numpy as np
from matplotlib.patches import Rectangle as MPRect


# Override matplotlib and allow us to stop the program with Ctrl-C
def goodbye(*args):
    print("Got Ctrl-C, terminating")

    pl.close("all")

    if "m2k" in globals():
        globals()["m2k"].contextClose()

    if "ad4080" in globals():
        del globals()["ad4080"]

    sys.exit(0)


signal.signal(signal.SIGINT, goodbye)


def time_points_from_freq(freq, fs=1, density=False):
    """Generate time series from half-spectrum.

    Parameters
    ----------
    freq : [float]
        Half-spectrum of signal to be generated. DC offset in zeroth element.
    fs : float
        Sampling frequency. Used if `density == True` to scale the resulting
        waveform.
    density : bool
        If true, scales the resulting waveform by $N \sqrt{fs / N}$, where $N$ is
        the half-spectrum size.

    Returns
    -------
    res : np.array
        Resulting waveform with specified spectrum. Its length is twice the length
        of the `freq` parameter.
    """

    N = len(freq)

    # Random phases for each frequency component, expect for DC which gets 0 phase
    rnd_ph_pos = np.ones(N - 1, dtype=complex) * np.exp(
        1j * np.random.uniform(0.0, 2.0 * np.pi, N - 1)
    )
    rnd_ph_neg = np.flip(np.conjugate(rnd_ph_pos))
    rnd_ph_full = np.concatenate(([1], rnd_ph_pos, [1], rnd_ph_neg))

    r_spectrum_full = np.concatenate((freq, np.roll(np.flip(freq), 1)))
    r_spectrum_rnd_ph = r_spectrum_full * rnd_ph_full

    r_time_full = np.fft.ifft(r_spectrum_rnd_ph)  # This line does the "real work"

    # Sanity check: is the imaginary component close to nothing?
    rms_imag = np.std(np.imag(r_time_full))
    rms_real = np.std(np.real(r_time_full))
    if rms_imag > rms_real * 1e-6:
        print("RMS imaginary component should be close to zero, and it's a bit high...")

    if density:
        r_time_full *= N * np.sqrt(fs / N)  # Note that this N is "predivided" by 2

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
    """Do fixed tone fourier analysis using genalyzer and plot results.

    Parameters
    ----------
    waveform : np.array
        Received waveform.
    sampling_rate : int
        Sampling rate of received waveform.
    fundamental : float
        Fundamental frequency expected in the received waveform.
    ssb_fund : int
        Number of Fourier analysis single side bins for the fundamental and its
        harmonics. If this value is too low, spectral leakage around signal peaks
        will be labeled as noise.
    ssb_rest : int
        Number of Fourier analysis single side bins for other components: DC,
        WorstOther.
    navg : int
        Number of FFT windows to be averaged.
    nfft : int
        Length in samples of an FFT window. The total length of the waveform MUST
        be equal to `navg * nfft`.
    window : genalyzer.advanced.Window
        Windowing used for FFT.
    code_fmt : genalyzer.advanced.CodeFormat
        Code format of received samples.
    rfft_scale : genalyzer.advanced.RfftScale
        Real FFT scale for analysis.
    fund_ampl : float
        Amplitude of generated fundamental, used for computing THD.

    Returns
    -------
    None
    """
    if nfft is None:
        nfft = len(waveform) // navg
    assert len(waveform) == navg * nfft

    # Remove DC component
    waveform = waveform - np.average(waveform)

    # Compute FFT
    fft_cplx = gn.rfft(np.array(waveform), navg, nfft, window, code_fmt, rfft_scale)

    # Compute frequency axis
    freq_axis = gn.freq_axis(nfft, gn.FreqAxisType.REAL, sampling_rate)

    # Compute FFT in db
    fft_db = gn.db(fft_cplx)

    # Fourier analysis configuration
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

    # Fourier analysis results
    fft_results = gn.fft_analysis(key, fft_cplx, nfft)
    # compute THD
    thd = 20 * np.log10(fft_results["thd_rss"] / fund_ampl)

    print("\nFourier Analysis Results:\n")
    print("\nFrequency, Phase and Amplitude for Harmonics:\n")
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
    print("\nFrequency, Phase and Amplitude for Noise:\n")
    for k in ["wo:freq", "wo:mag_dbfs", "wo:phase"]:
        print("{:20s}{:20.6f}".format(k, fft_results[k]))
    print("\nSNR and THD \n")
    for k in ["snr", "fsnr"]:
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
    pl.show()

    return fft_results


def generate_noise_band(center, width, fs):
    """Generate a waveform whose spectral content is a band of white noise with specified center frequency and width.

    Parameters
    ----------
    center : int
        Center frequency in Hz
    width : int
        Width in Hz
    fs : int
        Sampling frequency of generated signal

    Returns
    -------
    res : np.array
        Resulting waveform with specified spectrum. Its length equals `fs`, representing a 1 second waveform.
    """

    noise_band_lo = int(max(center - width // 2, 1))
    noise_band_hi = int(min(center + width // 2, fs // 2))

    # FIXME: Generate a shorter waveform with the same spectral content!
    #        Currently generating one whole second, but, for example, noise
    #        around 10k would only need a circa 200us waveform
    spectrum = np.concatenate(
        (
            np.zeros(noise_band_lo),
            np.ones(noise_band_hi - noise_band_lo),
            np.zeros(fs // 2 - noise_band_hi),
        )
    )
    spectrum /= np.sqrt(noise_band_hi - noise_band_lo)  # Normalize to 1V RMS

    return time_points_from_freq(spectrum, fs=fs, density=True)


def plot_waveform_and_fft(name, waveform, fs, fft=None, freq_range=None, fignum=None):
    """Plot a waveform and its FFT.

    Parameters
    ----------
    name : str
        Description of the waveform. Subplot titles will contain this.
    waveform : np.array
        Waveform to plot.
    fs : int
        Sampling frequency of waveform.
    fft : np.array
        FFT to plot. If omitted, it will be computed from the waveform using genalyzer.

    Returns
    -------
    res : np.array
        Resulting waveform with specified spectrum. Its length equals `fs`, representing a 1 second waveform.
    """

    times = np.arange(len(waveform)) / fs  # Time of each sample

    # Plot generated waveform
    fig = pl.figure(fignum, figsize=(10, 10))
    fig.canvas.mpl_connect("close_event", goodbye)

    pl.clf()
    pl.subplot(2, 1, 1)
    pl.title(f"{name} waveform")
    pl.plot(times, waveform)
    pl.ylim(-5, 5)
    pl.grid(True)

    if fft is None:
        # Compute and plot generated signal FFT
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
    """ Plot sinc1 response folded once around nyquist """

    # Compute frequency axis
    freq_axis = gn.freq_axis(int(fs_in / 2 / decimation), gn.FreqAxisType.REAL, fs_in)

    # Compute expected sinc response
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
    # pl.savefig(f'frames/{i:02}.png')


def interactive_sinc_folding_ui(fs_in, npts, nfft, iiothread):
    plot_freq_range = fs_in / 2 * 5
    times = np.arange(npts) / fs_in
    freq_axis = gn.freq_axis(nfft, gn.FreqAxisType.REAL, fs_in)

    # axw - AXes for received Waveform
    # axf - AXes for received Fft
    # axs - AXes for Slider widget
    fig, (axw, axf, axs) = pl.subplots(
        3, 1, gridspec_kw={"height_ratios": [4, 5, 1]}, figsize=(8, 8)
    )

    pl.pause(0.01)

    axs.set_title("Transmit noise center frequency")
    slider = matplotlib.widgets.Slider(
        axs,
        "",
        0,
        plot_freq_range,
        valinit=iiothread.selected_center_frequency,
        valstep=1000,
        initcolor="none",
    )

    def slider_changed(value):
        iiothread.selected_center_frequency = value

    slider.on_changed(slider_changed)

    fig.tight_layout()
    fig.canvas.draw()

    while pl.get_fignums():  # get_fignums will be falsey if window has been closed
        axw.clear()
        axw.set_title("Received waveform")
        axw.set_xlim(0, npts / fs_in)
        axw.set_ylim(-5, 5)
        axw.grid(True)
        axw.text(
            0,
            4.5,
            f"Status: {iiothread.status_msg}",
            horizontalalignment="left",
            verticalalignment="center",
        )
        axw.plot(times, iiothread.data_in)

        axf.clear()
        axf.set_title("Received FFT")
        axf.set_xlim(0, plot_freq_range)
        axf.set_ylim(-100, 10)
        axf.grid(True)

        for fold in range(5):
            freqs = freq_axis + fold * (fs_in // 2 + 1)
            sinc1 = np.sinc(freqs / fs_in)
            sinc1 = gn.db(np.complex128(sinc1)) - 10  # Convert to dB and adjust

            axf.plot(
                freqs,
                sinc1,
                "r--" if fold > 0 else "r",
                alpha=0.75 ** fold,
                label=f"Theoretical sinc1 response",
            )
            axf.plot(
                freqs,
                iiothread.fft_db[:: (-1) ** fold],
                "b--" if fold > 0 else "b",
                alpha=0.75 ** fold,
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

        # x tick at nyquist
        axf.axvline(fs_in // 2, linestyle="--", color="k")

        if iiothread.received_center_frequency is not None:
            fc = iiothread.received_center_frequency

            # Draw arrow at generated frequency
            axf.annotate(
                "Generated",
                xy=(fc, 0),
                xytext=(fc, 10),
                arrowprops=dict(facecolor="black", shrink=0.05),
                horizontalalignment="center",
            )

            if fc > fs_in // 2:
                # Compute fa = aliased frequency
                fold = fc // (fs_in // 2)
                if fold % 2 == 0:
                    fa = fc - (fs_in // 2) * fold
                else:
                    fa = (fs_in // 2) * (fold + 1) - fc

                # Draw arrow at aliased frequency
                axf.annotate(
                    "Aliased",
                    xy=(fa, 0),
                    xytext=(fa, 10),
                    arrowprops=dict(facecolor="black", shrink=0.05),
                    horizontalalignment="center",
                )

        fig.canvas.draw_idle()
        pl.pause(0.01)
