"""
game.py — Stage 2: Fruit Ninja (phone-controlled)
=======================================================
Architecture: asyncio + threading
  - A daemon thread owns its own asyncio loop and runs the WebSocket server,
    so it never blocks the Pygame main loop.
  - Sensor readings land in a thread-safe deque(maxlen=1) — always the
    freshest packet, never a stale queue.
  - The Pygame loop drains that deque each frame.
    All rendering/physics stays on the main thread (required by SDL/Pygame).

Run:  py -3.11 game.py

!! CONFLICT WARNING !!
  sensor_server.py (Stage 1) also binds port 8765.
  NEVER run both at the same time → OSError 10048.

If you get "OSError: [Errno 10048]":
  netstat -ano | findstr :8765
  taskkill /PID <pid> /F
"""

import asyncio
import json
import math
import random
import socket
import sys
import threading
import traceback
from collections import deque

import pygame
import websockets

# ══════════════════════════════════════════════════════════════════════════════
#  Force UTF-8 stdout so any unicode chars don't crash on Windows cp1252
# ══════════════════════════════════════════════════════════════════════════════
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ══════════════════════════════════════════════════════════════════════════════
#  TUNABLE CONSTANTS — adjust these to taste
# ══════════════════════════════════════════════════════════════════════════════

# ── WebSocket ──────────────────────────────────────────────────────────────
WS_HOST = "0.0.0.0"
WS_PORT = 8765

# ── Window ─────────────────────────────────────────────────────────────────
SCREEN_W = 1280
SCREEN_H = 720
FPS      = 60

# ══════════════════════════════════════════════════════════════════════════════
#  AXIS MAPPING — edit these after running calibration mode (press C in-game)
# ══════════════════════════════════════════════════════════════════════════════
CURSOR_X_AXIS    = "ax"
CURSOR_Y_AXIS    = "ay"
INVERT_X         = False
INVERT_Y         = False
ACCEL_SCALE_X    = 10.0
ACCEL_SCALE_Y    = 10.0
# ══════════════════════════════════════════════════════════════════════════════

# DAMPING: fraction of velocity kept each frame (0–1).
# ~0.90 = snappy but drifty; ~0.75 = tight & precise.
DAMPING          = 0.80

# GRAVITY_OFFSET_Y is deprecated. We now use dynamic gravity calibration (high-pass filter).
GRAVITY_OFFSET_Y = 0.0

# ── Blade (cursor trail) ───────────────────────────────────────────────────
TRAIL_LENGTH  = 18     # past positions kept (~0.3 seconds at 60 FPS)
TRAIL_MIN_W   = 2      # blade width at oldest point (px)
TRAIL_MAX_W   = 14     # blade width at newest point (px)

# Minimum speed (px/frame) for the blade to count as "slicing"
SLICE_MIN_SPEED = 3.0

# ── Fruit ──────────────────────────────────────────────────────────────────
FRUIT_RADIUS      = 38
FRUIT_SPAWN_RATE  = 90          # frames between spawns (lower = harder)
FRUIT_MIN_SPEED_Y = -14         # launch speed (negative = up)
FRUIT_MAX_SPEED_Y = -9
FRUIT_GRAVITY     = 0.25        # px/frame² downward acceleration
MAX_FRUITS        = 12

# ── Particles ──────────────────────────────────────────────────────────────
PARTICLE_COUNT    = 14
PARTICLE_LIFETIME = 35          # frames
PARTICLE_SPEED    = 5.5         # max launch speed

# ── Colours ────────────────────────────────────────────────────────────────
BG_TOP    = (10,  8, 25)
BG_BOT    = (20, 12, 40)
HUD_COLOR = (200, 200, 220)
BLADE_TIP = (255, 255, 255)
BLADE_MID = (180, 120, 255)
SCORE_COL = (255, 220, 50)

FRUIT_PALETTE = [
    ((220, 50,  50),  (255, 130, 130), (200, 30,  30)),   # red apple
    ((255, 165,  30), (255, 210, 120), (220, 120,  20)),   # orange
    ((80,  190,  60), (160, 240, 130), (50,  150,  40)),   # watermelon
    ((240, 230,  30), (255, 255, 160), (200, 190,  10)),   # lemon
    ((160,  50, 200), (210, 130, 255), (130,  30, 170)),   # plum
    ((255, 100, 150), (255, 180, 200), (220,  60, 120)),   # strawberry
]

# ══════════════════════════════════════════════════════════════════════════════
#  Shared sensor state
# ══════════════════════════════════════════════════════════════════════════════
sensor_queue: deque = deque(maxlen=1)   # newest packet only
ws_connected         = threading.Event()

# ══════════════════════════════════════════════════════════════════════════════
#  Port pre-check
# ══════════════════════════════════════════════════════════════════════════════
def check_port_free(port: int) -> None:
    """
    Try to bind the port. If it fails → print a clear diagnosis and exit.
    This is faster/cleaner than letting websockets crash mid-startup.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
        except OSError:
            print(
                "\n" + "=" * 60 + "\n"
                f"  [ERROR] Port {port} is already in use (OSError 10048).\n\n"
                f"  Another Python process (sensor_server.py or a previous\n"
                f"  game.py) is still holding this port.\n\n"
                f"  Step 1 — find the offending PID:\n"
                f"    netstat -ano | findstr :{port}\n\n"
                f"  Step 2 — kill it:\n"
                f"    taskkill /PID <pid> /F\n\n"
                f"  Then re-run:  py -3.11 game.py\n"
                + "=" * 60 + "\n"
            )
            sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
#  WebSocket server (runs in background thread)
# ══════════════════════════════════════════════════════════════════════════════
async def ws_handler(websocket):
    ws_connected.set()
    addr = websocket.remote_address
    print(f"[WS] Phone connected: {addr}")
    try:
        async for raw in websocket:
            try:
                data = json.loads(raw)
                sensor_queue.append(data)
            except json.JSONDecodeError:
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as exc:
        print(f"[WS] Handler exception: {exc}")
    finally:
        ws_connected.clear()
        print(f"[WS] Phone disconnected: {addr}")


async def ws_server_coro():
    try:
        async with websockets.serve(ws_handler, WS_HOST, WS_PORT):
            print(f"[WS] Server running  ws://{WS_HOST}:{WS_PORT}")
            await asyncio.Future()   # run until cancelled
    except OSError as exc:
        # Shouldn't reach here (check_port_free already tested), but just in case
        print(f"[WS] Failed to start server: {exc}")


def ws_thread_main():
    """Entry point for the background WebSocket thread."""
    try:
        asyncio.run(ws_server_coro())
    except Exception as exc:
        print(f"[WS thread] Unexpected error: {exc}")
        traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════════
#  Fruit Drawing Helpers & Cache
# ══════════════════════════════════════════════════════════════════════════════
FRUIT_CACHE = {}

def draw_radial_gradient(surface, cx, cy, r, base_color, highlight_color=(255, 255, 255)):
    pygame.draw.circle(surface, base_color, (cx, cy), r)
    # Overlay multiple circles with offset centers to simulate 3D volume
    for i in range(1, 6):
        ratio = i / 5.0
        c = (
            int(base_color[0] + (highlight_color[0] - base_color[0]) * ratio * 0.6),
            int(base_color[1] + (highlight_color[1] - base_color[1]) * ratio * 0.6),
            int(base_color[2] + (highlight_color[2] - base_color[2]) * ratio * 0.6)
        )
        hx = int(cx - (r // 3) * ratio)
        hy = int(cy - (r // 3) * ratio)
        hr = int(r * (1 - ratio * 0.7))
        if hr > 0:
            pygame.draw.circle(surface, c, (hx, hy), hr)

def draw_radial_gradient_ellipse(surf, cx, cy, rx, ry, base_color, highlight_color=(255, 255, 255)):
    rect = (cx - rx, cy - ry, rx * 2, ry * 2)
    pygame.draw.ellipse(surf, base_color, rect)
    for i in range(1, 6):
        ratio = i / 5.0
        c = (
            int(base_color[0] + (highlight_color[0] - base_color[0]) * ratio * 0.6),
            int(base_color[1] + (highlight_color[1] - base_color[1]) * ratio * 0.6),
            int(base_color[2] + (highlight_color[2] - base_color[2]) * ratio * 0.6)
        )
        hx = int(cx - (rx // 3) * ratio)
        hy = int(cy - (ry // 3) * ratio)
        hrx = int(rx * (1 - ratio * 0.7))
        hry = int(ry * (1 - ratio * 0.7))
        if hrx > 0 and hry > 0:
            pygame.draw.ellipse(surf, c, (hx - hrx, hy - hry, hrx * 2, hry * 2))

def draw_fruit_surface(type, r):
    size = r * 3
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx, cy = size // 2, size // 2

    if type == "watermelon":
        # Green sphere with dark green stripes
        draw_radial_gradient(surf, cx, cy, r, (76, 175, 80), (139, 195, 74))
        # Stripes
        for dx in [-r//2, -r//4, 0, r//4, r//2]:
            pygame.draw.arc(surf, (46, 125, 50), (cx + dx - 8, cy - r, 16, r*2), -math.pi/2, math.pi/2, 3)
    elif type == "orange":
        # Orange with dot pattern and green stem
        draw_radial_gradient(surf, cx, cy, r, (255, 128, 0), (255, 200, 100))
        # Small dots
        for i in range(15):
            random.seed(i + 100)
            rx = random.randint(-r+5, r-5)
            ry = random.randint(-r+5, r-5)
            if math.hypot(rx, ry) < r - 3:
                pygame.draw.circle(surf, (220, 100, 0), (cx + rx, cy + ry), 1)
        # Stem on top
        pygame.draw.line(surf, (101, 67, 33), (cx, cy - r), (cx, cy - r - 6), 2)
        pygame.draw.circle(surf, (76, 175, 80), (cx + 3, cy - r - 5), 2)
    elif type == "apple":
        # Red apple with stem and green leaf
        draw_radial_gradient(surf, cx, cy, r, (220, 30, 30), (255, 120, 120))
        # Stem
        pygame.draw.line(surf, (101, 67, 33), (cx, cy - r + 3), (cx + 4, cy - r - 8), 2)
        # Leaf
        leaf_pts = [(cx + 4, cy - r - 8), (cx + 10, cy - r - 10), (cx + 8, cy - r - 5)]
        pygame.draw.polygon(surf, (76, 175, 80), leaf_pts)
    elif type == "lemon":
        # Yellow oval with small tips
        draw_radial_gradient_ellipse(surf, cx, cy, int(r * 1.25), r, (240, 230, 30), (255, 255, 180))
        pygame.draw.circle(surf, (210, 200, 20), (cx - int(r*1.2), cy), 4)
        pygame.draw.circle(surf, (210, 200, 20), (cx + int(r*1.2), cy), 4)
    elif type == "strawberry":
        # Red teardrop shape with seed dots and green leaf top
        pts = []
        for a in range(0, 360, 10):
            rad = a * math.pi / 180
            factor = 1.0 - 0.25 * math.sin(rad)
            px = cx + int(r * factor * math.cos(rad))
            py = cy + int(r * factor * math.sin(rad) * 1.1)
            pts.append((px, py))
        pygame.draw.polygon(surf, (230, 30, 60), pts)
        pygame.draw.polygon(surf, (150, 10, 30), pts, 1)

        # Seeds
        for i in range(16):
            random.seed(i + 200)
            rx = random.randint(-r+6, r-6)
            ry = random.randint(-r+6, r-6)
            if math.hypot(rx, ry) < r - 4:
                pygame.draw.circle(surf, (255, 255, 150), (cx + rx, cy + ry), 1)
        # Green leaf top
        leaf_pts = [(cx, cy - r), (cx - 8, cy - r - 4), (cx - 4, cy - r + 2), 
                    (cx + 8, cy - r - 4), (cx + 4, cy - r + 2)]
        pygame.draw.polygon(surf, (46, 125, 50), leaf_pts)
    elif type == "plum":
        # Deep purple circle
        draw_radial_gradient(surf, cx, cy, r, (100, 30, 120), (180, 80, 200))
    return surf

def draw_cut_face(surf, cx, cy, r, type):
    if type == "watermelon":
        pygame.draw.circle(surf, (46, 125, 50), (cx, cy), r)
        pygame.draw.circle(surf, (240, 240, 240), (cx, cy), r - 3)
        pygame.draw.circle(surf, (230, 30, 30), (cx, cy), r - 6)
        # Seeds
        seed_offsets = [(-r//3, -r//4), (r//3, -r//4), (-r//4, r//4), (r//4, r//4), (0, -r//3), (0, r//3)]
        for ox, oy in seed_offsets:
            pygame.draw.circle(surf, (20, 20, 20), (cx + ox, cy + oy), 2)
    elif type == "orange":
        pygame.draw.circle(surf, (255, 128, 0), (cx, cy), r)
        pygame.draw.circle(surf, (255, 230, 180), (cx, cy), r - 2)
        pygame.draw.circle(surf, (255, 140, 0), (cx, cy), r - 4)
        for a in range(0, 360, 45):
            rad = a * math.pi / 180
            tx = cx + int((r - 4) * math.cos(rad))
            ty = cy + int((r - 4) * math.sin(rad))
            pygame.draw.line(surf, (255, 230, 180), (cx, cy), (tx, ty), 1)
    elif type == "apple":
        pygame.draw.circle(surf, (220, 30, 30), (cx, cy), r)
        pygame.draw.circle(surf, (255, 253, 208), (cx, cy), r - 2)
        # Seed pit area
        pygame.draw.ellipse(surf, (210, 180, 140), (cx - 5, cy - 8, 10, 16))
        pygame.draw.circle(surf, (101, 67, 33), (cx - 2, cy), 2)
        pygame.draw.circle(surf, (101, 67, 33), (cx + 2, cy), 2)
    elif type == "lemon":
        pygame.draw.circle(surf, (240, 230, 30), (cx, cy), r)
        pygame.draw.circle(surf, (255, 255, 200), (cx, cy), r - 2)
        pygame.draw.circle(surf, (245, 235, 40), (cx, cy), r - 4)
        for a in range(0, 360, 45):
            rad = a * math.pi / 180
            tx = cx + int((r - 4) * math.cos(rad))
            ty = cy + int((r - 4) * math.sin(rad))
            pygame.draw.line(surf, (255, 255, 200), (cx, cy), (tx, ty), 1)
    elif type == "strawberry":
        pygame.draw.circle(surf, (230, 30, 60), (cx, cy), r)
        pygame.draw.circle(surf, (255, 100, 120), (cx, cy), r - 3)
        pygame.draw.ellipse(surf, (255, 240, 240), (cx - r//4, cy - r//2, r//2, r))
    elif type == "plum":
        pygame.draw.circle(surf, (100, 30, 120), (cx, cy), r)
        pygame.draw.circle(surf, (235, 210, 80), (cx, cy), r - 3)
        pygame.draw.circle(surf, (80, 30, 10), (cx, cy), r // 3)

def draw_half_surface(type, r, side):
    size = r * 3
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx, cy = size // 2, size // 2
    draw_cut_face(surf, cx, cy, r, type)
    if side == "left":
        surf.fill((0, 0, 0, 0), (cx, 0, size - cx, size))
    else:
        surf.fill((0, 0, 0, 0), (0, 0, cx, size))
    return surf

def get_fruit_surface(type, r):
    key = (type, r)
    if key not in FRUIT_CACHE:
        FRUIT_CACHE[key] = draw_fruit_surface(type, r)
    return FRUIT_CACHE[key]

def get_half_surface(type, r, side):
    key = (type, r, side)
    if key not in FRUIT_CACHE:
        FRUIT_CACHE[key] = draw_half_surface(type, r, side)
    return FRUIT_CACHE[key]

# ══════════════════════════════════════════════════════════════════════════════
#  Game entities
# ══════════════════════════════════════════════════════════════════════════════
class Fruit:
    def __init__(self):
        self.type = random.choice(["watermelon", "orange", "apple", "lemon", "strawberry", "plum"])
        self.radius = FRUIT_RADIUS
        if self.type == "watermelon":
            self.radius = int(FRUIT_RADIUS * 1.35)
        
        self.x = random.randint(self.radius + 60, SCREEN_W - self.radius - 60)
        self.y = SCREEN_H + self.radius + 10
        self.vy = random.uniform(FRUIT_MIN_SPEED_Y, FRUIT_MAX_SPEED_Y)
        self.vx = random.uniform(-2.5, 2.5)
        self.spin = random.uniform(-4, 4)
        self.angle = 0.0
        self.alive = True
        self.sliced = False
        
        # Halves physics
        self.lx = 0.0
        self.ly = 0.0
        self.rx = 0.0
        self.ry = 0.0
        self.lvx = 0.0
        self.lvy = 0.0
        self.rvx = 0.0
        self.rvy = 0.0
        self.l_angle = 0.0
        self.r_angle = 0.0
        
        # Colors for particles
        juice_colors = {
            "watermelon": (230, 30, 30),
            "orange":     (255, 140, 0),
            "apple":      (255, 253, 208),
            "lemon":      (245, 235, 40),
            "strawberry": (255, 100, 120),
            "plum":       (180, 80, 200)
        }
        self.juice = juice_colors[self.type]

    def update(self):
        if not self.sliced:
            self.vy += FRUIT_GRAVITY
            self.x  += self.vx
            self.y  += self.vy
            self.angle += self.spin
            if self.y > SCREEN_H + self.radius + 50:
                self.alive = False
        else:
            # Update halves
            self.lvy += FRUIT_GRAVITY
            self.lx  += self.lvx
            self.ly  += self.lvy
            self.l_angle -= 5.0
            
            self.rvy += FRUIT_GRAVITY
            self.rx  += self.rvx
            self.ry  += self.rvy
            self.r_angle += 5.0
            
            # If both halves go off-screen
            if self.ly > SCREEN_H + self.radius + 100 and self.ry > SCREEN_H + self.radius + 100:
                self.alive = False

    def draw(self, surface):
        if not self.alive:
            return
            
        if not self.sliced:
            # Draw shadow
            r = self.radius
            shadow = pygame.Surface((r*2+4, r//2+4), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (0, 0, 0, 60), (0, 0, r*2+4, r//2+4))
            surface.blit(shadow, (int(self.x) - r - 2, int(self.y) + r - 4))
            
            # Get cached intact fruit surface
            surf = get_fruit_surface(self.type, self.radius)
            # Rotate
            rot_surf = pygame.transform.rotate(surf, self.angle)
            rect = rot_surf.get_rect(center=(int(self.x), int(self.y)))
            surface.blit(rot_surf, rect.topleft)
        else:
            # Get cached halves surfaces
            left_surf = get_half_surface(self.type, self.radius, "left")
            right_surf = get_half_surface(self.type, self.radius, "right")
            
            # Rotate
            rot_left = pygame.transform.rotate(left_surf, self.l_angle)
            rot_right = pygame.transform.rotate(right_surf, self.r_angle)
            
            rect_left = rot_left.get_rect(center=(int(self.lx), int(self.ly)))
            rect_right = rot_right.get_rect(center=(int(self.rx), int(self.ry)))
            
            surface.blit(rot_left, rect_left.topleft)
            surface.blit(rot_right, rect_right.topleft)


class Particle:
    def __init__(self, x, y, color):
        self.x    = x + random.uniform(-8, 8)
        self.y    = y + random.uniform(-8, 8)
        angle     = random.uniform(0, 2 * math.pi)
        speed     = random.uniform(1.5, PARTICLE_SPEED)
        self.vx   = math.cos(angle) * speed
        self.vy   = math.sin(angle) * speed - random.uniform(1, 3)
        self.life = PARTICLE_LIFETIME
        self.max  = PARTICLE_LIFETIME
        self.rad  = random.randint(3, 8)
        self.col  = color

    def update(self):
        self.vy += 0.18
        self.x  += self.vx
        self.y  += self.vy
        self.life -= 1

    def draw(self, surface):
        if self.life <= 0:
            return
        alpha  = int(255 * (self.life / self.max))
        r, g, b = self.col
        color  = (min(255,r+60), min(255,g+60), min(255,b+60), alpha)
        s      = pygame.Surface((self.rad*2, self.rad*2), pygame.SRCALPHA)
        pygame.draw.circle(s, color, (self.rad, self.rad), self.rad)
        surface.blit(s, (int(self.x) - self.rad, int(self.y) - self.rad))


class SliceFlash:
    def __init__(self, x, y):
        self.x    = x
        self.y    = y
        self.life = 18

    def update(self):
        self.life -= 1

    def draw(self, surface):
        if self.life <= 0:
            return
        t     = self.life / 18
        alpha = int(200 * t)
        r     = int(60 * (1 - t))
        s     = pygame.Surface((r*2+2, r*2+2), pygame.SRCALPHA)
        pygame.draw.circle(s, (255, 240, 100, alpha), (r+1, r+1), r+1)
        surface.blit(s, (int(self.x) - r - 1, int(self.y) - r - 1))


# ══════════════════════════════════════════════════════════════════════════════
#  Geometry helpers
# ══════════════════════════════════════════════════════════════════════════════
def dist_point_to_segment(px, py, ax, ay, bx, by):
    """Closest distance from point (px,py) to segment (ax,ay)-(bx,by)."""
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax)*dx + (py - ay)*dy) / (dx*dx + dy*dy)))
    return math.hypot(px - ax - t*dx, py - ay - t*dy)


def blade_hits_fruit(trail, fruit):
    r, fx, fy = fruit.radius, fruit.x, fruit.y
    for i in range(len(trail) - 1):
        ax, ay = trail[i]
        bx, by = trail[i+1]
        if dist_point_to_segment(fx, fy, ax, ay, bx, by) < r:
            return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
#  Rendering helpers
# ══════════════════════════════════════════════════════════════════════════════
def draw_background(surface):
    for y in range(SCREEN_H):
        t   = y / SCREEN_H
        col = (
            int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t),
            int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t),
            int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t),
        )
        pygame.draw.line(surface, col, (0, y), (SCREEN_W, y))


def draw_blade(surface, trail, blade_speed):
    """Two-pass tapered blade: cyan outer glow + bright white core."""
    if len(trail) < 2:
        return
    n = len(trail)
    # Pre-build a shared SRCALPHA surface for segment drawing
    seg = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)

    # Pass 1 — outer cyan/blue glow (thicker, more transparent)
    for i in range(n - 1):
        age_ratio = i / max(n - 1, 1)          # 0 = oldest, 1 = newest
        alpha = int(20 + 130 * age_ratio)       # fades out at tail
        width = int(4 + 18 * age_ratio)         # tapers: thin at tail, thick at tip
        seg.fill((0, 0, 0, 0))
        pygame.draw.line(seg, (0, 180, 255, alpha),
                         (int(trail[i][0]),   int(trail[i][1])),
                         (int(trail[i+1][0]), int(trail[i+1][1])), width)
        surface.blit(seg, (0, 0))

    # Pass 2 — bright white core (thinner)
    for i in range(n - 1):
        age_ratio = i / max(n - 1, 1)
        alpha = int(60 + 195 * age_ratio)
        width = max(1, int(1 + 7 * age_ratio))
        seg.fill((0, 0, 0, 0))
        pygame.draw.line(seg, (255, 255, 255, alpha),
                         (int(trail[i][0]),   int(trail[i][1])),
                         (int(trail[i+1][0]), int(trail[i+1][1])), width)
        surface.blit(seg, (0, 0))

    # Glowing radial dot at the blade tip
    tip = trail[-1]
    tx, ty = int(tip[0]), int(tip[1])
    glow = pygame.Surface((50, 50), pygame.SRCALPHA)
    pygame.draw.circle(glow, (180, 240, 255, 70),  (25, 25), 22)
    pygame.draw.circle(glow, (100, 200, 255, 120), (25, 25), 14)
    pygame.draw.circle(glow, (255, 255, 255, 200), (25, 25), 6)
    surface.blit(glow, (tx - 25, ty - 25))


def _draw_calib_overlay(surface, font_sm, font_lg, raw_vals):
    """Full-screen calibration panel — shows all 6 raw sensor values live.
    The axis with the largest absolute value is highlighted in yellow.
    Press C again to exit calibration mode.
    """
    # 1. Darkened semi-transparent overlay
    panel = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    panel.fill((10, 8, 25, 220))  # Sleek dark blue/indigo transparent bg
    surface.blit(panel, (0, 0))

    # 2. Outer border for the calibration area
    pygame.draw.rect(surface, (80, 70, 140), (40, 40, SCREEN_W - 80, SCREEN_H - 80), width=3, border_radius=15)

    # 3. Title & Instructions
    title = font_lg.render("CALIBRATION MODE", True, (255, 220, 50))
    surface.blit(title, (SCREEN_W // 2 - title.get_width() // 2, 70))

    sub = font_sm.render("Swing your phone and watch which raw sensor value spikes the most.", True, (180, 180, 220))
    surface.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, 135))
    
    sub2 = font_sm.render("Press 'C' to exit and resume the game.", True, (130, 130, 160))
    surface.blit(sub2, (SCREEN_W // 2 - sub2.get_width() // 2, 160))

    # 4. Find the largest absolute value
    max_key = ""
    max_val = -1.0
    for k, v in raw_vals.items():
        if abs(v) > max_val:
            max_val = abs(v)
            max_key = k

    # Fonts
    font_val = pygame.font.SysFont("Consolas", 42, bold=True)
    font_lbl = pygame.font.SysFont("Consolas", 24, bold=True)
    
    # 5. Draw 2x3 Grid
    cols = [180, 500, 820]
    box_w = 280
    box_h = 110

    # Map keys to positions
    grid = [
        {"key": "ax", "row": 0, "col": 0, "label": "ax (Accel X)"},
        {"key": "ay", "row": 0, "col": 1, "label": "ay (Accel Y)"},
        {"key": "az", "row": 0, "col": 2, "label": "az (Accel Z)"},
        {"key": "rx", "row": 1, "col": 0, "label": "rx (Gyro X)"},
        {"key": "ry", "row": 1, "col": 1, "label": "ry (Gyro Y)"},
        {"key": "rz", "row": 1, "col": 2, "label": "rz (Gyro Z)"},
    ]

    for item in grid:
        key = item["key"]
        v = raw_vals.get(key, 0.0)
        is_max = (key == max_key)

        col_idx = item["col"]
        row_idx = item["row"]
        bx = cols[col_idx]
        by = 210 + row_idx * 150

        # Draw box background
        box_bg = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        if is_max:
            box_bg.fill((255, 220, 0, 30))  # Semi-transparent yellow glow
            pygame.draw.rect(surface, (255, 220, 0), (bx, by, box_w, box_h), width=3, border_radius=10)
        else:
            box_bg.fill((30, 30, 60, 120))  # Standard dark box
            pygame.draw.rect(surface, (60, 60, 100), (bx, by, box_w, box_h), width=1, border_radius=10)
        
        surface.blit(box_bg, (bx, by))

        # Render Label
        lbl_color = (255, 220, 0) if is_max else (160, 160, 200)
        lbl_surf = font_lbl.render(item["label"], True, lbl_color)
        surface.blit(lbl_surf, (bx + 15, by + 15))

        # Render Value
        val_str = f"{v:+.2f}"
        val_color = (255, 220, 0) if is_max else (220, 220, 255)
        val_surf = font_val.render(val_str, True, val_color)
        surface.blit(val_surf, (bx + 15, by + 50))

    # 6. Draw LARGEST label at the bottom
    largest_font = pygame.font.SysFont("Consolas", 48, bold=True)
    largest_lbl = largest_font.render(f"LARGEST: {max_key.upper()}", True, (255, 220, 0))
    surface.blit(largest_lbl, (SCREEN_W // 2 - largest_lbl.get_width() // 2, 530))

    # 7. Current configuration notice
    config_font = pygame.font.SysFont("Consolas", 18)
    config_str = (
        f"Config: CURSOR_X_AXIS = \"{CURSOR_X_AXIS}\" | CURSOR_Y_AXIS = \"{CURSOR_Y_AXIS}\" "
        f"| INVERT_X = {INVERT_X} | INVERT_Y = {INVERT_Y} | ACCEL_SCALE_X = {ACCEL_SCALE_X} | ACCEL_SCALE_Y = {ACCEL_SCALE_Y}"
    )
    config_lbl = config_font.render(config_str, True, (120, 220, 120))
    surface.blit(config_lbl, (SCREEN_W // 2 - config_lbl.get_width() // 2, 620))


def draw_hud(surface, font_sm, font_lg,
             vel_x, vel_y, cur_x, cur_y, speed,
             score, frame, connected):
    # Score — top centre
    score_txt = font_lg.render(f"{score}", True, SCORE_COL)
    surface.blit(score_txt, (SCREEN_W//2 - score_txt.get_width()//2, 16))

    # Connection status — top right
    if connected:
        conn_col  = (80, 255, 140)
        conn_text = "PHONE CONNECTED"
    else:
        conn_col  = (255, 80, 80) if (frame // 30) % 2 == 0 else (120, 40, 40)
        conn_text = "WAITING FOR PHONE..."
    ct = font_sm.render(conn_text, True, conn_col)
    surface.blit(ct, (SCREEN_W - ct.get_width() - 16, 16))

    # Debug HUD — top left
    debug_lines = [
        f"vel  x:{vel_x:+.1f}  y:{vel_y:+.1f}",
        f"pos  x:{int(cur_x)}  y:{int(cur_y)}",
        f"spd  {speed:.1f} px/f",
    ]
    for i, line in enumerate(debug_lines):
        txt = font_sm.render(line, True, HUD_COLOR)
        surface.blit(txt, (14, 14 + i * 22))

    # Hint when not connected
    if not connected:
        hint = font_sm.render(
            "Open phone-sensor.html on phone  -->  tap Connect & Stream",
            True, (160, 140, 200)
        )
        surface.blit(hint, (SCREEN_W//2 - hint.get_width()//2, SCREEN_H - 40))


# ══════════════════════════════════════════════════════════════════════════════
#  Main game loop
# ══════════════════════════════════════════════════════════════════════════════
def run_game():
    """Run the Pygame loop. Returns a string describing why it exited."""
    pygame.init()
    screen  = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Phone Fruit Ninja")
    clock   = pygame.time.Clock()

    font_sm = pygame.font.SysFont("Consolas", 17)
    font_lg = pygame.font.SysFont("Consolas", 52, bold=True)

    # Pre-render gradient background once
    bg_surf = pygame.Surface((SCREEN_W, SCREEN_H))
    draw_background(bg_surf)

    # ── Game state ───────────────────────────────────────────────────────────
    cur_x = float(SCREEN_W // 2)
    cur_y = float(SCREEN_H // 2)
    vel_x = 0.0
    vel_y = 0.0
    last_ax = 0.0
    last_ay = 0.0
    last_az = 0.0

    # Gravity tracking for dynamic calibration (high-pass filter)
    grav_x = 0.0
    grav_y = 0.0
    grav_z = 0.0
    first_packet = True

    # Frame counter for recentering
    low_vel_frames = 0

    # Calibration mode
    calib_mode  = False
    raw_vals    = {"ax": 0.0, "ay": 0.0, "az": 0.0, "rx": 0.0, "ry": 0.0, "rz": 0.0}

    trail:     list = []
    fruits:    list = []
    particles: list = []
    flashes:   list = []

    score       = 0
    frame       = 0
    spawn_timer = 0
    exit_reason = "User closed the window (QUIT event)"

    try:
        while True:
            # ── Events ───────────────────────────────────────────────────
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "User closed the window (QUIT event)"
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return "User pressed ESC"
                    elif event.key == pygame.K_c:
                        calib_mode = not calib_mode
                    elif event.key == pygame.K_r:
                        score = 0
                        fruits.clear()
                        particles.clear()
                        flashes.clear()
                        cur_x = float(SCREEN_W // 2)
                        cur_y = float(SCREEN_H // 2)
                        vel_x = 0.0
                        vel_y = 0.0
                        trail.clear()
                        low_vel_frames = 0
                        first_packet = True

            # ── Sensor input ─────────────────────────────────────────────
            connected = ws_connected.is_set()

            if sensor_queue:
                data = sensor_queue.pop()
                raw_ax = data.get("ax", 0.0)
                raw_ay = data.get("ay", 0.0)
                raw_az = data.get("az", 0.0)
                raw_ra = data.get("ra", 0.0)
                raw_rb = data.get("rb", 0.0)
                raw_rg = data.get("rg", 0.0)

                # Store raw values for calibration overlay
                raw_vals = {
                    "ax": raw_ax, "ay": raw_ay, "az": raw_az,
                    "rx": raw_ra, "ry": raw_rb, "rz": raw_rg,
                }

                if first_packet:
                    grav_x = raw_ax
                    grav_y = raw_ay
                    grav_z = raw_az
                    first_packet = False
                else:
                    # Exponential moving average to track steady gravity vector
                    alpha = 0.95
                    grav_x = alpha * grav_x + (1 - alpha) * raw_ax
                    grav_y = alpha * grav_y + (1 - alpha) * raw_ay
                    grav_z = alpha * grav_z + (1 - alpha) * raw_az

                # Motion = raw minus gravity
                last_ax = raw_ax - grav_x
                last_ay = raw_ay - grav_y
                last_az = raw_az - grav_z

            # ── Acceleration → velocity integration ───────────────────────
            if connected:
                # Use CURSOR_X_AXIS / CURSOR_Y_AXIS to pick which sensor drives each screen axis
                sensor_map = {
                    "ax": last_ax,
                    "ay": last_ay,
                    "az": last_az,
                    "rx": raw_vals.get("rx", 0.0),
                    "ry": raw_vals.get("ry", 0.0),
                    "rz": raw_vals.get("rz", 0.0),
                }
                sx = sensor_map.get(CURSOR_X_AXIS, last_ax) * ACCEL_SCALE_X * (-1 if INVERT_X else 1)
                sy = sensor_map.get(CURSOR_Y_AXIS, last_ay) * ACCEL_SCALE_Y * (-1 if INVERT_Y else 1)
                vel_x += sx
                vel_y -= sy   # screen Y flipped: tilt forward = cursor up
            else:
                # If disconnected, reset state and stop applying forces
                first_packet = True
                last_ax = 0.0
                last_ay = 0.0
                last_az = 0.0

            # ── Damping every frame (applied exactly once per frame) ──────
            # This ensures the cursor decelerates smoothly even if the phone 
            # streams at a lower rate than the game loop's 60 FPS.
            vel_x *= DAMPING
            vel_y *= DAMPING

            # ── Integrate: velocity → position ───────────────────────────
            cur_x += vel_x
            cur_y += vel_y

            # ── Clamp to screen and reflect/bounce velocity on boundary hit ─────
            # Reflects the velocity component to bounce off boundaries with elastic behavior (multiplied by -0.5),
            # preventing the cursor from getting stuck.
            if cur_x <= 0.0:
                cur_x = 0.0
                if vel_x < 0.0:
                    vel_x = -0.5 * vel_x
            elif cur_x >= float(SCREEN_W):
                cur_x = float(SCREEN_W)
                if vel_x > 0.0:
                    vel_x = -0.5 * vel_x

            if cur_y <= 0.0:
                cur_y = 0.0
                if vel_y < 0.0:
                    vel_y = -0.5 * vel_y
            elif cur_y >= float(SCREEN_H):
                cur_y = float(SCREEN_H)
                if vel_y > 0.0:
                    vel_y = -0.5 * vel_y

            # ── Auto-recentering spring force ─────────────────────────────
            # If cursor velocity magnitude stays below 0.5 px/f for > 2 seconds (120 frames),
            # gently pull the cursor back toward screen center (640, 360).
            vel_mag = math.hypot(vel_x, vel_y)
            if vel_mag < 0.5:
                low_vel_frames += 1
            else:
                low_vel_frames = 0

            if low_vel_frames >= 120:
                cur_x = 640.0 + (cur_x - 640.0) * 0.98
                cur_y = 360.0 + (cur_y - 360.0) * 0.98

            # ── Blade trail ───────────────────────────────────────────────
            trail.append((cur_x, cur_y))
            if len(trail) > TRAIL_LENGTH:
                trail.pop(0)

            if len(trail) >= 2:
                dx, dy      = trail[-1][0] - trail[-2][0], trail[-1][1] - trail[-2][1]
                blade_speed = math.hypot(dx, dy)
            else:
                blade_speed = 0.0

            blade_active = blade_speed >= SLICE_MIN_SPEED

            # ── Spawn fruit (frozen during calibration) ───────────────────
            if not calib_mode:
                spawn_timer += 1
                if spawn_timer >= FRUIT_SPAWN_RATE and len(fruits) < MAX_FRUITS:
                    fruits.append(Fruit())
                    spawn_timer = 0

            # ── Update + collision ────────────────────────────────────────
            surviving = []
            for fruit in fruits:
                fruit.update()
                if fruit.alive and blade_active and not fruit.sliced:
                    if blade_hits_fruit(trail, fruit):
                        fruit.sliced = True
                        score += 1
                        # Set up halves at the fruit's current position
                        fruit.lx = fruit.x - fruit.radius * 0.3
                        fruit.ly = fruit.y
                        fruit.rx = fruit.x + fruit.radius * 0.3
                        fruit.ry = fruit.y
                        # Left half: flies left-up, right half: flies right-up
                        fruit.lvx = fruit.vx - 2.5
                        fruit.lvy = fruit.vy - 4.0
                        fruit.rvx = fruit.vx + 2.5
                        fruit.rvy = fruit.vy - 4.0
                        fruit.l_angle = fruit.angle
                        fruit.r_angle = fruit.angle
                        for _ in range(PARTICLE_COUNT):
                            particles.append(Particle(fruit.x, fruit.y, fruit.juice))
                        flashes.append(SliceFlash(fruit.x, fruit.y))
                if fruit.alive:
                    surviving.append(fruit)
            fruits = surviving

            particles = [p for p in particles if p.life > 0]
            for p in particles:
                p.update()

            flashes = [f for f in flashes if f.life > 0]
            for f in flashes:
                f.update()

            # ── Render ────────────────────────────────────────────────────
            screen.blit(bg_surf, (0, 0))
            for fruit in fruits:
                fruit.draw(screen)
            for p in particles:
                p.draw(screen)
            for f in flashes:
                f.draw(screen)
            draw_blade(screen, trail, blade_speed)
            draw_hud(screen, font_sm, font_lg,
                     vel_x, vel_y, cur_x, cur_y, blade_speed,
                     score, frame, connected)

            # ── Calibration overlay (press C to toggle) ──────────────────
            if calib_mode:
                _draw_calib_overlay(screen, font_sm, font_lg, raw_vals)

            pygame.display.flip()
            clock.tick(FPS)
            frame += 1

    except Exception as exc:
        return f"CRASH — unhandled exception: {exc}\n{traceback.format_exc()}"
    finally:
        pygame.quit()


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════
def main():
    print()
    print("=" * 60)
    print("  Phone Fruit Ninja — game.py")
    print()
    print(f"  Starting WebSocket server on port {WS_PORT} ...")
    print(f"  Pygame window will open next.")
    print()
    print("  If startup fails with OSError 10048 (port in use):")
    print(f"    netstat -ano | findstr :{WS_PORT}")
    print(f"    taskkill /PID <pid> /F")
    print()
    print("  Controls:  ESC = quit   R = reset score")
    print("=" * 60 + "\n")

    # Pre-check: fail fast with a clear message if port is occupied
    check_port_free(WS_PORT)

    # Start WebSocket server in background thread
    ws_thread = threading.Thread(target=ws_thread_main, daemon=True, name="ws-server")
    ws_thread.start()

    # Give the server half a second to bind before the window opens
    import time; time.sleep(0.5)

    # Run Pygame on the main thread
    reason = run_game()

    print(f"\n[game] Exited — reason: {reason}")
    if "CRASH" in reason:
        print("[game] A crash occurred. Full traceback is above.")
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
