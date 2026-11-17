"""Take control of ASUS Aura lighting briefly, list devices, flash a colour, then hand back.
Result on this PC (Aura SDK 3.08 + current Armoury Crate): 0 devices, so no sync is possible this way."""
import time
import win32com.client

sdk = win32com.client.Dispatch("aura.sdk.1")
sdk.SwitchMode()
try:
    devs = sdk.Enumerate(0)
    print("devices:", devs.Count)
    for i in range(devs.Count):
        d = devs.Item(i)
        print(f"[{i}] name={d.Name} type={hex(d.Type)} leds={d.Lights.Count}")
    # Aura colours are 0x00BBGGRR
    for name, col in (("blue", 0xFF4000), ("orange", 0x006AFF)):
        for i in range(devs.Count):
            d = devs.Item(i)
            for j in range(d.Lights.Count):
                d.Lights.Item(j).Color = col
            d.Apply()
        print("set", name)
        time.sleep(2)
finally:
    sdk.ReleaseControl(0)
    print("released back to Armoury Crate")
