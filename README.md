# sub_delay

Play your Mac's audio through a **wired subwoofer** and a **Bluetooth speaker** at the same time, with an adjustable delay so the two line up.

Bluetooth adds a noticeable delay, so a wired output and a Bluetooth output playing together usually sound out of sync. macOS has no built-in way to delay one output to match the other. This script fills that gap. It works with any two output devices, not just a subwoofer and a speaker.

**Requirements:** macOS, Python 3, [Homebrew](https://brew.sh) (to install BlackHole).

## Quick start

Once setup is done (see [Setup](#setup)):

1. **System Settings → Sound → Output → BlackHole 2ch**
2. From this folder, run:
   ```bash
   .venv/bin/python sub_delay.py --sub "External Headphones" --speaker "Your Speaker Name"
   ```
   `External Headphones` is the Mac's headphone jack. Use `--list` to see your exact device names. Any part of a name works.
3. Play music and keep the Terminal window open.
4. Line the outputs up by ear (see [Tuning the offset](#tuning-the-offset)). When you quit, the script prints the offset to reuse next time with `--offset`.
5. When you're done, press **Ctrl+C** and switch the sound output back to your usual speakers.

> While the output is set to BlackHole, nothing plays unless the script is running.

## Tuning the offset

The offset is how much one output is held back, in milliseconds:

- **Positive** delays the **subwoofer** (`--sub`).
- **Negative** delays the **speaker** (`--speaker`).

While the script runs, type a command and press Enter:

| Type | What it does |
|---|---|
| `+` / `-` | Nudge the offset by 10 ms |
| `+25` / `-25` | Nudge it by any amount |
| `=N` | Set it outright, e.g. `=-40` |
| Ctrl+C | Quit and print the final offset |

To tune, play a track with a punchy kick drum. The outputs are in sync when each kick lands as one solid hit instead of two.

## How it works

```
Any app ──► BlackHole 2ch (Mac's sound output)
                 │
            sub_delay.py  ── 2-second ring buffer
                 ├─► delay 20 ms + max(offset, 0)  ──► subwoofer (--sub)
                 └─► delay 20 ms + max(-offset, 0) ──► speaker (--speaker)
```

- **BlackHole** is a free, open-source virtual audio device. macOS doesn't let one program capture another app's audio directly. Instead, your music app plays into BlackHole, and the script reads from it like a microphone.
- **Ring buffer and taps.** Incoming audio is written once into a 2-second buffer. Each output has its own read position ("tap") held a set distance behind the writer, and that distance is its delay. Every output gets a 20 ms base buffer so it never reads audio that hasn't arrived yet. The offset adds extra delay to one side, up to ±1500 ms.
- **Clock drift.** BlackHole and each output device run on their own clocks, at very slightly different speeds. Left alone, the delays would creep apart by hundreds of milliseconds per hour. Each tap watches its smoothed delay. When the delay drifts more than 2 ms from the target, the tap skips or repeats a single sample to pull it back, which you can't hear. A simulation with clock errors of ±150 ppm held both delays within a few ms over an hour.
- **Why not a Multi-Output Device?** macOS's built-in Multi-Output Device can play to several outputs at once, but it has no delay setting. In testing, the wired path sometimes ended up *later* than the Bluetooth speaker, so delaying only one side wasn't enough. Driving both outputs from the script means either side can be delayed.

## Setup

1. **Install BlackHole**
   ```bash
   brew install blackhole-2ch
   ```
   This asks for your Mac password. If BlackHole doesn't appear in Audio MIDI Setup afterwards, restart the audio system with the command below, or restart the Mac:
   ```bash
   sudo killall coreaudiod
   ```
2. **Match the sample rate.** Open Audio MIDI Setup (Applications → Utilities) and press ⌘1 for the Audio Devices window. Check the Format of your subwoofer and speaker, then set **BlackHole 2ch** to the same rate, commonly 44,100 or 48,000 Hz.
3. **Create a Python environment** in this folder:
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install sounddevice numpy
   ```
4. **Allow microphone access.** On the first run, macOS asks whether Terminal (or your editor, if you run it there) can use the microphone, because reading from BlackHole counts as audio input. Allow it. This setting lives in System Settings → Privacy & Security → Microphone.

## Options

| Option | Meaning |
|---|---|
| `--list` | List audio devices and exit |
| `--sub NAME` | Subwoofer (or first) output device |
| `--speaker NAME` | Speaker (or second) output device |
| `--offset MS` | Starting offset (default 0) |
| `--in NAME` | Input device (default `BlackHole 2ch`) |
| `--rate HZ` | Sample rate (default: BlackHole's current rate) |

## Troubleshooting

| Symptom | Fix |
|---|---|
| BlackHole isn't in Audio MIDI Setup | Make sure you're in the Audio Devices window (⌘1), not MIDI Studio. Check that `ls /Library/Audio/Plug-Ins/HAL` lists `BlackHole2ch.driver`, then run `sudo killall coreaudiod`. |
| No sound at all | Check that the script is running and showing its `>` prompt, and that the Mac's volume isn't muted. |
| Script runs but nothing comes out | Check microphone permission for Terminal or your editor (Privacy & Security → Microphone). |
| `PaMacCore (AUHAL) ... err='-10863'` | Sample-rate mismatch. Set BlackHole to the same rate as your outputs, or pass `--rate`, e.g. `--rate 44100`. The script's first line shows the rate in use. |
| `No output device matching ...` | Run with `--list` and use part of the exact name shown. |
| `can't open file ... sub_delay.py` | Run the command from this folder, or give the full path to `sub_delay.py`. |
| Sync drifts after the speaker reconnects | Bluetooth latency can change between connections. Re-nudge with `+` / `-`. |

## Known limitations

- The Terminal window must stay open while you listen.
- The offset is set by ear, and Bluetooth latency can shift slightly each time a speaker reconnects.
- Audio plays a little behind the screen, so this setup suits music better than video.

---

## Future work: automatic delay detector

**Goal:** replace tuning by ear with a one-command calibration (`--calibrate`, or typing `c` while running). It would measure how late each output actually arrives at the listening spot and set the offset automatically, accurate to about ±2 ms.

Why ±2 ms: sound travels about 34 cm per millisecond, so 1 ms equals roughly 1 ft of speaker placement. At 100 Hz one cycle lasts 10 ms, so a few ms of error noticeably weakens the bass where the subwoofer and speaker overlap.

### Approach: active measurement with a test sweep

1. **Pick a microphone at the listening position.** An iPhone used as a Continuity microphone shows up as an input device and can sit where you actually listen. The Mac's built-in microphone works too, but it measures from the computer's position.
2. **Mute the music** while measuring, so the taps output silence.
3. **Record once, play twice.** Start one microphone recording. Inject a test sweep into the subwoofer tap, wait about 1 s, then inject the same sweep into the speaker tap. Both play from known positions in the buffer, so the script knows exactly when each was sent.
4. **Find each arrival time** by cross-correlating the recording against the sweep. An exponential sine sweep deconvolved with its inverse filter (the Farina method) gives a clean impulse response and separates out distortion. Take the first strong peak as the direct sound and ignore later room reflections. Use sub-sample peak interpolation for precision.
5. **Compute the offset.** `offset = (speaker arrival − speaker send) − (sub arrival − sub send)`. A positive result means the speaker is later, so the subwoofer gets delayed, which matches the script's sign convention. The microphone's own latency is the same for both measurements in one recording, so it cancels out. Measure with the offset at 0, or subtract the current offset.
6. **Repeat 3–5 times and use the median.** Reject the run if the results are spread by more than about 2 ms.
7. **Verify.** Apply the offset, measure again, and confirm the remaining difference is under about 1 ms.

### Test signal design

- **Measure both outputs in the band where they overlap**, roughly 60–150 Hz. That's where alignment matters, and it's the only band a subwoofer reproduces.
- **Expect broad peaks.** A low-frequency sweep produces a wide correlation peak, several ms across, and phone or laptop microphones lose sensitivity in deep bass. Compensate with a longer sweep (2–3 s), comfortable volume, interpolation and averaging.
- **A subwoofer's own low-pass filter adds group delay** that varies with frequency, so a wired subwoofer can sound later than expected. Measuring in the overlap band builds this into the result automatically.

### Stretch goal: continuous tracking while music plays

Only the speaker produces sound above roughly 200 Hz. The script could correlate the microphone's high band against BlackHole's high band in the background, track the speaker's latency continuously, and re-adjust the offset if it shifts after a Bluetooth reconnect. A wired subwoofer's latency is stable, so measuring it once at calibration is enough.

### Implementation sketch

- New functions: `make_sweep(f0, f1, seconds, rate)`, `inject(tap, signal)` to mix the signal into a tap's output at a known frame, `record(mic, seconds)`, and `arrival_time(recording, sweep)` using FFT cross-correlation with `numpy.fft` (no new dependencies).
- New option `--mic NAME`, defaulting to the Mac's built-in microphone.
- New option `--calibrate`, which runs steps 2–7 at startup and prints the measured offset. Add the matching `c` command while running.
- Tests: extend the drift simulation with a fake room. Each output gets a known latency, group delay, echo and noise level, and the detector must recover the offset within ±1 ms.

### Risks

- Continuity microphone dropouts or varying latency between sessions. A single recording covering both sweeps protects against this.
- Room echoes and noise. Pick the first strong peak, average several sweeps, and reject inconsistent runs.
- Weak low-frequency pickup by the microphone. If the overlap band is too noisy, fall back to measuring the speaker with a full-range sweep and correcting for the subwoofer's group delay.
