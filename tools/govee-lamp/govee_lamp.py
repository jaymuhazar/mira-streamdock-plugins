"""Bluetooth LE control for the Govee H6052 (Aura table lamp).

Protocol (verified on firmware 2.00.19):
  every packet is 20 bytes: payload padded with zeros, last byte = XOR of the first 19
  33 01 01/00                power on/off
  33 04 <0-100>              brightness
  33 05 0D r g b             RGB colour
  33 05 0D FF FF FF kH kL r g b   white at kelvin (kH kL big-endian), r g b = preview tint
  33 05 04 idLo idHi         scene
  AA 01 / AA 04 / AA 05 01   query power / brightness / mode (reply echoes the same header)
  AA 01                      also used as keep-alive
"""
from __future__ import annotations

import asyncio
import math
import os
import threading
from concurrent.futures import Future

from bleak import BleakClient, BleakScanner

# Your lamp's Bluetooth address, e.g. "AA:BB:CC:DD:EE:FF". Leave unset to scan for the
# first nearby "Govee_H6052_*" lamp. Can also be set with the GOVEE_LAMP_ADDRESS env var.
DEFAULT_ADDRESS = os.environ.get("GOVEE_LAMP_ADDRESS") or None
CTRL_UUID = "00010203-0405-0607-0809-0a0b0c0d2b11"
NOTIFY_UUID = "00010203-0405-0607-0809-0a0b0c0d2b10"


def packet(*body: int) -> bytes:
    b = bytearray(body) + bytearray(19 - len(body))
    x = 0
    for v in b:
        x ^= v
    return bytes(b + bytes([x]))


def kelvin_to_rgb(k: int) -> tuple[int, int, int]:
    t = k / 100
    if t <= 66:
        r = 255
        g = 99.4708025861 * math.log(t) - 161.1195681661
        b = 0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
    else:
        r = 329.698727446 * (t - 60) ** -0.1332047592
        g = 288.1221695283 * (t - 60) ** -0.0755148492
        b = 255
    clamp = lambda v: max(0, min(255, int(v)))
    return clamp(r), clamp(g), clamp(b)


async def find_lamps(timeout: float = 6.0) -> list[tuple[str, str]]:
    devs = await BleakScanner.discover(timeout=timeout)
    return [(d.address, d.name) for d in devs if (d.name or "").startswith("Govee_H6052")]


class GoveeLamp:
    """Async lamp connection with keep-alive and automatic reconnect."""

    def __init__(self, address: str | None = DEFAULT_ADDRESS, keep_alive: bool = True):
        self.address = address
        self.keep_alive = keep_alive  # False = don't hold/re-open the link in the background
        self.client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._replies: dict[bytes, asyncio.Future] = {}
        self._keepalive: asyncio.Task | None = None
        self.on_state_change = None  # callback(connected: bool)

    @property
    def connected(self) -> bool:
        return bool(self.client and self.client.is_connected)

    async def connect(self) -> None:
        if self.connected and self.client.services.get_characteristic(CTRL_UUID):
            return
        if not self.address:
            found = await find_lamps()
            if not found:
                raise ConnectionError("no Govee H6052 lamp found nearby (set its address in config.json)")
            self.address = found[0][0]
        # Windows sometimes hands back an empty/stale service list right after a previous
        # connection closed, so verify the Govee characteristic is there and retry if not.
        last_err = None
        for attempt in range(4):
            if self.client:
                try:
                    await self.client.disconnect()
                except Exception:
                    pass
            self.client = BleakClient(self.address, timeout=20, disconnected_callback=self._on_disconnect,
                                      winrt={"use_cached_services": False})
            try:
                await self.client.connect()
                if not self.client.services.get_characteristic(CTRL_UUID):
                    raise RuntimeError("lamp services not ready")
                await self.client.start_notify(NOTIFY_UUID, self._on_notify)
                break
            except Exception as e:
                last_err = e
                await asyncio.sleep(1.5)
        else:
            raise ConnectionError(f"could not connect to lamp: {last_err}")
        if self.keep_alive and (self._keepalive is None or self._keepalive.done()):
            self._keepalive = asyncio.create_task(self._keepalive_loop())
        if self.on_state_change:
            self.on_state_change(True)

    async def disconnect(self) -> None:
        if self._keepalive:
            self._keepalive.cancel()
        if self.client:
            await self.client.disconnect()

    def _on_disconnect(self, _client) -> None:
        if self.on_state_change:
            self.on_state_change(False)

    def _on_notify(self, _char, data: bytearray) -> None:
        fut = self._replies.pop(bytes(data[:2]), None)
        if fut and not fut.done():
            fut.set_result(bytes(data))

    async def _keepalive_loop(self) -> None:
        while True:
            await asyncio.sleep(2)
            try:
                await self._write(packet(0xAA, 0x01))  # reconnects under the lock if needed
            except Exception:
                await asyncio.sleep(3)

    async def _write(self, data: bytes, expect_reply: bool = False, timeout: float = 2.0) -> bytes | None:
        async with self._lock:
            if not self.connected:
                await self.connect()
            fut = None
            if expect_reply:
                fut = asyncio.get_running_loop().create_future()
                self._replies[data[:2]] = fut
            await self.client.write_gatt_char(CTRL_UUID, data, response=False)
            if fut:
                try:
                    return await asyncio.wait_for(fut, timeout)
                finally:
                    self._replies.pop(data[:2], None)
            return None

    # ---- commands -------------------------------------------------------
    async def power(self, on: bool) -> None:
        await self._write(packet(0x33, 0x01, 0x01 if on else 0x00))

    async def brightness(self, pct: int) -> None:
        await self._write(packet(0x33, 0x04, max(1, min(100, int(pct)))))

    async def color(self, r: int, g: int, b: int) -> None:
        await self._write(packet(0x33, 0x05, 0x0D, r & 255, g & 255, b & 255))

    async def white(self, kelvin: int) -> None:
        k = max(2000, min(9000, int(kelvin)))
        r, g, b = kelvin_to_rgb(k)
        await self._write(packet(0x33, 0x05, 0x0D, 0xFF, 0xFF, 0xFF, k >> 8, k & 255, r, g, b))

    async def scene(self, scene_id: int) -> None:
        await self._write(packet(0x33, 0x05, 0x04, scene_id & 255, (scene_id >> 8) & 255))

    async def state(self) -> dict:
        p = await self._write(packet(0xAA, 0x01), True)
        br = await self._write(packet(0xAA, 0x04), True)
        m = await self._write(packet(0xAA, 0x05, 0x01), True)
        st = {"on": bool(p and p[2]), "brightness": br[2] if br else None, "mode": None}
        if m:
            if m[2] == 0x0D and m[3:6] == b"\xff\xff\xff" and (m[6] or m[7]):
                st.update(mode="white", kelvin=(m[6] << 8) | m[7])
            elif m[2] == 0x0D:
                st.update(mode="color", rgb=(m[3], m[4], m[5]))
            elif m[2] == 0x04:
                st.update(mode="scene", scene=m[3] | (m[4] << 8))
            else:
                st.update(mode=f"0x{m[2]:02x}")
        return st


class LampThread:
    """Runs a GoveeLamp on a background asyncio loop so GUI/sync code can call it."""

    def __init__(self, address: str | None = DEFAULT_ADDRESS):
        self.loop = asyncio.new_event_loop()
        self.lamp = GoveeLamp(address)
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

    def submit(self, coro) -> Future:
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def call(self, name: str, *args) -> Future:
        return self.submit(getattr(self.lamp, name)(*args))

    def close(self) -> None:
        try:
            self.submit(self.lamp.disconnect()).result(5)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
