<div align="center">

# 🍉 Phone Fruit Ninja — Smart Motion Sensor

**Control a Fruit Ninja game on your PC using your Android phone as a motion controller — over local Wi-Fi, in real time.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Pygame](https://img.shields.io/badge/Pygame-2.5+-00B140?style=for-the-badge&logo=pygame&logoColor=white)](https://www.pygame.org/)
[![WebSockets](https://img.shields.io/badge/WebSockets-12.0+-FF6B35?style=for-the-badge&logo=websocket&logoColor=white)](https://websockets.readthedocs.io/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

> 📱 **Tilt your phone → Move the blade → Slice the fruit!**  
> Your Android phone's accelerometer and gyroscope become a real-time sword controller.

</div>

---

## 📖 Table of Contents

- [✨ Features](#-features)
- [🏗️ Architecture](#️-architecture)
- [📁 Project Structure](#-project-structure)
- [⚙️ Requirements](#️-requirements)
- [🚀 Quick Start](#-quick-start)
  - [Stage 1 — Verify Sensor Streaming](#stage-1--verify-sensor-streaming)
  - [Stage 2 — Play the Full Game](#stage-2--play-the-full-game)
- [📱 Phone Setup (First Time)](#-phone-setup-first-time)
- [🎮 In-Game Controls & HUD](#-in-game-controls--hud)
- [🔧 Tuning & Calibration](#-tuning--calibration)
- [🛠️ Troubleshooting](#️-troubleshooting)
- [🧠 How the Physics Work](#-how-the-physics-work)

---

## ✨ Features

| Feature | Description |
|---|---|
| 📡 **Real-time sensor streaming** | Phone streams accelerometer + gyroscope at ~60 Hz over WebSocket |
| 🍎 **6 unique fruit types** | Apple, Orange, Watermelon, Lemon, Strawberry, Plum — each with custom art |
| ⚔️ **Glowing blade trail** | Tapered cyan/white blade with glow tip — follows your phone movements |
| 💥 **Slice physics** | Fruits split into halves with juice particles and flash effects on contact |
| 🔄 **Dynamic gravity calibration** | Exponential moving average strips out gravity bias automatically |
| 🧭 **Calibration mode** | Press `C` in-game to see all 6 raw sensor axes live and pick the best mapping |
| 🌀 **Auto-recentering** | Cursor gently drifts back to center when idle (no more stuck cursor!) |
| 🖥️ **Debug HUD** | Live velocity, position, and blade speed readout every frame |

---

## 🏗️ Architecture

The project is split into two clean, decoupled stages:

```
┌─────────────────────────────────────────────────────────┐
│                   YOUR ANDROID PHONE                     │
│  ┌───────────────────────────────────────────────────┐  │
│  │           phone-sensor.html (Chrome)               │  │
│  │  DeviceMotionEvent → JSON → WebSocket client       │  │
│  └─────────────────────────┬─────────────────────────┘  │
└────────────────────────────│────────────────────────────┘
                             │  Wi-Fi  ws://LAPTOP_IP:8765
┌────────────────────────────▼────────────────────────────┐
│                  YOUR WINDOWS LAPTOP                     │
│  ┌──────────────────────────────────────────────────┐   │
│  │              game.py (Main Process)               │   │
│  │                                                   │   │
│  │  ┌─────────────────┐   deque(maxlen=1)            │   │
│  │  │  Background      │ ──────────────────►         │   │
│  │  │  Thread (asyncio)│   newest packet only        │   │
│  │  │  WebSocket Server│                             │   │
│  │  └─────────────────┘                             │   │
│  │                                                   │   │
│  │  ┌───────────────────────────────────────────┐   │   │
│  │  │  Pygame Main Thread (60 FPS)              │   │   │
│  │  │  • Read sensor → update velocity          │   │   │
│  │  │  • Physics: gravity strip, damping, clamp │   │   │
│  │  │  • Collision: blade vs. fruit             │   │   │
│  │  │  • Render: background, fruits, blade, HUD │   │   │
│  │  └───────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

> **Key design decision:** Sensor packets land in a `deque(maxlen=1)` — only the **freshest** packet is ever kept, so the game loop never runs on stale data regardless of network jitter.

---

## 📁 Project Structure

```
Smart_motion_sensor/
│
├── 📄 phone-sensor.html    # Phone UI: reads sensors, streams via WebSocket
│                           # Dark-mode UI with live axis bars + status pill
│
├── 🐍 sensor_server.py     # Stage 1 ONLY — diagnostic WebSocket server
│                           # Prints live sensor data to console
│                           # ⚠️  Do NOT run alongside game.py (same port!)
│
├── 🎮 game.py              # Stage 2: Full Fruit Ninja game (1011 lines)
│                           # Pygame + asyncio + threading
│
├── 📦 requirements.txt     # Python dependencies
│
└── 📖 README.md            # This file
```

---

## ⚙️ Requirements

- **Python 3.11+** (tested on Windows with `py -3.11`)
- **Android phone** with Chrome (any phone with accelerometer + gyroscope)
- **Same Wi-Fi network** for both devices

### Install Dependencies

```powershell
py -3.11 -m pip install -r requirements.txt
```

**`requirements.txt` contains:**
```
websockets>=12.0
pygame>=2.5.0
```

---

## 🚀 Quick Start

### Stage 1 — Verify Sensor Streaming

> Use this to confirm your phone can stream sensor data before running the full game.

#### Step 1 — Find Your Laptop's IP

```powershell
ipconfig
```

Look for **IPv4 Address** under **Wireless LAN adapter Wi-Fi:**

```
Wireless LAN adapter Wi-Fi:
   IPv4 Address. . . . . . . : 192.168.1.100   ← note this
```

---

#### Step 2 — Set Your IP in `phone-sensor.html`

Open `phone-sensor.html` and update line ~168:

```js
const LAPTOP_IP = "192.168.1.100";   // ← Replace with your actual IP
```

---

#### Step 3 — Start the Diagnostic WebSocket Server

```powershell
py -3.11 sensor_server.py
```

Expected output:
```
==================================================
  Motion Sensor Server — Stage 1
  Listening on  ws://0.0.0.0:8765

  NOTE: Do NOT run this alongside game.py — both bind port 8765 and will conflict!
==================================================
```

---

#### Step 4 — Serve the HTML Over HTTP

> Android Chrome **requires** HTTP (not `file://`) to access motion sensors.

Open a **second terminal** and run:

```powershell
py -3.11 -m http.server 8000
```

---

#### Step 5 — Connect Your Phone

1. On your phone, open **Chrome** (not Samsung Internet or Firefox)
2. Navigate to: `http://192.168.1.100:8000/phone-sensor.html`
3. Tap **Connect & Stream**
4. Status pill turns 🟢 **green** = success!

---

#### Step 6 — Verify Data

Back in the `sensor_server.py` terminal, you should see:

```
[+] Phone connected: ('192.168.1.101', 54321)
[14:32:01.123]  Acc  x=  +0.234m/s2  y=  -9.810m/s2  z=  +0.012m/s2   Rot  a= +0.000deg/s  b= +0.123deg/s  g= -0.456deg/s  #1
[14:32:01.140]  Acc  x=  +0.251m/s2  y=  -9.803m/s2  z=  +0.008m/s2   Rot  a= +0.000deg/s  b= +0.131deg/s  g= -0.449deg/s  #2
  ~60.0 Hz over last 5 s
```

✅ **Stage 1 is working!** Stop `sensor_server.py` before proceeding.

---

### Stage 2 — Play the Full Game

> ⚠️ **Never run `sensor_server.py` and `game.py` at the same time** — they both bind port 8765.

Open **two** terminal windows:

**Terminal 1 — HTTP server** (so your phone can load the HTML):
```powershell
py -3.11 -m http.server 8000
```

**Terminal 2 — Game**:
```powershell
py -3.11 game.py
```

A Pygame window opens immediately showing **"WAITING FOR PHONE…"**

On your phone: open `http://<LAPTOP_IP>:8000/phone-sensor.html` → tap **Connect & Stream**

The top-right turns 🟢 **PHONE CONNECTED** — now **swing the phone like a sword** to slice fruit!

---

## 📱 Phone Setup (First Time)

Android Chrome blocks sensor access on plain `http://` by default.  
Follow these one-time steps on your phone:

1. Open Chrome and go to:
   ```
   chrome://flags/#unsafely-treat-insecure-origin-as-secure
   ```
2. **Enable** the flag
3. Add your laptop's URL to the text box (e.g. `http://192.168.1.100:8000`)
4. Tap **Relaunch**

> This only needs to be done once per device.

---

## 🎮 In-Game Controls & HUD

### Keyboard Controls

| Key | Action |
|---|---|
| `ESC` | Quit the game |
| `R` | Reset score, clear all fruit, re-center cursor |
| `C` | Toggle **Calibration Mode** (see all 6 raw sensor axes live) |

### Debug HUD (top-left)

| Value | Meaning |
|---|---|
| `vel x / vel y` | Current cursor velocity in px/frame |
| `pos x / pos y` | Cursor pixel position on screen |
| `spd` | Blade tip speed — must exceed **3.0 px/frame** to register a slice |

### Connection Status (top-right)

| Display | Meaning |
|---|---|
| 🟢 `PHONE CONNECTED` | Sensor data arriving — blade is active |
| 🔴 `WAITING FOR PHONE...` (blinking) | No phone connected yet |

---

## 🔧 Tuning & Calibration

### In-Game Calibration (Press `C`)

A full-screen overlay shows all 6 raw sensor axes in real time. The axis with the **largest absolute value** is highlighted in yellow — that's the axis most sensitive to your phone's movement in that direction.

Use this to determine which axis to assign in the tunable constants below.

### Tunable Constants (`game.py`, top of file)

| Constant | Default | Effect |
|---|---|---|
| `CURSOR_X_AXIS` | `"ax"` | Which sensor axis drives horizontal cursor movement |
| `CURSOR_Y_AXIS` | `"ay"` | Which sensor axis drives vertical cursor movement |
| `INVERT_X` | `False` | Flip horizontal direction |
| `INVERT_Y` | `False` | Flip vertical direction |
| `ACCEL_SCALE_X` | `10.0` | Higher = more responsive horizontally |
| `ACCEL_SCALE_Y` | `10.0` | Higher = more responsive vertically |
| `DAMPING` | `0.80` | `0.75` = tight/precise · `0.90` = floaty/drifty |
| `SLICE_MIN_SPEED` | `3.0 px/f` | Min blade speed to register a cut |
| `FRUIT_SPAWN_RATE` | `90 frames` | Lower = more fruit = harder |
| `TRAIL_LENGTH` | `18` | Longer trail = easier to hit wide slices |

---

## 🛠️ Troubleshooting

### ❌ OSError: [Errno 10048] — Port 8765 Already in Use

This happens when a previous process is still holding port 8765, or both scripts are running simultaneously.

```powershell
# Step 1 — find the process
netstat -ano | findstr :8765

# Step 2 — kill it (replace 12345 with the actual PID)
taskkill /PID 12345 /F

# Step 3 — confirm port is free (should return nothing)
netstat -ano | findstr :8765

# Step 4 — restart
py -3.11 game.py
```

---

### ❌ Phone Shows "Connection Error" / Can't Reach WebSocket

| Symptom | Fix |
|---|---|
| Can't load `phone-sensor.html` in browser | Make sure `py -3.11 -m http.server 8000` is running |
| WebSocket never connects | Verify `LAPTOP_IP` in `phone-sensor.html` matches your `ipconfig` Wi-Fi IP |
| Both devices on same Wi-Fi but still failing | Windows Firewall may be blocking — see below |

**Open firewall ports** (run PowerShell as Administrator):
```powershell
netsh advfirewall firewall add rule name="FruitNinja_WS"   dir=in action=allow protocol=TCP localport=8765
netsh advfirewall firewall add rule name="FruitNinja_HTTP" dir=in action=allow protocol=TCP localport=8000
```

---

### ❌ Phone Shows "Disconnected (code 1011)" Immediately

Code `1011` = the server crashed right after the phone connected.

| Cause | Fix |
|---|---|
| Port conflict | Kill old process, restart `game.py` |
| `UnicodeEncodeError` in console | Already fixed in latest code — re-run |
| Pygame crashed before WS was ready | Check terminal for Python traceback |

---

### ❌ "DeviceMotionEvent not available" on Phone

Android Chrome blocks sensor access on plain `http://`. Follow the [📱 Phone Setup (First Time)](#-phone-setup-first-time) section to add your laptop URL as a trusted origin.

---

### ❌ Cursor Gets Stuck at Screen Edges

This is fixed in the latest version via edge-reflection and auto-recentering:
- **Velocity is reflected** (multiplied by `−0.5`) when hitting a boundary — no hard zero-clamp
- **Auto-recentering**: if cursor velocity stays below `0.5 px/f` for >2 seconds, a gentle spring pulls it back to `(640, 360)`
- Press **`R`** to instantly reset cursor to center

---

### 🔄 Clean Restart (One-Liner)

```powershell
# Kill any Python process on port 8765, then start the game
$pid = (netstat -ano | Select-String ":8765").ToString().Trim().Split()[-1]; if ($pid) { taskkill /PID $pid /F }; py -3.11 game.py
```

In a **second** PowerShell window:
```powershell
py -3.11 -m http.server 8000
```

---

## 🧠 How the Physics Work

### Sensor → Cursor Motion

```
raw_ax = phone accelerationIncludingGravity.x   (tilt left/right)
raw_ay = phone accelerationIncludingGravity.y   (tilt forward/back)

# Strip gravity using exponential moving average (α = 0.95)
grav_x = 0.95 * grav_x + 0.05 * raw_ax         # tracks slow-moving gravity
motion_ax = raw_ax - grav_x                     # pure motion signal

# Velocity integration
vel_x += motion_ax × ACCEL_SCALE_X
vel_y -= motion_ay × ACCEL_SCALE_Y             # screen Y is flipped

# Damping (applied every frame — "air resistance")
vel_x *= DAMPING    # (e.g. 0.80)
vel_y *= DAMPING

# Integrate velocity → position
cursor_x += vel_x
cursor_y += vel_y
```

**Effect:** Swinging the phone fast builds velocity quickly. Holding it still decays velocity to zero within ~1 second thanks to damping. No more infinite drift!

### Slice Detection

The blade is a list of the last `TRAIL_LENGTH` cursor positions. Each frame, the game checks the **minimum distance from each fruit's center to each segment** of the trail. If that distance < fruit radius AND blade speed > `SLICE_MIN_SPEED`, the fruit is sliced.

### Fruit Halves

On slice, the fruit splits into a left and right half that inherit the original velocity, then diverge:
- **Left half:** `vx -= 2.5`, `vy -= 4.0` (flies up-left)
- **Right half:** `vx += 2.5`, `vy -= 4.0` (flies up-right)

Both halves spin and fall under gravity (`0.25 px/frame²`) until off-screen.

---

<div align="center">

**Built with ❤️ using Python, Pygame, WebSockets & the Web DeviceMotion API**

*Swing your phone. Slice the fruit. Be the ninja.*  
⭐ **Star this repo if you found it useful!**

</div>
#   M o t i o n B r i d g e - C o n t r o l - P C - G a m e s - w i t h - Y o u r - S m a r t p h o n e - S e n s o r s  
 