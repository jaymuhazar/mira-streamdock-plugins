"""Probe the lamp: send status queries (0xAA) and optional test commands, print replies.

  python probe.py q   status queries only (read-only)
  python probe.py c   power on, brightness, and four colour-command formats (0x0D is the one that works)
  python probe.py x   white 2700K / 6500K and scene restore
"""
import asyncio
import os
import sys
from bleak import BleakClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from govee_lamp import DEFAULT_ADDRESS, find_lamps  # noqa: E402

ADDR = DEFAULT_ADDRESS  # GOVEE_LAMP_ADDRESS env var, or found by scanning below
CTRL = "00010203-0405-0607-0809-0a0b0c0d2b11"
NOTIFY = "00010203-0405-0607-0809-0a0b0c0d2b10"


def pkt(*body):
    b = bytearray(body) + bytearray(19 - len(body))
    x = 0
    for v in b:
        x ^= v
    return bytes(b + bytes([x]))


async def main(cmds):
    global ADDR
    if not ADDR:
        found = await find_lamps()
        if not found:
            print("No Govee H6052 found nearby.")
            return
        ADDR = found[0][0]
        print("Using", ADDR, found[0][1])
    async with BleakClient(ADDR, timeout=20, winrt={"use_cached_services": False}) as c:
        def on(_, data):
            print("  <-", data.hex(" "))
        await c.start_notify(NOTIFY, on)
        try:
            await c.start_notify(CTRL, on)
        except Exception as e:
            print("ctrl notify failed", e)
        for label, body, wait in cmds:
            p = pkt(*body)
            print(f"-> {label}: {p.hex(' ')}")
            await c.write_gatt_char(CTRL, p, response=False)
            await asyncio.sleep(wait)


QUERIES = [
    ("query power", [0xAA, 0x01], 0.6),
    ("query brightness", [0xAA, 0x04], 0.6),
    ("query mode/colour", [0xAA, 0x05, 0x01], 0.6),
    ("query mode", [0xAA, 0x05], 0.6),
    ("query fw", [0xAA, 0x06], 0.6),
    ("query hw", [0xAA, 0x07, 0x03], 0.6),
]

Q = ("  query mode", [0xAA, 0x05, 0x01], 0.8)
COLOUR_TESTS = [
    ("power on", [0x33, 0x01, 0x01], 1.5),
    ("query power", [0xAA, 0x01], 0.8),
    ("brightness 0x64", [0x33, 0x04, 0x64], 1.5),
    ("query brightness", [0xAA, 0x04], 0.8),
    ("A: 33 05 02 red", [0x33, 0x05, 0x02, 255, 0, 0], 2.5), Q,
    ("B: 33 05 0d green", [0x33, 0x05, 0x0D, 0, 255, 0], 2.5), Q,
    ("C: 33 05 15 01 blue all-segments", [0x33, 0x05, 0x15, 0x01, 0, 0, 255, 0, 0, 0, 0, 0, 0xFF, 0x7F], 2.5), Q,
    ("D: 33 05 0b purple", [0x33, 0x05, 0x0B, 160, 0, 255], 2.5), Q,
]

EXTRA_TESTS = [
    ("white 2700K", [0x33, 0x05, 0x0D, 0xFF, 0xFF, 0xFF, 0x0A, 0x8C, 0xFF, 0xA7, 0x57], 2.5), Q,
    ("white 6500K", [0x33, 0x05, 0x0D, 0xFF, 0xFF, 0xFF, 0x19, 0x64, 0xFF, 0xF9, 0xFD], 2.5), Q,
    ("scene 0x0bb9 (previous)", [0x33, 0x05, 0x04, 0xB9, 0x0B], 2.5), Q,
]

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "q"
    asyncio.run(main({"q": QUERIES, "c": COLOUR_TESTS, "x": EXTRA_TESTS}[which]))
