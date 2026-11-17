"""Scan for Govee lamps and list the services of the first one found
(or of GOVEE_LAMP_ADDRESS if set)."""
import asyncio
import os
from bleak import BleakClient, BleakScanner

ADDR = os.environ.get("GOVEE_LAMP_ADDRESS")


async def main():
    global ADDR
    print("Scanning 8s...")
    devs = await BleakScanner.discover(timeout=8, return_adv=True)
    for d, adv in devs.values():
        if (d.name or "").startswith(("Govee", "ihoment", "GBK")):
            print("FOUND", d.address, d.name, adv.rssi, adv.manufacturer_data, adv.service_uuids)
            ADDR = ADDR or d.address
    if not ADDR:
        print("No Govee device found.")
        return
    # use_cached_services=False: Windows can return a stale service list otherwise
    async with BleakClient(ADDR, timeout=20, winrt={"use_cached_services": False}) as c:
        print("connected", c.is_connected)
        for s in c.services:
            print("SERVICE", s.uuid, s.description)
            for ch in s.characteristics:
                print("   CHAR", ch.uuid, ch.properties, ch.description)


asyncio.run(main())
