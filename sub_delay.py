#!/usr/bin/env python3
"""
sub_delay.py - play your Mac's audio through a wired subwoofer and a Bluetooth
speaker at the same time, with an adjustable offset to line them up.

Audio path:
    Amazon Music -> BlackHole 2ch (set as the Mac's sound output)
    BlackHole 2ch -> this script -> subwoofer
                                 -> Bluetooth speaker

Usage:
    python sub_delay.py --list
    python sub_delay.py --sub "External Headphones" --speaker "X10 MAX"
    python sub_delay.py --sub "External Headphones" --speaker "X10 MAX" --offset -40

The offset is in milliseconds: positive delays the subwoofer, negative delays
the speaker.

While it runs, type "+" or "-" and Enter to nudge the offset by 10 ms, "+25"
or "-25" to nudge by any amount, or "=-40" to set it outright. Ctrl+C quits.
"""
import argparse
import sys
import threading
from contextlib import ExitStack

import numpy as np
import sounddevice as sd

BLOCK = 256           # frames per callback (~6 ms)
BASE_DELAY_MS = 20    # buffering on every output, keeps reads behind writes
MAX_SECONDS = 2.0     # longest delay the buffer can hold
MAX_OFFSET_MS = 1500


def find_device(name, kind):
    """Return the index of the first device whose name contains `name`."""
    for i, d in enumerate(sd.query_devices()):
        if name.lower() in d["name"].lower() and d[f"max_{kind}_channels"] > 0:
            return i
    sys.exit(f"No {kind} device matching '{name}'. Run with --list to see names.")


class Ring:
    """Audio from BlackHole, written once and read by each output at its own delay."""

    def __init__(self, samplerate, channels=2):
        self.sr = samplerate
        self.size = int(MAX_SECONDS * samplerate)
        self.buf = np.zeros((self.size, channels), dtype=np.float32)
        self.w = 0                 # total frames written
        self.lock = threading.Lock()

    def write(self, frames):
        n = len(frames)
        with self.lock:
            idx = (self.w + np.arange(n)) % self.size
            self.buf[idx] = frames
            self.w += n


class Tap:
    """One output's read position in the ring, held a set delay behind the writer.

    Each output device runs on its own clock, slightly faster or slower than
    BlackHole's, so the gap slowly drifts. When the smoothed gap wanders more
    than 2 ms from the target, the tap skips or repeats one sample per
    callback to pull it back. That's inaudible, and it keeps the delay steady
    for hours.
    """

    def __init__(self, ring):
        self.ring = ring
        self.r = 0                 # total frames read
        self.target = 0            # desired write-read gap, in frames
        self.avg_fill = None       # smoothed measurement of that gap
        self.tolerance = int(0.002 * ring.sr)

    def _set_delay_ms(self, ms):
        """Caller must hold ring.lock."""
        self.target = int(ms * self.ring.sr / 1000)
        self.r = self.ring.w - self.target     # jump straight to the new delay
        self.avg_fill = None

    def read(self, n):
        ring = self.ring
        with ring.lock:
            fill = ring.w - self.r
            if self.avg_fill is None:
                self.avg_fill = float(fill)
            else:
                self.avg_fill = 0.995 * self.avg_fill + 0.005 * fill
            if self.avg_fill > self.target + self.tolerance:
                self.r += 1                    # running behind: skip a sample
                self.avg_fill -= 1
            elif self.avg_fill < self.target - self.tolerance:
                self.r -= 1                    # running ahead: repeat a sample
                self.avg_fill += 1
            idx = (self.r + np.arange(n)) % ring.size
            out = ring.buf[idx]
            self.r += n
        return out


def set_offset(ring, sub, speaker, offset_ms):
    """Positive offset delays the subwoofer, negative delays the speaker."""
    offset_ms = max(-MAX_OFFSET_MS, min(MAX_OFFSET_MS, offset_ms))
    with ring.lock:
        sub._set_delay_ms(BASE_DELAY_MS + max(offset_ms, 0))
        speaker._set_delay_ms(BASE_DELAY_MS + max(-offset_ms, 0))
    return offset_ms


def describe(offset):
    if offset > 0:
        return f"+{offset:.0f} ms (subwoofer delayed)"
    if offset < 0:
        return f"{offset:.0f} ms (speaker delayed)"
    return "0 ms (neither delayed)"


def make_output_callback(tap, channels):
    def callback(outdata, frames, time, status):
        out = tap.read(frames)
        outdata[:] = out if channels == 2 else out.mean(axis=1, keepdims=True)
    return callback


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list", action="store_true", help="list audio devices and exit")
    p.add_argument("--in", dest="inp", default="BlackHole 2ch",
                   help="input device name (default: BlackHole 2ch)")
    p.add_argument("--sub", help="subwoofer output device name")
    p.add_argument("--speaker", help="Bluetooth speaker output device name")
    p.add_argument("--offset", type=float, default=0,
                   help="starting offset in ms (+ delays the subwoofer, - delays the speaker)")
    p.add_argument("--rate", type=int, help="sample rate (default: BlackHole's current rate)")
    args = p.parse_args()

    if args.list:
        print(sd.query_devices())
        return
    if not (args.sub and args.speaker):
        p.error("--sub and --speaker are both required (run with --list to see device names)")

    in_dev = find_device(args.inp, "input")
    sub_dev = find_device(args.sub, "output")
    spk_dev = find_device(args.speaker, "output")
    in_info = sd.query_devices(in_dev)
    rate = args.rate or int(in_info["default_samplerate"])

    ring = Ring(rate)
    sub, speaker = Tap(ring), Tap(ring)
    offset = set_offset(ring, sub, speaker, args.offset)

    def on_input(indata, frames, time, status):
        ring.write(indata[:, :2])

    common = dict(samplerate=rate, blocksize=BLOCK, dtype="float32", latency="low")
    with ExitStack() as stack:
        stack.enter_context(sd.InputStream(device=in_dev, channels=2,
                                           callback=on_input, **common))
        names = []
        for dev, tap in ((sub_dev, sub), (spk_dev, speaker)):
            info = sd.query_devices(dev)
            ch = min(2, info["max_output_channels"])
            stack.enter_context(sd.OutputStream(device=dev, channels=ch,
                                                callback=make_output_callback(tap, ch),
                                                **common))
            names.append(info["name"])

        print(f"{in_info['name']}  ->  sub: {names[0]}  +  speaker: {names[1]}  ({rate} Hz)")
        print(f"Offset: {describe(offset)}")
        print("Type + or - to nudge 10 ms, +25 / -25 for any amount, =N to set. Ctrl+C quits.")
        try:
            while True:
                cmd = input("> ").replace(" ", "")
                if not cmd:
                    continue
                if cmd in ("+", "-"):
                    cmd += "10"
                try:
                    if cmd.startswith("="):
                        new = float(cmd[1:])
                    elif cmd[0] in "+-":
                        new = offset + float(cmd)
                    else:
                        new = float(cmd)
                except ValueError:
                    print("Type + or -, a nudge like +25, or =N to set the offset.")
                    continue
                offset = set_offset(ring, sub, speaker, new)
                print(f"Offset: {describe(offset)}")
        except (KeyboardInterrupt, EOFError):
            print(f"\nStopped. Next time add: --offset {offset:.0f}")


if __name__ == "__main__":
    main()
