"""Command-line control for the Govee H6052 lamp.

  python lamp.py status
  python lamp.py on | off | toggle
  python lamp.py brightness 60
  python lamp.py color ff8800        (or: color 255 136 0)
  python lamp.py white 3000          (kelvin, 2000-9000)
  python lamp.py scene 3001
  python lamp.py scan
"""
import asyncio
import sys

from govee_lamp import DEFAULT_ADDRESS, GoveeLamp, find_lamps


async def run(args: list[str]) -> None:
    if not args:
        print(__doc__)
        return
    cmd, rest = args[0].lower(), args[1:]
    if cmd == "scan":
        for addr, name in await find_lamps():
            print(addr, name)
        return
    lamp = GoveeLamp(DEFAULT_ADDRESS)
    await lamp.connect()
    try:
        if cmd == "on":
            await lamp.power(True)
        elif cmd == "off":
            await lamp.power(False)
        elif cmd == "toggle":
            on = not (await lamp.state())["on"]
            await lamp.power(on)
            print("on" if on else "off")
        elif cmd in ("brightness", "b"):
            await lamp.brightness(int(rest[0]))
        elif cmd in ("color", "colour", "c"):
            if len(rest) == 3:
                r, g, b = map(int, rest)
            else:
                h = rest[0].lstrip("#")
                r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            await lamp.power(True)
            await lamp.color(r, g, b)
        elif cmd in ("white", "w"):
            await lamp.power(True)
            await lamp.white(int(rest[0]))
        elif cmd == "scene":
            await lamp.power(True)
            await lamp.scene(int(rest[0], 0))
        elif cmd == "status":
            print(await lamp.state())
        else:
            print(__doc__)
            return
        await asyncio.sleep(0.3)  # let the write leave before disconnecting
    finally:
        await lamp.disconnect()


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1:]))
