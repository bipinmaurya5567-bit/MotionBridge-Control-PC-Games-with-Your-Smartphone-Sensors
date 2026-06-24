<div align="center">

# 🎮 MotionBridge
### Control PC Games with Your Smartphone Sensors

**Turn your Android phone into a real-time motion controller — no app install, no cables, just Wi-Fi.**

<br/>

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Pygame](https://img.shields.io/badge/Pygame-2.5+-00B140?style=for-the-badge&logo=python&logoColor=white)](https://www.pygame.org/)
[![WebSockets](https://img.shields.io/badge/WebSockets-12.0+-FF6B35?style=for-the-badge&logo=websocket&logoColor=white)](https://websockets.readthedocs.io/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://www.microsoft.com/)
[![License](https://img.shields.io/badge/License-MIT-F7C948?style=for-the-badge)](LICENSE)

<br/>

> **📱 Tilt your phone → ⚔️ Move the blade → 🍉 Slice the fruit!**
>
> Your phone's accelerometer and gyroscope stream live motion data over local Wi-Fi to a Python Pygame game on your PC. Open one webpage on your phone — that's all it takes.

<br/>

</div>

---

## 📖 Table of Contents

- [✨ Features](#-features)
- [🏗️ How It Works](#️-how-it-works)
- [📁 Project Structure](#-project-structure)
- [⚙️ Requirements](#️-requirements)
- [🚀 Quick Start](#-quick-start)
  - [Stage 1 — Verify Sensor Streaming](#-stage-1--verify-sensor-streaming)
  - [Stage 2 — Play the Full Game](#-stage-2--play-the-full-game)
- [📱 First-Time Phone Setup](#-first-time-phone-setup)
- [🎮 In-Game Controls & HUD](#-in-game-controls--hud)
- [🧠 How the Physics Work](#-how-the-physics-work)
- [🛠️ Troubleshooting](#️-troubleshooting)
- [📜 License](#-license)

---

## ✨ Features

| | Feature | Description |
|---|---|---|
| 📡 | **Real-time sensor streaming** | Phone streams accelerometer + gyroscope at ~60 Hz over WebSocket |
| 🍎 | **6 unique fruit types** | Apple, Orange, Watermelon, Lemon, Strawberry, Plum — each with custom pixel art |
| ⚔️ | **Glowing blade trail** | Tapered cyan/white blade with a glowing tip that follows your phone movements |
| 💥 | **Slice physics** | Fruits split into animated halves with juice particles and flash effects on cut |
| 🔄 | **Dynamic gravity calibration** | Exponential moving average auto-strips gravity bias every frame |
| 🧭 | **Calibration mode** | Press `C` in-game to view all 6 raw sensor axes live and tune your mapping |
| 🌀 | **Auto-recentering** | Cursor gently springs back to center after 2 seconds of inactivity |
| 📵 | **Zero app install** | Phone only needs a browser — served via Python's built-in HTTP server |
| 🖥️ | **Debug HUD** | Live velocity, position, and blade speed readout every frame |

---

## 🏗️ How It Works

```
┌──────────────────────────────────────────────┐
│               ANDROID PHONE                  │
│                                              │
│   phone-sensor.html  (Chrome browser)        │
│   ┌──────────────────────────────────────┐   │
│   │  DeviceMotionEvent API               │   │
│   │  → Reads ax, ay, az, ra, rb, rg      │   │
│   │  → JSON packet every ~16 ms (~60 Hz) │   │
│   │  → WebSocket client sends to laptop  │   │
│   └──────────────────────┬───────────────┘   │
└─────────────────────────-│───────────────────┘
                           │
                Wi-Fi  ws://LAPTOP_IP:8765
                           │
┌──────────────────────────▼───────────────────┐
│              WINDOWS LAPTOP                  │
│                                              │
│  ┌───────────────┐    deque(maxlen=1)         │
│  │ Background    │ ─────────────────────►    │
│  │ Thread        │   Freshest packet only     │
│  │ asyncio WS    │   (no stale queue lag)     │
│  │ Server :8765  │                            │
│  └───────────────┘                            │
│                                              │
│  ┌───────────────────────────────────────┐   │
│  │  Pygame Main Thread  @ 60 FPS         │   │
│  │                                       │   │
│  │  1. Read sensor → strip gravity       │   │
│  │  2. Integrate accel → velocity        │   │
│  │  3. Apply damping + edge bounce       │   │
│  │  4. Blade trail collision detection   │   │
│  │  5. Render: bg, fruits, blade, HUD    │   │
│  └───────────────────────────────────────┘   │
└──────────────────────────────────────────────┘
```

> **Design note:** All sensor packets land in a `deque(maxlen=1)` — only the **newest** packet is ever processed. This prevents lag accumulation from network jitter and keeps the game running at a consistent 60 FPS.

---

## 📁 Project Structure

```
MotionBridge/
│
├── 📄 phone-sensor.html     ← Open this on your phone in Chrome
│                              Reads DeviceMotion sensors, streams via WebSocket
│                              Dark-mode UI with live axis bars + status indicator
│
├── 🐍 sensor_server.py      ← Stage 1 ONLY — diagnostic console server
│                              Prints all incoming sensor data to terminal
│                              ⚠️  Uses same port as game.py — never run together!
│
├── 🎮 game.py               ← Stage 2 — Full Fruit Ninja game
│                              Pygame + asyncio WebSocket server on background thread
│                              1011 lines: physics, rendering, calibration mode
│
├── 📦 requirements.txt      ← Python dependencies (websockets, pygame)
│
└── 📖 README.md             ← You are here
```

---

## ⚙️ Requirements

- **Python 3.11+** (Windows, tested with `py -3.11`)
- **Android phone** running Chrome (any device with accelerometer + gyroscope)
- **Same local Wi-Fi network** on both laptop and phone

### Install Python Dependencies

```powershell
pip install pygame websockets
```

Or using the requirements file:

```powershell
pip install -r requirements.txt
```

---

## 🚀 Quick Start

### 🔬 Stage 1 — Verify Sensor Streaming

> Confirm your phone can stream data before launching the full game.

**Step 1 — Find your laptop's local IP address**

```powershell
ipconfig
```

Look for **IPv4 Address** under **Wireless LAN adapter Wi-Fi:**

```
Wireless LAN adapter Wi-Fi:
   IPv4 Address. . . . . . . : 192.168.1.100   ← Copy this
```

---

**Step 2 — Set your IP in `phone-sensor.html`**

Open `phone-sensor.html` in any text editor and update this line:

```js
const LAPTOP_IP = "192.168.1.100";   // ← Replace with your actual IP
```

---

**Step 3 — Start the diagnostic WebSocket server**

```powershell
python sensor_server.py
```

You should see:
```
==================================================
  Motion Sensor Server — Stage 1
  Listening on  ws://0.0.0.0:8765
==================================================
```

---

**Step 4 — Serve `phone-sensor.html` over HTTP**

> Android Chrome **requires HTTP** (not `file://`) to access motion sensors.

Open a **second terminal** and run:

```powershell
python -m http.server 8000
```

---

**Step 5 — Connect your phone**

1. Ensure phone and laptop are on the **same Wi-Fi**
2. Open **Chrome** on your phone
3. Navigate to: `http://192.168.1.100:8000/phone-sensor.html`
4. Tap **Connect & Stream**
5. The status pill turns 🟢 green — you're connected!

---

**Step 6 — Verify data is arriving**

In the `sensor_server.py` terminal, you should see:

```
[+] Phone connected: ('192.168.1.101', 54321)
[14:32:01.123]  Acc  x=  +0.234m/s2  y=  -9.810m/s2  z=  +0.012m/s2   Rot  a=+0.000deg/s  #1
[14:32:01.140]  Acc  x=  +0.251m/s2  y=  -9.803m/s2  z=  +0.008m/s2   Rot  a=+0.000deg/s  #2
  ~60.0 Hz over last 5 s
```

✅ **Stage 1 complete!** Stop `sensor_server.py` before proceeding.

---

### 🎮 Stage 2 — Play the Full Game

> ⚠️ **Never run `sensor_server.py` and `game.py` at the same time** — both bind port 8765.

Open **two** terminal windows:

**Terminal 1 — HTTP server** (so the phone can load the HTML):

```powershell
python -m http.server 8000
```

**Terminal 2 — Launch the game:**

```powershell
python game.py
```

The Pygame window opens showing **"WAITING FOR PHONE…"**

On your phone → open `http://<LAPTOP_IP>:8000/phone-sensor.html` → tap **Connect & Stream**

Top-right turns 🟢 **PHONE CONNECTED** — now **swing your phone like a sword!** 🗡️

---

## 📱 First-Time Phone Setup

Android Chrome blocks sensor access on plain `http://` by default. This is a **one-time setup**:

1. Open Chrome on your phone and navigate to:
   ```
   chrome://flags/#unsafely-treat-insecure-origin-as-secure
   ```

2. **Enable** the flag

3. In the text box below it, add your laptop's full URL:
   ```
   http://192.168.1.100:8000
   ```

4. Tap **Relaunch** at the bottom

> ✅ This only needs to be done once per device.

---

## 🎮 In-Game Controls & HUD

### Keyboard Controls

| Key | Action |
|---|---|
| `ESC` | Quit the game |
| `R` | Reset score, clear all fruit, re-center cursor |
| `C` | Toggle **Calibration Mode** — see all 6 raw sensor axes live |

### Debug HUD (top-left corner)

| Field | Meaning |
|---|---|
| `vel x / vel y` | Current cursor velocity in px/frame |
| `pos x / pos y` | Cursor pixel position on the 1280×720 screen |
| `spd` | Blade tip speed — must exceed **3.0 px/frame** to register a slice |

### Connection Status (top-right corner)

| Display | Meaning |
|---|---|
| 🟢 `PHONE CONNECTED` | Sensor data arriving — blade is fully active |
| 🔴 `WAITING FOR PHONE...` *(blinking)* | No phone connected yet |

---

## 🧠 How the Physics Work

<details>
<summary><strong>📐 Sensor → Cursor Motion (click to expand)</strong></summary>

<br/>

The phone sends raw `accelerationIncludingGravity` (includes Earth's ~9.8 m/s² pull).  
To get **pure motion**, gravity is stripped using an exponential moving average (EMA):

```python
# Track the slowly-changing gravity vector (α = 0.95 = slow decay)
grav_x = 0.95 * grav_x + 0.05 * raw_ax   # gravity estimate
grav_y = 0.95 * grav_y + 0.05 * raw_ay

# Pure motion = raw reading minus the gravity estimate
motion_ax = raw_ax - grav_x
motion_ay = raw_ay - grav_y

# Integrate into cursor velocity
vel_x += motion_ax * ACCEL_SCALE_X
vel_y -= motion_ay * ACCEL_SCALE_Y    # screen Y is flipped

# Apply damping every frame ("air resistance" — prevents infinite drift)
vel_x *= DAMPING   # default: 0.80
vel_y *= DAMPING

# Integrate velocity into position
cursor_x += vel_x
cursor_y += vel_y
```

Swinging the phone fast builds velocity quickly. Holding it still decays velocity to zero in ~1 second.

</details>

<details>
<summary><strong>⚔️ Blade Slice Detection (click to expand)</strong></summary>

<br/>

The blade is stored as a list of the last `TRAIL_LENGTH` (18) cursor positions.

Each frame, the game computes the **minimum distance from each fruit's center to every segment** of the blade trail. If:

- Distance < fruit radius, **AND**
- `blade_speed >= SLICE_MIN_SPEED` (3.0 px/frame)

→ The fruit is sliced!

On slice, the fruit splits into left and right halves with diverging velocities:

```python
left_half.vx  = fruit.vx - 2.5   # flies left
right_half.vx = fruit.vx + 2.5   # flies right
# Both inherit upward momentum and spin under gravity (0.25 px/frame²)
```

</details>

<details>
<summary><strong>🌀 Auto-Recentering & Edge Bounce (click to expand)</strong></summary>

<br/>

**Edge bounce:** When the cursor hits a screen boundary, velocity is reflected and halved (elastic bounce) — no hard zero-clamp that would freeze movement.

```python
if cursor_x <= 0:
    cursor_x = 0
    vel_x = -0.5 * vel_x    # bounce with energy loss
```

**Auto-recentering:** If cursor speed stays below `0.5 px/frame` for more than 2 seconds (120 frames), a gentle spring pulls the cursor back toward `(640, 360)`:

```python
if low_vel_frames >= 120:
    cursor_x = 640.0 + (cursor_x - 640.0) * 0.98   # 2% pull per frame
    cursor_y = 360.0 + (cursor_y - 360.0) * 0.98
```

Press **`R`** at any time to instantly snap the cursor to center.

</details>

---

## 🛠️ Troubleshooting

<details>
<summary><strong>❌ OSError: [Errno 10048] — Port 8765 Already In Use</strong></summary>

<br/>

This happens when a previous `game.py` or `sensor_server.py` didn't fully exit, or when both are running at the same time.

> ⚠️ **Never run `sensor_server.py` and `game.py` simultaneously.**

**Fix:**

```powershell
# Step 1 — find the process holding port 8765
netstat -ano | findstr :8765

# Step 2 — kill it (replace 12345 with the actual PID from the output above)
taskkill /PID 12345 /F

# Step 3 — confirm the port is free (should return nothing)
netstat -ano | findstr :8765

# Step 4 — restart
python game.py
```

</details>

<details>
<summary><strong>❌ Phone Shows "Disconnected (code 1011)" Immediately After Connecting</strong></summary>

<br/>

Code `1011` = the server crashed with an unhandled exception right after the phone connected.

| Cause | Fix |
|---|---|
| Port conflict (another process on 8765) | Kill old process, restart `game.py` |
| `UnicodeEncodeError` in the terminal | Already fixed in latest code — re-run |
| Pygame crashed before WebSocket was ready | Check terminal output for a Python traceback |

Check the terminal running `game.py` — the crash reason is printed before exit.

</details>

<details>
<summary><strong>❌ "DeviceMotionEvent not available" on Phone</strong></summary>

<br/>

Android Chrome blocks sensor access on `http://` by default.

Follow the [📱 First-Time Phone Setup](#-first-time-phone-setup) section to enable the Chrome flag and whitelist your laptop's URL as a trusted origin.

> Use **Chrome** specifically — Samsung Internet and Firefox do not expose `DeviceMotionEvent` reliably.

</details>

<details>
<summary><strong>❌ Phone Can't Connect / WebSocket Keeps Failing</strong></summary>

<br/>

| Symptom | Fix |
|---|---|
| Can't load `phone-sensor.html` in browser | Make sure `python -m http.server 8000` is running |
| WebSocket never connects | Verify `LAPTOP_IP` in `phone-sensor.html` matches your `ipconfig` Wi-Fi IP |
| Both on same Wi-Fi but still failing | Windows Firewall may be blocking ports — see below |
| WebSocket connects then drops instantly | See "code 1011" section above |

**Open firewall ports** (run PowerShell as **Administrator**):

```powershell
netsh advfirewall firewall add rule name="MotionBridge_WS"   dir=in action=allow protocol=TCP localport=8765
netsh advfirewall firewall add rule name="MotionBridge_HTTP" dir=in action=allow protocol=TCP localport=8000
```

</details>

<details>
<summary><strong>🔄 Clean Restart — Step-by-Step</strong></summary>

<br/>

Run in a single PowerShell window:

```powershell
# Kill any Python process on port 8765
$p = (netstat -ano | Select-String ":8765").ToString().Trim().Split()[-1]
if ($p) { taskkill /PID $p /F }

# Launch the game
python game.py
```

In a **second** PowerShell window:

```powershell
python -m http.server 8000
```

</details>

---

## 📜 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**🏗️ Built with**

`Python` · `Pygame` · `WebSockets` · `HTML5 DeviceMotion API`

<br/>

⭐ **If you found this project useful, please give it a star!** ⭐

<br/>

Made with ❤️ by **[Bipin Maurya](https://github.com/bipinmaurya5567-bit)**

</div>