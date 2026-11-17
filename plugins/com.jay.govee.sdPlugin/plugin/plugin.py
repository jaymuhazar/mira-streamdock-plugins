"""StreamDock plugin backend for the Govee H6052 lamp.

Started by index.js with StreamDock's usual arguments:
  -port N -pluginUUID X -registerEvent Y -info {...}

Press the key -> toggle the lamp.  The key image shows live state (on with the lamp's
colour, off, busy, offline).  The Bluetooth link is opened only for a press or a status
check and closed again after a few idle seconds, so the phone / Govee Desktop can still
reach the lamp in between.
"""
import asyncio
import json
import logging
import os
import sys
import time

import websockets

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from govee_lamp import DEFAULT_ADDRESS, GoveeLamp, kelvin_to_rgb  # noqa: E402
import keyart  # noqa: E402

POLL_SECONDS = 20      # status refresh while a key is visible
IDLE_DISCONNECT = 6    # close the Bluetooth link after this many idle seconds
SCENE_GLOW = (255, 196, 120)

logging.basicConfig(filename=os.path.join(HERE, "log.txt"), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("govee")


def parse_args(argv):
    a = {}
    it = iter(argv)
    for k in it:
        if k.startswith("-"):
            a[k.lstrip("-")] = next(it, "")
    return a


class Plugin:
    def __init__(self, ws, address):
        self.ws = ws
        self.lamp = GoveeLamp(address, keep_alive=False)
        self.contexts: set[str] = set()
        self.state: dict | None = None
        self.checked = False   # has the first status check finished (ok or not)?
        self.last_use = 0.0
        self.busy = False
        self.lock = asyncio.Lock()

    async def send(self, obj):
        await self.ws.send(json.dumps(obj))

    def image_for(self, st):
        if not self.checked:
            return keyart.render("busy")
        if st is None:
            return keyart.render("offline")
        if not st.get("on"):
            return keyart.render("off")
        if st.get("mode") == "color":
            rgb = st["rgb"]
        elif st.get("mode") == "white":
            rgb = kelvin_to_rgb(st["kelvin"])
        else:
            rgb = SCENE_GLOW
        return keyart.render("on", tuple(rgb), st.get("brightness"))

    async def paint(self, image=None, only=None):
        image = image or self.image_for(self.state)
        for ctx in ([only] if only else list(self.contexts)):
            await self.send({"event": "setImage", "context": ctx, "payload": {"image": image, "target": 0}})

    async def refresh(self):
        async with self.lock:
            try:
                self.state = await asyncio.wait_for(self.lamp.state(), 30)
                self.last_use = time.monotonic()
            except Exception as e:
                log.warning("refresh failed: %r", e)
                self.state = None
            self.checked = True
        await self.paint()

    async def toggle(self):
        if self.busy:
            return
        self.busy = True
        try:
            await self.paint(keyart.render("busy"))
            async with self.lock:
                try:
                    cur = await asyncio.wait_for(self.lamp.state(), 30)
                    await self.lamp.power(not cur["on"])
                    await asyncio.sleep(0.4)
                    self.state = await asyncio.wait_for(self.lamp.state(), 10)
                    self.last_use = time.monotonic()
                    log.info("toggled -> %s", "on" if self.state["on"] else "off")
                except Exception as e:
                    log.warning("toggle failed: %r", e)
                    self.state = None
                    for ctx in self.contexts:
                        await self.send({"event": "showAlert", "context": ctx})
                self.checked = True
            await self.paint()
        finally:
            self.busy = False

    async def background(self):
        next_poll = 0.0
        while True:
            await asyncio.sleep(1)
            now = time.monotonic()
            if self.lamp.connected and now - self.last_use > IDLE_DISCONNECT and not self.lock.locked():
                try:
                    await self.lamp.disconnect()
                except Exception:
                    pass
            if self.contexts and now >= next_poll and not self.busy:
                next_poll = now + POLL_SECONDS
                asyncio.create_task(self.refresh())

    async def handle(self, msg):
        ev, ctx = msg.get("event"), msg.get("context")
        if ev == "willAppear":
            self.contexts.add(ctx)
            await self.paint(only=ctx)   # the background loop does the first status check right away
        elif ev == "willDisappear":
            self.contexts.discard(ctx)
        elif ev == "keyDown":
            asyncio.create_task(self.toggle())


async def main():
    args = parse_args(sys.argv[1:])
    address = DEFAULT_ADDRESS
    cfg = os.path.join(HERE, "config.json")
    if os.path.exists(cfg):
        address = json.load(open(cfg)).get("address", address)
    uri = f"ws://127.0.0.1:{args['port']}"
    log.info("starting, connecting to %s", uri)
    async with websockets.connect(uri, max_size=None) as ws:
        await ws.send(json.dumps({"event": args["registerEvent"], "uuid": args["pluginUUID"]}))
        plugin = Plugin(ws, address)
        bg = asyncio.create_task(plugin.background())
        try:
            async for raw in ws:
                try:
                    await plugin.handle(json.loads(raw))
                except Exception:
                    log.exception("event failed")
        finally:
            bg.cancel()
            try:
                await plugin.lamp.disconnect()
            except Exception:
                pass
    log.info("StreamDock closed the connection, exiting")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        log.exception("fatal")
