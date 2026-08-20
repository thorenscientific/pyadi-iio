# ADALM-MMSC (AD4080) Examples — Environment Setup Guide

Reproducible setup for running the DSP examples in this folder on **Windows**
(git bash). Verified 2026-08-05 with **Python 3.11.9** — full stack incl. libm2k,
both boards live.

- **Repo (fork):** `C:\phase0\pyadi-iio`, branch `adalm-mmsc-phase0-cleanup`
- **Virtual env:** `C:\phase0\.venv` (**Python 3.11**)
- **Examples:** `C:\phase0\pyadi-iio\examples\adalm-mmsc`

> **Why Python 3.11 (not 3.13)?** `libm2k` is not on PyPI; the only wheel we have
> is `libm2k-0.9.0-cp311-...`, which loads **only on Python 3.11**. The whole venv
> is therefore pinned to 3.11. (An earlier 3.13 venv ran `simulated_data.py` fine
> but could not load libm2k — so 11 of the 15 examples were blocked.)

---

## 0. Prerequisites

- **Python 3.11** installed (required — see note above).
- Git bash.
- Hardware (examples 03, 05–15): **ADALM2000 (M2K)** + **ADALM-MMSC (AD4080ARDZ)**.
- The local libm2k wheel:
  `C:\Users\JGEALON\OneDrive - Analog Devices, Inc\My Documents\ADALM-MMSC (AD4080)\pyadi-iio\libm2k-0.9.0-cp311-cp311-win_amd64.whl`

---

## 1. Verify your Python

```bash
py -0p
```

Lists installed interpreters and paths. You want a **3.11** entry.

> **Known machine quirk (this laptop):** every base `python.exe` had been renamed
> to `python311.exe` / `python313.exe`. That breaks the `py` launcher
> (*"system cannot find the file specified"*) **and** `python -m venv`
> (ensurepip exit 1/103). If you hit that, restore a real `python.exe` next to it:
>
> ```bash
> cp "/c/Users/JGEALON/AppData/Local/Programs/Python/Python311/python311.exe" \
>    "/c/Users/JGEALON/AppData/Local/Programs/Python/Python311/python.exe"
> ```
>
> This only adds a copy; it does not touch the renamed exe.

---

## 2. Create the virtual environment (Python 3.11)

```bash
"/c/Users/JGEALON/AppData/Local/Programs/Python/Python311/python.exe" -m venv /c/phase0/.venv
```

> `venv` may print exit code 1 even on success on this machine — cosmetic.
> Verify with step 3; if `Scripts/python.exe` and `Scripts/activate` exist, it's good.

---

## 3. Confirm the venv

Each git-bash `!` command runs in a fresh shell, so `activate` does **not** persist.

**Option A — activate per session (interactive):**
```bash
source /c/phase0/.venv/Scripts/activate
python --version && python -m pip --version
```

**Option B — call by full path (recommended for scripted/one-off):**
```bash
/c/phase0/.venv/Scripts/python.exe --version
/c/phase0/.venv/Scripts/python.exe -m pip --version
```

Expected: `Python 3.11.9`, pip pointing at `C:\phase0\.venv\...`.

---

## 4. Install requirements

```bash
/c/phase0/.venv/Scripts/python.exe -m pip install --upgrade pip
/c/phase0/.venv/Scripts/python.exe -m pip install -r \
  "/c/phase0/pyadi-iio/examples/adalm-mmsc/requirements.txt"
```

> If you install unpinned, on 3.11 you'll get numpy 2.4.6 / scipy 1.17.1
> (numpy ≥2.5 needs Python ≥3.12 and will fail to resolve — expected).

---

## 5. libm2k (required for M2K examples — NOT on PyPI)

Install the **local cp311 wheel** (matches the 3.11 venv exactly):

```bash
/c/phase0/.venv/Scripts/python.exe -m pip install \
  "/c/Users/JGEALON/OneDrive - Analog Devices, Inc/My Documents/ADALM-MMSC (AD4080)/pyadi-iio/libm2k-0.9.0-cp311-cp311-win_amd64.whl"
```

Confirm the whole stack (including libm2k) loads:

```bash
/c/phase0/.venv/Scripts/python.exe -c "import numpy, scipy, matplotlib, genalyzer, paramiko, iio, adi, serial, libm2k; print('libm2k', libm2k.getVersion()); print('ALL IMPORTS OK')"
```

Expect `libm2k v0.9.0-gce0cf95` + `ALL IMPORTS OK`.

> The wheel is cp311-only. On Python 3.13 it will NOT install (its `.pyd` is a
> 3.11 binary). There is no cp313 build available locally.

---

## 6. Hardware connection map (IMPORTANT)

The two boards are addressed **differently** — this is the key gotcha:

| Device | Role | How to address it | Verified |
|---|---|---|---|
| **ADALM2000 (M2K)** | signal **source** | `libm2k.m2kOpen()` (auto-detect; URI varies) | ✅ |
| **ADALM-MMSC (AD4080)** | ADC **sink** | `adi.ad4080("serial:COM4,115200")` | ✅ 40 Msps |

> **⚠️ The M2K USB address is NOT stable.** It re-enumerates across reconnect/reboot —
> e.g. it has been seen as both `usb:1.7.5` and `usb:1.18.5` on this machine. **Always
> scan first** (next command) and pass whatever `scan_contexts()` reports that day; don't
> hard-code a URI. `libm2k.m2kOpen()` with no argument auto-detects and is the safest
> default when only one M2K is attached.

> **The AD4080 is NOT an IIO USB/network context — it is a SERIAL (COM) device.**
> `iio.scan_contexts()` only ever shows the M2K; that is expected and does not mean
> the AD4080 is missing. Do not rely on the IIO scan to find the ADC.

Check the M2K (IIO view — shows M2K only, by design):

```bash
/c/phase0/.venv/Scripts/python.exe -c "import iio; [print(u,'|',d) for u,d in iio.scan_contexts().items()]"
```

Find the AD4080's COM port — look for an ADI vendor `USB Serial Device`
(VID `0456`), **not** the "M2k Serial Console":

```bash
/c/phase0/.venv/Scripts/python.exe -c "import serial.tools.list_ports as lp; [print(p.device,'|',p.description,'|',p.hwid) for p in lp.comports()]"
```

On this machine: **COM4** = AD4080 (VID:PID `0456:8102`); COM10 = M2k Serial Console.
Port numbers vary per machine/USB slot — the reference pilot script defaults to
`COM12`, which is stale here. Confirm the ADC opens:

```bash
/c/phase0/.venv/Scripts/python.exe -c "import adi; d=adi.ad4080('serial:COM4,115200'); print('AD4080 fs=', d.sampling_frequency, 'filter=', d.filter_type)"
```

Expect `fs= 40000000  filter= none`.

> A harmless warning may print: *"program compiled against libxml 20 using
> libxml 2"* — non-fatal, ignore.

---

## 7. Run an example

**No hardware** (proves the DSP stack) — run plain (no `!`) to see the plot window:

```bash
cd /c/phase0/pyadi-iio/examples/adalm-mmsc
/c/phase0/.venv/Scripts/python.exe simulated_data.py
```

**Hardware examples** — most take a COM-port / URI argument. Check each script's
argparse defaults and override the port to **COM4**, e.g. the pilot program:

```bash
/c/phase0/.venv/Scripts/python.exe adalm-mmsc-pilot-tst-prog.py --ad4080_com_port COM4
```

> **Plots vs. the `!` harness:** running via `! ...` here shows the printed metrics
> but the Tk plot window will NOT appear (it can't attach to the desktop). Run the
> command **plain in your own git-bash terminal** to see plots; `pl.show()` blocks
> until you close the window. Backend is `tkagg` and works. To capture plots to PNG
> without a window, use the headless wrapper in
> `platform-readiness/run-notes/tools/capture_plots.py`.

---

## Quick reference — runnability (current: 3.11 venv + both boards live)

| Example | Needs | Status |
|---|---|---|
| 04 `simulated_data.py` | core only | ✅ runs (validated PASS) |
| 02 `workshop.py` | library (imported) | n/a — not run directly |
| 03 `sine_gen.py` | libm2k + M2K | ✅ runnable |
| 05–15 (all) | libm2k + `serial:COM4` (+ M2K) | ✅ runnable (not yet run) |

See `requirements.txt` for exact pinned versions.

---

## Environment state (verified 2026-08-05)

- venv: `C:\phase0\.venv`, Python 3.11.9
- numpy 2.4.6 · scipy 1.17.1 · matplotlib 3.11.1 · genalyzer 0.1.4 ·
  pyadi-iio 0.0.21 · pylibiio 0.25 · pyserial 3.5 · paramiko 5.0.0 ·
  **libm2k 0.9.0** (`v0.9.0-gce0cf95`)
- M2K: `usb:1.7.5` at the time of this verification (libm2k) — **address is not stable,
  since seen as `usb:1.18.5`; scan first, don't hard-code** · AD4080: `serial:COM4,115200`,
  40 Msps
