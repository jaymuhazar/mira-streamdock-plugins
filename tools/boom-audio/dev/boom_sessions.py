"""Show which playback device each program (esp. Boom3D) has an audio stream on.
  python boom_sessions.py          list once
  python boom_sessions.py press N  press Boom's Ctrl+Shift+D N times, listing after each
"""
import ctypes
import sys
import time

import comtypes
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioSessionManager2, IAudioSessionControl2
from pycaw.constants import EDataFlow, DEVICE_STATE

import psutil  # pulled in by pycaw


def boom_devices():
    comtypes.CoInitialize()
    enum = AudioUtilities.GetDeviceEnumerator()
    coll = enum.EnumAudioEndpoints(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value)
    out = []
    for i in range(coll.GetCount()):
        dev = coll.Item(i)
        name = AudioUtilities.CreateDevice(dev).FriendlyName
        mgr = dev.Activate(IAudioSessionManager2._iid_, CLSCTX_ALL, None)
        mgr = ctypes.cast(mgr, ctypes.POINTER(IAudioSessionManager2))
        sessions = mgr.GetSessionEnumerator()
        procs = []
        for j in range(sessions.GetCount()):
            ctl = sessions.GetSession(j).QueryInterface(IAudioSessionControl2)
            pid = ctl.GetProcessId()
            state = ctl.GetState()  # 0 inactive, 1 active, 2 expired
            try:
                pname = psutil.Process(pid).name() if pid else "System"
            except Exception:
                pname = f"pid {pid}"
            procs.append(f"{pname}[{('inactive', 'ACTIVE', 'expired')[state]}]")
        out.append((name, procs))
    return out


def show(label):
    print(f"--- {label}")
    for name, procs in boom_devices():
        mark = "  <== Boom" if any(p.lower().startswith("boom3d") and "ACTIVE" in p for p in procs) else ""
        print(f"  {name}: {', '.join(procs) or '-'}{mark}")


if __name__ == "__main__":
    show("now")
    if len(sys.argv) > 2 and sys.argv[1] == "press":
        import ctypes.wintypes
        user32 = ctypes.windll.user32
        VK_CONTROL, VK_SHIFT, VK_D, UP = 0x11, 0x10, 0x44, 2
        for n in range(int(sys.argv[2])):
            for vk in (VK_CONTROL, VK_SHIFT, VK_D):
                user32.keybd_event(vk, 0, 0, 0)
            for vk in (VK_D, VK_SHIFT, VK_CONTROL):
                user32.keybd_event(vk, 0, UP, 0)
            time.sleep(2.5)
            show(f"after press {n + 1}")
