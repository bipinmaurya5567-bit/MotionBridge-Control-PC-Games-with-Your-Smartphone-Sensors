"""
sensor_server.py — Stage 1  (run ONLY for testing, NOT alongside game.py)
==========================================================================
WebSocket server: receives JSON sensor data from phone-sensor.html
and prints it live to the console.

!! WARNING !!  Both sensor_server.py and game.py bind to port 8765.
               Never run both at the same time — you will get OSError 10048.
               Use sensor_server.py to verify Stage 1, then switch to game.py.

Run:  py -3.11 sensor_server.py

If you get "OSError: [Errno 10048]" — another process owns port 8765.
  1. netstat -ano | findstr :8765
  2. taskkill /PID <pid> /F
"""

import asyncio
import json
import socket
import sys
import websockets
from datetime import datetime

# Force UTF-8 output so Greek/special chars don't crash on Windows cp1252
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "0.0.0.0"
PORT = 8765


# ─── port pre-check ────────────────────────────────────────────────────────────
def check_port_free(port: int) -> None:
    """Raise a clear RuntimeError if the port is already occupied."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
        except OSError:
            print(
                f"\n[ERROR] Port {port} is already in use (OSError 10048).\n"
                f"  Find the process:  netstat -ano | findstr :{port}\n"
                f"  Kill it:           taskkill /PID <pid> /F\n"
                f"  Then re-run this script.\n"
            )
            sys.exit(1)


# ─── console helpers ───────────────────────────────────────────────────────────
def fmt_val(v, unit="", width=8):
    return f"{v:+{width}.3f}{unit}"


async def handle_client(websocket):
    client_addr = websocket.remote_address
    print(f"\n[+] Phone connected: {client_addr}")

    packet_count = 0
    last_report  = asyncio.get_event_loop().time()

    try:
        async for raw in websocket:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                print(f"[!] Bad JSON: {raw[:80]}")
                continue

            packet_count += 1
            now = asyncio.get_event_loop().time()

            ts  = datetime.fromtimestamp(data.get("t", 0) / 1000).strftime("%H:%M:%S.%f")[:-3]
            ax  = data.get("ax", 0.0)
            ay  = data.get("ay", 0.0)
            az  = data.get("az", 0.0)
            ra  = data.get("ra", 0.0)
            rb  = data.get("rb", 0.0)
            rg  = data.get("rg", 0.0)

            # Use ASCII labels (a/b/g) instead of Greek chars — avoids cp1252 crash
            print(
                f"[{ts}]  "
                f"Acc  x={fmt_val(ax,'m/s2')}  y={fmt_val(ay,'m/s2')}  z={fmt_val(az,'m/s2')}   "
                f"Rot  a={fmt_val(ra,'deg/s')}  b={fmt_val(rb,'deg/s')}  g={fmt_val(rg,'deg/s')}  "
                f"#{packet_count}"
            )

            if now - last_report >= 5.0:
                hz = packet_count / (now - last_report)
                print(f"  ~{hz:.1f} Hz over last 5 s")
                packet_count = 0
                last_report  = now

    except websockets.exceptions.ConnectionClosedOK:
        pass
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"[!] Connection dropped: {e}")
    finally:
        print(f"[-] Phone disconnected: {client_addr}\n")


async def main():
    print("=" * 50)
    print("  Motion Sensor Server — Stage 1")
    print(f"  Listening on  ws://{HOST}:{PORT}")
    print()
    print("  NOTE: Do NOT run this alongside game.py —")
    print("  both bind port 8765 and will conflict!")
    print()
    print("  If you get OSError 10048:")
    print(f"    netstat -ano | findstr :{PORT}")
    print(f"    taskkill /PID <pid> /F")
    print("=" * 50 + "\n")

    async with websockets.serve(handle_client, HOST, PORT):
        await asyncio.Future()


if __name__ == "__main__":
    check_port_free(PORT)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[sensor_server] Stopped by user (Ctrl+C).")
