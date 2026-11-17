"""StreamDock plugin backend: one key that cycles Boom 3D's output device and shows
which device Boom is using right now.

How it knows the device: Boom3D.exe keeps an ACTIVE audio session on the real output it
forwards to, so we look for that session across Windows' playback devices.
How it switches: it presses Boom's own "switch device" hotkey (Ctrl+Shift+D by default).
"""
import asyncio
import ctypes
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import comtypes
import psutil
import websockets
from comtypes import CLSCTX_ALL
from pycaw.constants import DEVICE_STATE, EDataFlow
from pycaw.pycaw import AudioUtilities, IAudioSessionControl2, IAudioSessionManager2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import keyart  # noqa: E402

logging.basicConfig(filename=os.path.join(HERE, "log.txt"), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("boomaudio")

CONFIG = {
    "hotkey": ["ctrl", "shift", "d"],
    "poll_seconds": 2,
    # "match" is part of the Windows playback-device name. "icon" is a built-in glyph
    # (headset | monitor | speakers) or any name with your own images/glyph-<icon>.png.
    # Override the whole list in config.json.
    "devices": [
        {"match": "Headset", "icon": "headset", "label": "HEADSET"},
        {"match": "Headphones", "icon": "headset", "label": "HEADPHONES"},
        {"match": "Speakers", "icon": "speakers", "label": "SPEAKERS"},
    ],
}
_cfg = os.path.join(HERE, "config.json")
if os.path.exists(_cfg):
    CONFIG.update(json.load(open(_cfg, encoding="utf-8")))

VK = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B}
COM = ThreadPoolExecutor(max_workers=1, initializer=comtypes.CoInitialize)


def detect_device() -> str | None:
    """Friendly name of the device Boom3D is currently playing to, or None."""
    enum = AudioUtilities.GetDeviceEnumerator()
    coll = enum.EnumAudioEndpoints(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value)
    for i in range(coll.GetCount()):
        dev = coll.Item(i)
        name = AudioUtilities.CreateDevice(dev).FriendlyName
        if name.startswith("Boom (Boom Audio)"):
            continue  # Boom's own virtual input device
        mgr = ctypes.cast(dev.Activate(IAudioSessionManager2._iid_, CLSCTX_ALL, None),
                          ctypes.POINTER(IAudioSessionManager2))
        sessions = mgr.GetSessionEnumerator()
        for j in range(sessions.GetCount()):
            ctl = sessions.GetSession(j).QueryInterface(IAudioSessionControl2)
            if ctl.GetState() != 1:
                continue
            try:
                if psutil.Process(ctl.GetProcessId()).name().lower() == "boom3d.exe":
                    return name
            except Exception:
                pass
    return None


def press_hotkey() -> None:
    keys = [VK.get(k.lower(), None) or ord(k.upper()) for k in CONFIG["hotkey"]]
    u = ctypes.windll.user32
    for k in keys:
        u.keybd_event(k, 0, 0, 0)
    for k in reversed(keys):
        u.keybd_event(k, 0, 2, 0)


def device_info(name: str | None) -> dict:
    if name:
        for d in CONFIG["devices"]:
            if d["match"].lower() in name.lower():
                return d
    return {"icon": "speakers", "label": (name or "")[:10].upper()}


class Plugin:
    def __init__(self, ws):
        self.ws = ws
        self.contexts: set[str] = set()
        self.device: str | None = None
        self.checked = False
        self.busy = False

    async def run_com(self, fn, *a):
        return await asyncio.get_running_loop().run_in_executor(COM, fn, *a)

    async def send(self, obj):
        await self.ws.send(json.dumps(obj))

    def image(self, state=None):
        info = device_info(self.device)
        if state is None:
            state = "busy" if not self.checked else ("on" if self.device else "offline")
        return keyart.render(info["icon"], state, info.get("label", ""))

    async def paint(self, image=None, only=None):
        image = image or self.image()
        for ctx in ([only] if only else list(self.contexts)):
            await self.send({"event": "setImage", "context": ctx, "payload": {"image": image, "target": 0}})

    async def refresh(self, force=False):
        try:
            dev = await self.run_com(detect_device)
        except Exception as e:
            log.warning("detect failed: %r", e)
            dev = None
        changed = dev != self.device or not self.checked
        self.device, self.checked = dev, True
        if changed or force:
            await self.paint()

    async def press(self):
        if self.busy:
            return
        self.busy = True
        try:
            before = self.device
            await self.paint(self.image("busy"))
            await self.run_com(press_hotkey)
            for _ in range(20):                      # wait up to ~5 s for Boom to move
                await asyncio.sleep(0.25)
                dev = await self.run_com(detect_device)
                if dev and dev != before:
                    break
            self.device, self.checked = dev, True
            log.info("switched %s -> %s", before, dev)
            if not dev:
                for ctx in self.contexts:
                    await self.send({"event": "showAlert", "context": ctx})
            await self.paint()
        except Exception:
            log.exception("press failed")
        finally:
            self.busy = False

    async def background(self):
        while True:
            if self.contexts and not self.busy:
                await self.refresh()
            await asyncio.sleep(CONFIG["poll_seconds"])

    async def handle(self, msg):
        ev, ctx = msg.get("event"), msg.get("context")
        if ev == "willAppear":
            self.contexts.add(ctx)
            await self.paint(only=ctx)
            if self.checked:
                return
            asyncio.create_task(self.refresh(force=True))
        elif ev == "willDisappear":
            self.contexts.discard(ctx)
        elif ev == "keyDown":
            asyncio.create_task(self.press())


def parse_args(argv):
    a, it = {}, iter(argv)
    for k in it:
        if k.startswith("-"):
            a[k.lstrip("-")] = next(it, "")
    return a


async def main():
    args = parse_args(sys.argv[1:])
    uri = f"ws://127.0.0.1:{args['port']}"
    log.info("starting, connecting to %s", uri)
    async with websockets.connect(uri, max_size=None) as ws:
        await ws.send(json.dumps({"event": args["registerEvent"], "uuid": args["pluginUUID"]}))
        plugin = Plugin(ws)
        bg = asyncio.create_task(plugin.background())
        try:
            async for raw in ws:
                try:
                    await plugin.handle(json.loads(raw))
                except Exception:
                    log.exception("event failed")
        finally:
            bg.cancel()
    log.info("StreamDock closed the connection, exiting")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        log.exception("fatal")
