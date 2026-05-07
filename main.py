import math
import random
import threading
import time
import tkinter as tk

try:
    import winsound
except ImportError:
    winsound = None


WIDTH = 1280
HEIGHT = 720
TARGET_FPS = 120
FRAME_MS = max(4, int(1000 / TARGET_FPS))
MAX_DT = 1.0 / 30.0

THEME = {
    "bg": "#05080f",
    "panel": "#101a2b",
    "grid": "#17253f",
    "neon_blue": "#16d9ff",
    "neon_cyan": "#57f6ff",
    "neon_green": "#39ff96",
    "neon_red": "#ff4f7a",
    "neon_orange": "#ffad4f",
    "text": "#d8ecff",
    "muted": "#8fa8c4",
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def normalize(x: float, y: float) -> tuple[float, float, float]:
    length = math.hypot(x, y)
    if length <= 1e-9:
        return 0.0, 0.0, 0.0
    return x / length, y / length, length


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


def scale_color(color: str, factor: float) -> str:
    r, g, b = hex_to_rgb(color)
    factor = clamp(factor, 0.0, 2.0)
    return rgb_to_hex(
        (
            int(clamp(r * factor, 0, 255)),
            int(clamp(g * factor, 0, 255)),
            int(clamp(b * factor, 0, 255)),
        )
    )


class Particle:
    """Simple neon particle for hits, dashes, and ambient effects."""

    __slots__ = (
        "game",
        "x",
        "y",
        "vx",
        "vy",
        "size",
        "life",
        "max_life",
        "color",
        "drag",
        "gravity",
        "kind",
        "item_id",
    )

    def __init__(
        self,
        game,
        x: float,
        y: float,
        vx: float,
        vy: float,
        size: float,
        life: float,
        color: str,
        drag: float = 3.0,
        gravity: float = 0.0,
        kind: str = "circle",
    ):
        self.game = game
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.size = size
        self.life = life
        self.max_life = life
        self.color = color
        self.drag = drag
        self.gravity = gravity
        self.kind = kind
        c = self.game.canvas
        if kind == "line":
            self.item_id = c.create_line(
                0, 0, 1, 1, fill=color, width=max(1.0, size * 0.25), capstyle=tk.ROUND
            )
        else:
            self.item_id = c.create_oval(0, 0, 1, 1, fill=color, outline="")

    def update(self, dt: float) -> bool:
        self.life -= dt
        if self.life <= 0.0:
            return False

        self.vy += self.gravity * dt
        if self.drag > 0:
            damp = max(0.0, 1.0 - self.drag * dt)
            self.vx *= damp
            self.vy *= damp

        self.x += self.vx * dt
        self.y += self.vy * dt
        return True

    def draw(self, camera_x: float, camera_y: float) -> None:
        t = clamp(self.life / self.max_life, 0.0, 1.0)
        size = max(0.4, self.size * t)
        color = scale_color(self.color, 0.35 + t * 0.95)
        x = self.x + camera_x
        y = self.y + camera_y

        if self.kind == "line":
            tail = 8.0 * (1.0 - t)
            self.game.canvas.coords(
                self.item_id, x - self.vx * 0.01, y - self.vy * 0.01, x + tail, y + tail
            )
            self.game.canvas.itemconfig(self.item_id, fill=color)
            return

        self.game.canvas.coords(self.item_id, x - size, y - size, x + size, y + size)
        self.game.canvas.itemconfig(self.item_id, fill=color)

    def destroy(self) -> None:
        self.game.canvas.delete(self.item_id)


class Player:
    def __init__(self, game, x: float, y: float):
        self.game = game
        self.x = x
        self.y = y
        self.size = 34
        self.speed = 300.0
        self.max_hp = 220.0
        self.hp = self.max_hp

        self.facing_x = 1.0
        self.facing_y = 0.0

        self.kb_vx = 0.0
        self.kb_vy = 0.0

        self.attack_range = 86.0
        self.attack_damage = 25.0
        self.attack_cooldown = 0.23
        self.attack_timer = 0.0
        self.attack_anim = 0.0

        self.dash_speed = 760.0
        self.dash_duration = 0.14
        self.dash_cooldown = 0.9
        self.dash_timer = 0.0
        self.dash_cd_timer = 0.0
        self.dash_dir_x = 1.0
        self.dash_dir_y = 0.0

        self.hit_invuln = 0.0
        self.hit_flash = 0.0

        self.combo = 0
        self.combo_timer = 0.0
        self.max_combo_window = 2.4
        self.crit_chance = 0.19
        self.crit_mult = 1.75

        c = self.game.canvas
        self.glow_id = c.create_rectangle(
            0, 0, 1, 1, outline=THEME["neon_cyan"], width=3
        )
        self.body_id = c.create_rectangle(
            0, 0, 1, 1, fill="#0e1f36", outline=THEME["neon_blue"], width=2
        )
        self.core_id = c.create_rectangle(0, 0, 1, 1, fill="#122748", outline="")
        self.attack_id = c.create_arc(
            0,
            0,
            1,
            1,
            start=0,
            extent=0,
            style=tk.ARC,
            outline=THEME["neon_orange"],
            width=4,
            state="hidden",
        )

    def reset(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.hp = self.max_hp
        self.combo = 0
        self.combo_timer = 0.0
        self.kb_vx = 0.0
        self.kb_vy = 0.0
        self.attack_timer = 0.0
        self.attack_anim = 0.0
        self.dash_timer = 0.0
        self.dash_cd_timer = 0.0
        self.hit_invuln = 0.0
        self.hit_flash = 0.0

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def trigger_dash(self, keys_down: set[str]) -> None:
        if self.dash_cd_timer > 0.0 or self.dash_timer > 0.0 or not self.alive:
            return

        ix = ("d" in keys_down) - ("a" in keys_down)
        iy = ("s" in keys_down) - ("w" in keys_down)
        if ix == 0 and iy == 0:
            dx, dy = self.facing_x, self.facing_y
        else:
            dx, dy, _ = normalize(float(ix), float(iy))

        self.dash_dir_x = dx
        self.dash_dir_y = dy
        self.dash_timer = self.dash_duration
        self.dash_cd_timer = self.dash_cooldown

        for _ in range(10):
            ang = random.uniform(0.0, math.tau)
            spd = random.uniform(100.0, 360.0)
            self.game.spawn_particle(
                self.x,
                self.y,
                math.cos(ang) * spd,
                math.sin(ang) * spd,
                random.uniform(1.5, 3.3),
                random.uniform(0.2, 0.45),
                THEME["neon_cyan"],
            )

    def trigger_attack(self, enemies: list["Enemy"]) -> None:
        if self.attack_timer > 0.0 or not self.alive:
            return

        self.attack_timer = self.attack_cooldown
        self.attack_anim = 0.14

        front_x = self.x + self.facing_x * (self.size * 0.6)
        front_y = self.y + self.facing_y * (self.size * 0.6)
        hits = 0

        for enemy in enemies:
            if not enemy.alive or enemy.spawn_timer > 0.0:
                continue

            to_x = enemy.x - front_x
            to_y = enemy.y - front_y
            dir_x, dir_y, dist = normalize(to_x, to_y)
            if dist > self.attack_range + enemy.size * 0.45:
                continue

            # Attack cone check keeps melee directional and readable.
            dot = dir_x * self.facing_x + dir_y * self.facing_y
            if dot < 0.25 and dist > enemy.size * 0.6:
                continue

            combo_mult = 1.0 + min(12, self.combo) * 0.04
            dmg = self.attack_damage * combo_mult * random.uniform(0.92, 1.1)
            critical = random.random() < self.crit_chance
            if critical:
                dmg *= self.crit_mult

            enemy.take_damage(dmg, self.facing_x, self.facing_y, critical)
            kb = 420.0 if critical else 300.0
            enemy.kb_vx += self.facing_x * kb
            enemy.kb_vy += self.facing_y * kb
            hits += 1

            burst_color = THEME["neon_orange"] if critical else THEME["neon_blue"]
            self.game.hit_spark(enemy.x, enemy.y, burst_color, 10 if critical else 6)
            self.game.play_hit_sound(critical)
            self.game.add_shake(critical and 8.0 or 4.0, 0.12)

        if hits > 0:
            self.combo += hits
            self.combo_timer = self.max_combo_window
            self.game.score += hits * 9
        else:
            self.combo = max(0, self.combo - 1)

    def take_damage(self, amount: float, from_x: float, from_y: float) -> None:
        if self.hit_invuln > 0.0 or self.dash_timer > 0.0 or not self.alive:
            return

        self.hp -= amount
        self.hit_invuln = 0.25
        self.hit_flash = 0.2

        nx, ny, _ = normalize(self.x - from_x, self.y - from_y)
        if nx == 0 and ny == 0:
            nx = random.choice((-1.0, 1.0))
        self.kb_vx += nx * 360.0
        self.kb_vy += ny * 360.0
        self.game.add_shake(7.0, 0.15)
        self.game.hit_spark(self.x, self.y, THEME["neon_red"], 10)

        if self.hp <= 0:
            self.hp = 0
            self.game.set_state("game_over")

    def update(self, dt: float, keys_down: set[str]) -> None:
        if self.attack_timer > 0.0:
            self.attack_timer -= dt
        if self.dash_cd_timer > 0.0:
            self.dash_cd_timer -= dt
        if self.dash_timer > 0.0:
            self.dash_timer -= dt
        if self.hit_invuln > 0.0:
            self.hit_invuln -= dt
        if self.hit_flash > 0.0:
            self.hit_flash -= dt
        if self.attack_anim > 0.0:
            self.attack_anim -= dt

        if self.combo_timer > 0.0:
            self.combo_timer -= dt
            if self.combo_timer <= 0.0:
                self.combo = 0

        ix = ("d" in keys_down) - ("a" in keys_down)
        iy = ("s" in keys_down) - ("w" in keys_down)

        move_x = 0.0
        move_y = 0.0
        if ix != 0 or iy != 0:
            move_x, move_y, _ = normalize(float(ix), float(iy))
            self.facing_x = move_x
            self.facing_y = move_y

        if self.dash_timer > 0.0:
            vel_x = self.dash_dir_x * self.dash_speed
            vel_y = self.dash_dir_y * self.dash_speed
            if random.random() < 0.55:
                self.game.spawn_particle(
                    self.x,
                    self.y,
                    random.uniform(-60, 60),
                    random.uniform(-60, 60),
                    random.uniform(1.2, 2.6),
                    random.uniform(0.12, 0.22),
                    THEME["neon_cyan"],
                )
        else:
            vel_x = move_x * self.speed
            vel_y = move_y * self.speed

        self.x += (vel_x + self.kb_vx) * dt
        self.y += (vel_y + self.kb_vy) * dt

        kb_damp = max(0.0, 1.0 - 8.0 * dt)
        self.kb_vx *= kb_damp
        self.kb_vy *= kb_damp

        half = self.size * 0.5
        self.x = clamp(self.x, half + 6, WIDTH - half - 6)
        self.y = clamp(self.y, half + 6, HEIGHT - half - 6)

    def draw(self, camera_x: float, camera_y: float, time_s: float) -> None:
        x = self.x + camera_x
        y = self.y + camera_y
        half = self.size * 0.5

        pulse = 1.0 + math.sin(time_s * 8.0) * 0.08
        glow = half * (1.4 + 0.1 * pulse)

        self.game.canvas.coords(self.glow_id, x - glow, y - glow, x + glow, y + glow)
        self.game.canvas.coords(self.body_id, x - half, y - half, x + half, y + half)
        self.game.canvas.coords(
            self.core_id,
            x - half * 0.55,
            y - half * 0.55,
            x + half * 0.55,
            y + half * 0.55,
        )

        if self.hit_flash > 0.0:
            self.game.canvas.itemconfig(self.body_id, fill="#4f1a24", outline=THEME["neon_red"])
        else:
            self.game.canvas.itemconfig(self.body_id, fill="#0e1f36", outline=THEME["neon_blue"])

        if self.attack_anim > 0.0:
            self.game.canvas.itemconfig(self.attack_id, state="normal")
            r = self.attack_range
            ax = self.x + self.facing_x * r * 0.55 + camera_x
            ay = self.y + self.facing_y * r * 0.55 + camera_y
            self.game.canvas.coords(self.attack_id, ax - r, ay - r, ax + r, ay + r)
            angle = math.degrees(math.atan2(-self.facing_y, self.facing_x))
            self.game.canvas.itemconfig(
                self.attack_id,
                start=angle - 45,
                extent=90,
                outline=THEME["neon_orange"],
                width=4,
            )
        else:
            self.game.canvas.itemconfig(self.attack_id, state="hidden")


class Enemy:
    TYPE_DATA = {
        "normal": {
            "size": 30,
            "speed": 158,
            "max_hp": 70,
            "damage": 13,
            "attack_range": 40,
            "attack_cd": 0.95,
            "score": 60,
            "color": "#2dc0ff",
            "outline": "#7de6ff",
        },
        "fast": {
            "size": 24,
            "speed": 235,
            "max_hp": 42,
            "damage": 10,
            "attack_range": 34,
            "attack_cd": 0.64,
            "score": 75,
            "color": "#ff4da3",
            "outline": "#ff85c6",
        },
        "tank": {
            "size": 40,
            "speed": 110,
            "max_hp": 130,
            "damage": 20,
            "attack_range": 50,
            "attack_cd": 1.25,
            "score": 120,
            "color": "#20d98f",
            "outline": "#79ffc7",
        },
    }

    def __init__(self, game, enemy_type: str, x: float, y: float, hp_scale: float = 1.0):
        self.game = game
        self.enemy_type = enemy_type
        data = self.TYPE_DATA[enemy_type]

        self.x = x
        self.y = y
        self.size = float(data["size"])
        self.speed = float(data["speed"])
        self.max_hp = float(data["max_hp"]) * hp_scale
        self.hp = self.max_hp
        self.damage = float(data["damage"])
        self.attack_range = float(data["attack_range"])
        self.attack_cd = float(data["attack_cd"])
        self.score_value = int(data["score"])
        self.color = data["color"]
        self.outline = data["outline"]

        self.attack_timer = random.uniform(0.0, 0.5)
        self.kb_vx = 0.0
        self.kb_vy = 0.0
        self.flash = 0.0
        self.spawn_duration = 0.45
        self.spawn_timer = self.spawn_duration
        self.dead = False

        c = self.game.canvas
        self.glow_id = c.create_rectangle(0, 0, 1, 1, outline=self.outline, width=2)
        self.body_id = c.create_rectangle(
            0, 0, 1, 1, fill=self.color, outline=self.outline, width=2
        )
        self.core_id = c.create_rectangle(0, 0, 1, 1, fill=scale_color(self.color, 0.7), outline="")
        self.hp_bg_id = c.create_rectangle(0, 0, 1, 1, fill="#0e1522", outline="")
        self.hp_fg_id = c.create_rectangle(0, 0, 1, 1, fill=THEME["neon_green"], outline="")
        self.spawn_ring_id = c.create_oval(0, 0, 1, 1, outline=self.outline, width=2)

    @property
    def alive(self) -> bool:
        return not self.dead and self.hp > 0

    def take_damage(self, amount: float, dir_x: float, dir_y: float, critical: bool) -> None:
        if not self.alive:
            return

        self.hp -= amount
        self.flash = 0.15

        if self.hp <= 0:
            self.hp = 0
            self.dead = True
            self.game.score += self.score_value
            if critical:
                self.game.score += 30
            self.game.hit_spark(
                self.x, self.y, critical and THEME["neon_orange"] or self.outline, 14
            )
            self.game.spawn_particle(
                self.x,
                self.y,
                dir_x * 120,
                dir_y * 120,
                8,
                0.32,
                critical and THEME["neon_orange"] or self.outline,
            )
            return

        kb = 240.0 if self.enemy_type == "tank" else 320.0
        self.kb_vx += dir_x * kb
        self.kb_vy += dir_y * kb

    def update(self, dt: float, player: Player, enemies: list["Enemy"]) -> None:
        if self.flash > 0.0:
            self.flash -= dt
        if self.attack_timer > 0.0:
            self.attack_timer -= dt

        if not self.alive:
            return

        if self.spawn_timer > 0.0:
            self.spawn_timer -= dt
            if random.random() < 0.5:
                self.game.spawn_particle(
                    self.x,
                    self.y,
                    random.uniform(-60, 60),
                    random.uniform(-60, 60),
                    random.uniform(1.0, 2.2),
                    random.uniform(0.15, 0.3),
                    self.outline,
                )
            return

        to_px = player.x - self.x
        to_py = player.y - self.y
        dir_x, dir_y, distance = normalize(to_px, to_py)

        avoid_x = 0.0
        avoid_y = 0.0
        for other in enemies:
            if other is self or not other.alive:
                continue
            dx = self.x - other.x
            dy = self.y - other.y
            nx, ny, dist = normalize(dx, dy)
            min_dist = (self.size + other.size) * 0.8
            if 0.0001 < dist < min_dist:
                strength = (min_dist - dist) / min_dist
                avoid_x += nx * strength
                avoid_y += ny * strength

        move_x = dir_x * 1.05 + avoid_x * 1.8
        move_y = dir_y * 1.05 + avoid_y * 1.8
        move_x, move_y, _ = normalize(move_x, move_y)

        if distance <= self.attack_range + player.size * 0.35:
            if self.attack_timer <= 0.0:
                self.attack_timer = self.attack_cd
                dmg = self.damage * random.uniform(0.9, 1.1)
                player.take_damage(dmg, self.x, self.y)
                self.game.hit_spark(player.x, player.y, THEME["neon_red"], 6)
            move_x *= 0.25
            move_y *= 0.25

        self.x += (move_x * self.speed + self.kb_vx) * dt
        self.y += (move_y * self.speed + self.kb_vy) * dt

        kb_damp = max(0.0, 1.0 - 8.5 * dt)
        self.kb_vx *= kb_damp
        self.kb_vy *= kb_damp

        half = self.size * 0.5
        self.x = clamp(self.x, half + 4, WIDTH - half - 4)
        self.y = clamp(self.y, half + 4, HEIGHT - half - 4)

    def draw(self, camera_x: float, camera_y: float, t: float) -> None:
        if not self.alive and self.flash <= 0.0:
            self.hide()
            return

        scale = 1.0
        if self.spawn_timer > 0.0:
            prog = 1.0 - clamp(self.spawn_timer / self.spawn_duration, 0.0, 1.0)
            scale = 0.2 + prog * 0.8

        x = self.x + camera_x
        y = self.y + camera_y
        half = self.size * 0.5 * scale

        self.game.canvas.coords(
            self.glow_id, x - half * 1.3, y - half * 1.3, x + half * 1.3, y + half * 1.3
        )
        self.game.canvas.coords(self.body_id, x - half, y - half, x + half, y + half)
        self.game.canvas.coords(
            self.core_id,
            x - half * 0.5,
            y - half * 0.5,
            x + half * 0.5,
            y + half * 0.5,
        )

        if self.flash > 0.0:
            self.game.canvas.itemconfig(self.body_id, fill="#ffffff", outline=THEME["neon_orange"])
        else:
            self.game.canvas.itemconfig(self.body_id, fill=self.color, outline=self.outline)

        hp_w = self.size * 0.95
        hp_h = 5
        hp_x1 = x - hp_w * 0.5
        hp_y1 = y - half - 11
        hp_ratio = self.hp / self.max_hp if self.max_hp > 0 else 0

        self.game.canvas.coords(self.hp_bg_id, hp_x1, hp_y1, hp_x1 + hp_w, hp_y1 + hp_h)
        self.game.canvas.coords(
            self.hp_fg_id, hp_x1, hp_y1, hp_x1 + hp_w * hp_ratio, hp_y1 + hp_h
        )

        if self.spawn_timer > 0.0:
            ring = self.size * (1.0 + (1.0 - self.spawn_timer / self.spawn_duration) * 1.5)
            self.game.canvas.coords(self.spawn_ring_id, x - ring, y - ring, x + ring, y + ring)
            self.game.canvas.itemconfig(
                self.spawn_ring_id,
                state="normal",
                outline=scale_color(self.outline, 1.1 + math.sin(t * 18.0) * 0.2),
            )
        else:
            self.game.canvas.itemconfig(self.spawn_ring_id, state="hidden")

    def hide(self) -> None:
        for item_id in (
            self.glow_id,
            self.body_id,
            self.core_id,
            self.hp_bg_id,
            self.hp_fg_id,
            self.spawn_ring_id,
        ):
            self.game.canvas.itemconfig(item_id, state="hidden")

    def destroy(self) -> None:
        for item_id in (
            self.glow_id,
            self.body_id,
            self.core_id,
            self.hp_bg_id,
            self.hp_fg_id,
            self.spawn_ring_id,
        ):
            self.game.canvas.delete(item_id)


class WaveManager:
    def __init__(self, game):
        self.game = game
        self.current_wave = 0
        self.max_waves = 8
        self.delay_before_next = 1.5
        self.delay_timer = 0.0
        self.pending_spawns = 0
        self.spawn_cooldown = 0.22
        self.spawn_timer = 0.0

    def reset(self) -> None:
        self.current_wave = 0
        self.delay_timer = 0.8
        self.pending_spawns = 0
        self.spawn_timer = 0.0

    def start_next_wave(self) -> None:
        self.current_wave += 1
        if self.current_wave > self.max_waves:
            self.current_wave = self.max_waves
            return

        base_count = 3 + self.current_wave * 2
        self.pending_spawns = base_count + int(self.current_wave * 0.75)
        self.spawn_timer = 0.2

    def pick_type(self) -> str:
        w = self.current_wave
        r = random.random()
        fast_bias = clamp(0.18 + w * 0.055, 0.18, 0.55)
        tank_bias = clamp(0.06 + w * 0.05, 0.06, 0.32)

        if r < tank_bias:
            return "tank"
        if r < tank_bias + fast_bias:
            return "fast"
        return "normal"

    def spawn_enemy(self) -> None:
        margin = 60
        edge = random.randint(0, 3)

        if edge == 0:
            x = random.uniform(margin, WIDTH - margin)
            y = -40
        elif edge == 1:
            x = WIDTH + 40
            y = random.uniform(margin, HEIGHT - margin)
        elif edge == 2:
            x = random.uniform(margin, WIDTH - margin)
            y = HEIGHT + 40
        else:
            x = -40
            y = random.uniform(margin, HEIGHT - margin)

        enemy_type = self.pick_type()
        hp_scale = 1.0 + (self.current_wave - 1) * 0.08
        enemy = Enemy(self.game, enemy_type, x, y, hp_scale=hp_scale)
        self.game.enemies.append(enemy)

        for _ in range(12):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(80, 220)
            self.game.spawn_particle(
                x,
                y,
                math.cos(ang) * spd,
                math.sin(ang) * spd,
                random.uniform(1.0, 2.8),
                random.uniform(0.18, 0.35),
                enemy.outline,
            )

    def update(self, dt: float) -> None:
        if self.current_wave == 0 and self.pending_spawns == 0:
            self.start_next_wave()

        if self.pending_spawns > 0:
            self.spawn_timer -= dt
            if self.spawn_timer <= 0.0:
                self.spawn_timer = self.spawn_cooldown * random.uniform(0.85, 1.15)
                self.pending_spawns -= 1
                self.spawn_enemy()
            return

        if self.game.enemies:
            return

        if self.current_wave >= self.max_waves:
            self.game.set_state("victory")
            return

        self.delay_timer -= dt
        if self.delay_timer <= 0.0:
            self.delay_timer = self.delay_before_next
            self.start_next_wave()


class UI:
    def __init__(self, game):
        self.game = game
        c = self.game.canvas

        self.hud_panel = c.create_rectangle(
            16, 14, 390, 124, fill="#0b1220", outline="#1c314f", width=2
        )
        self.hp_bg = c.create_rectangle(32, 40, 332, 60, fill="#131b2b", outline="")
        self.hp_fg = c.create_rectangle(32, 40, 332, 60, fill=THEME["neon_green"], outline="")
        self.hp_text = c.create_text(182, 50, text="HP", fill=THEME["text"], font=("Consolas", 11, "bold"))

        self.score_text = c.create_text(
            38, 84, anchor="w", text="SCORE: 0", fill=THEME["text"], font=("Consolas", 14, "bold")
        )
        self.wave_text = c.create_text(
            220,
            84,
            anchor="w",
            text="WAVE: 1",
            fill=THEME["neon_cyan"],
            font=("Consolas", 14, "bold"),
        )
        self.fps_text = c.create_text(
            WIDTH - 16, 26, anchor="e", text="FPS: 0", fill=THEME["muted"], font=("Consolas", 11)
        )

        self.combo_text = c.create_text(
            WIDTH * 0.5,
            72,
            text="",
            fill=THEME["neon_orange"],
            font=("Consolas", 18, "bold"),
            state="hidden",
        )

        self.message_text = c.create_text(
            WIDTH * 0.5,
            HEIGHT * 0.18,
            text="",
            fill=THEME["neon_cyan"],
            font=("Consolas", 20, "bold"),
            state="hidden",
        )

        self.menu_overlay = c.create_rectangle(0, 0, WIDTH, HEIGHT, fill="#04070d", outline="")
        self.menu_title = c.create_text(
            WIDTH * 0.5,
            HEIGHT * 0.33,
            text="NEON BOX FIGHTER",
            fill=THEME["neon_cyan"],
            font=("Consolas", 50, "bold"),
        )
        self.menu_sub = c.create_text(
            WIDTH * 0.5,
            HEIGHT * 0.43,
            text="WASD Move   SPACE Attack   SHIFT Dash   ESC Pause",
            fill=THEME["muted"],
            font=("Consolas", 16),
        )
        self.menu_play = c.create_text(
            WIDTH * 0.5,
            HEIGHT * 0.57,
            text="Press ENTER to Start",
            fill=THEME["neon_green"],
            font=("Consolas", 24, "bold"),
        )

        self.pause_overlay = c.create_rectangle(
            0, 0, WIDTH, HEIGHT, fill="#05080f", outline="", state="hidden"
        )
        self.pause_title = c.create_text(
            WIDTH * 0.5,
            HEIGHT * 0.44,
            text="PAUSED",
            fill=THEME["neon_orange"],
            font=("Consolas", 48, "bold"),
            state="hidden",
        )
        self.pause_sub = c.create_text(
            WIDTH * 0.5,
            HEIGHT * 0.52,
            text="Press ESC to resume",
            fill=THEME["text"],
            font=("Consolas", 18),
            state="hidden",
        )

        self.end_overlay = c.create_rectangle(0, 0, WIDTH, HEIGHT, fill="#060a12", outline="", state="hidden")
        self.end_title = c.create_text(
            WIDTH * 0.5,
            HEIGHT * 0.42,
            text="",
            fill=THEME["neon_red"],
            font=("Consolas", 50, "bold"),
            state="hidden",
        )
        self.end_score = c.create_text(
            WIDTH * 0.5,
            HEIGHT * 0.51,
            text="",
            fill=THEME["text"],
            font=("Consolas", 20),
            state="hidden",
        )
        self.restart_btn = c.create_rectangle(
            WIDTH * 0.5 - 140,
            HEIGHT * 0.58 - 28,
            WIDTH * 0.5 + 140,
            HEIGHT * 0.58 + 28,
            fill="#0f1a2f",
            outline=THEME["neon_cyan"],
            width=3,
            state="hidden",
        )
        self.restart_text = c.create_text(
            WIDTH * 0.5,
            HEIGHT * 0.58,
            text="RESTART",
            fill=THEME["neon_cyan"],
            font=("Consolas", 22, "bold"),
            state="hidden",
        )

    def update_hud(self, dt: float) -> None:
        p = self.game.player
        hp_ratio = p.hp / p.max_hp if p.max_hp > 0 else 0
        self.game.canvas.coords(self.hp_fg, 32, 40, 32 + 300 * hp_ratio, 60)
        hp_color = (
            THEME["neon_green"]
            if hp_ratio > 0.55
            else THEME["neon_orange"]
            if hp_ratio > 0.28
            else THEME["neon_red"]
        )
        self.game.canvas.itemconfig(self.hp_fg, fill=hp_color)
        self.game.canvas.itemconfig(self.hp_text, text=f"HP: {int(max(0, p.hp))}/{int(p.max_hp)}")

        self.game.canvas.itemconfig(self.score_text, text=f"SCORE: {self.game.score}")
        self.game.canvas.itemconfig(
            self.wave_text,
            text=f"WAVE: {self.game.wave_manager.current_wave}/{self.game.wave_manager.max_waves}",
        )
        self.game.canvas.itemconfig(self.fps_text, text=f"FPS: {self.game.smoothed_fps:.0f}")

        if p.combo > 1 and p.combo_timer > 0:
            self.game.canvas.itemconfig(self.combo_text, state="normal", text=f"COMBO x{p.combo}")
            pulse = 1.0 + math.sin(self.game.elapsed_time * 10.0) * 0.25
            self.game.canvas.itemconfig(
                self.combo_text, fill=scale_color(THEME["neon_orange"], 0.85 + pulse * 0.2)
            )
        else:
            self.game.canvas.itemconfig(self.combo_text, state="hidden")

        if self.game.wave_manager.pending_spawns > 0 and self.game.state == "playing":
            self.game.canvas.itemconfig(
                self.message_text,
                state="normal",
                text=f"Incoming: {self.game.wave_manager.pending_spawns}",
                fill=THEME["neon_cyan"],
            )
        elif self.game.state == "playing" and not self.game.enemies:
            self.game.canvas.itemconfig(
                self.message_text, state="normal", text="Wave Cleared", fill=THEME["neon_green"]
            )
        else:
            self.game.canvas.itemconfig(self.message_text, state="hidden")

    def show_menu(self, visible: bool) -> None:
        state = "normal" if visible else "hidden"
        for item in (self.menu_overlay, self.menu_title, self.menu_sub, self.menu_play):
            self.game.canvas.itemconfig(item, state=state)

    def show_pause(self, visible: bool) -> None:
        state = "normal" if visible else "hidden"
        for item in (self.pause_overlay, self.pause_title, self.pause_sub):
            self.game.canvas.itemconfig(item, state=state)

    def show_end(self, visible: bool, victory: bool = False) -> None:
        state = "normal" if visible else "hidden"
        title = "VICTORY" if victory else "GAME OVER"
        title_color = THEME["neon_green"] if victory else THEME["neon_red"]
        self.game.canvas.itemconfig(self.end_title, text=title, fill=title_color)
        self.game.canvas.itemconfig(self.end_score, text=f"Final Score: {self.game.score}")
        for item in (
            self.end_overlay,
            self.end_title,
            self.end_score,
            self.restart_btn,
            self.restart_text,
        ):
            self.game.canvas.itemconfig(item, state=state)

    def point_in_restart(self, x: float, y: float) -> bool:
        x1, y1, x2, y2 = self.game.canvas.coords(self.restart_btn)
        return x1 <= x <= x2 and y1 <= y <= y2


class Game:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Neon Box Fighter")
        self.root.geometry(f"{WIDTH}x{HEIGHT}")
        self.root.configure(bg=THEME["bg"])
        self.root.resizable(False, False)

        self.canvas = tk.Canvas(
            self.root, width=WIDTH, height=HEIGHT, bg=THEME["bg"], highlightthickness=0, bd=0
        )
        self.canvas.pack()

        self.keys_down: set[str] = set()
        self.state = "menu"

        self.enemies: list[Enemy] = []
        self.particles: list[Particle] = []

        self.player = Player(self, WIDTH * 0.5, HEIGHT * 0.5)
        self.wave_manager = WaveManager(self)
        self.ui = UI(self)

        self.score = 0
        self.elapsed_time = 0.0

        self.camera_x = 0.0
        self.camera_y = 0.0
        self.shake_time = 0.0
        self.shake_strength = 0.0

        self.last_time = time.perf_counter()
        self.smoothed_fps = 0.0

        self.transition_flash = 0.0
        self.transition_color = THEME["neon_cyan"]

        self.background_items = []
        self.grid_items = []
        self.star_items = []
        self._create_background()

        self.canvas.bind("<Button-1>", self.on_click)
        self.root.bind("<KeyPress>", self.on_key_press)
        self.root.bind("<KeyRelease>", self.on_key_release)

        self.root.focus_set()
        self.set_state("menu")

    def _create_background(self) -> None:
        self.base_bg = self.canvas.create_rectangle(0, 0, WIDTH, HEIGHT, fill=THEME["bg"], outline="")

        # Layered atmospheric strips create a subtle sci-fi gradient feeling.
        self.gradient_layers = []
        layer_count = 20
        for i in range(layer_count):
            y1 = i * (HEIGHT / layer_count)
            y2 = (i + 1) * (HEIGHT / layer_count)
            c = rgb_to_hex((5 + i * 2, 8 + i * 3, 15 + i * 4))
            rid = self.canvas.create_rectangle(0, y1, WIDTH, y2 + 1, fill=c, outline="")
            self.gradient_layers.append(rid)

        spacing = 64
        for x in range(0, WIDTH + spacing, spacing):
            lid = self.canvas.create_line(x, 0, x, HEIGHT, fill=THEME["grid"], width=1)
            self.grid_items.append((lid, "v", x))
        for y in range(0, HEIGHT + spacing, spacing):
            lid = self.canvas.create_line(0, y, WIDTH, y, fill=THEME["grid"], width=1)
            self.grid_items.append((lid, "h", y))

        for _ in range(70):
            sx = random.uniform(0, WIDTH)
            sy = random.uniform(0, HEIGHT)
            size = random.uniform(1.0, 2.5)
            speed = random.uniform(6.0, 20.0)
            sid = self.canvas.create_oval(sx, sy, sx + size, sy + size, fill="#1d3a5e", outline="")
            self.star_items.append([sid, sx, sy, size, speed])

        self.vignette_top = self.canvas.create_rectangle(0, 0, WIDTH, 80, fill="#03050a", outline="")
        self.vignette_bot = self.canvas.create_rectangle(
            0, HEIGHT - 90, WIDTH, HEIGHT, fill="#03050a", outline=""
        )

    def set_state(self, new_state: str) -> None:
        self.state = new_state
        self.transition_flash = 0.22
        self.transition_color = {
            "menu": THEME["neon_cyan"],
            "playing": THEME["neon_green"],
            "paused": THEME["neon_orange"],
            "game_over": THEME["neon_red"],
            "victory": THEME["neon_green"],
        }.get(new_state, THEME["neon_cyan"])

        self.ui.show_menu(new_state == "menu")
        self.ui.show_pause(new_state == "paused")
        self.ui.show_end(new_state in ("game_over", "victory"), victory=(new_state == "victory"))

    def start_game(self) -> None:
        self.clear_entities()
        self.score = 0
        self.elapsed_time = 0.0
        self.shake_time = 0.0
        self.shake_strength = 0.0
        self.player.reset(WIDTH * 0.5, HEIGHT * 0.5)
        self.wave_manager.reset()
        self.set_state("playing")

    def clear_entities(self) -> None:
        for enemy in self.enemies:
            enemy.destroy()
        self.enemies.clear()

        for particle in self.particles:
            particle.destroy()
        self.particles.clear()

    def spawn_particle(
        self, x: float, y: float, vx: float, vy: float, size: float, life: float, color: str, kind: str = "circle"
    ) -> None:
        if len(self.particles) >= 520:
            old = self.particles.pop(0)
            old.destroy()
        self.particles.append(Particle(self, x, y, vx, vy, size, life, color, kind=kind))

    def hit_spark(self, x: float, y: float, color: str, count: int) -> None:
        for _ in range(count):
            ang = random.uniform(0.0, math.tau)
            spd = random.uniform(130.0, 440.0)
            self.spawn_particle(
                x,
                y,
                math.cos(ang) * spd,
                math.sin(ang) * spd,
                random.uniform(1.5, 3.6),
                random.uniform(0.16, 0.35),
                color,
            )

    def add_shake(self, amount: float, duration: float) -> None:
        self.shake_strength = max(self.shake_strength, amount)
        self.shake_time = max(self.shake_time, duration)

    def play_hit_sound(self, critical: bool = False) -> None:
        def _play():
            if winsound is not None:
                try:
                    freq = 980 if critical else 660
                    dur = 42 if critical else 28
                    winsound.Beep(freq, dur)
                    return
                except Exception:
                    pass
            try:
                self.root.bell()
            except Exception:
                pass

        threading.Thread(target=_play, daemon=True).start()

    def on_click(self, event) -> None:
        if self.state in ("game_over", "victory") and self.ui.point_in_restart(event.x, event.y):
            self.start_game()

    def on_key_press(self, event) -> None:
        key = event.keysym.lower()

        if key not in self.keys_down:
            self.keys_down.add(key)

            if key == "escape":
                if self.state == "playing":
                    self.set_state("paused")
                elif self.state == "paused":
                    self.set_state("playing")

            elif key == "space" and self.state == "playing":
                self.player.trigger_attack(self.enemies)

            elif key in ("shift_l", "shift_r") and self.state == "playing":
                self.player.trigger_dash(self.keys_down)

            elif key == "return":
                if self.state == "menu":
                    self.start_game()
                elif self.state in ("game_over", "victory"):
                    self.start_game()

            elif key == "r" and self.state in ("game_over", "victory"):
                self.start_game()

    def on_key_release(self, event) -> None:
        key = event.keysym.lower()
        if key in self.keys_down:
            self.keys_down.remove(key)

    def resolve_enemy_overlaps(self) -> None:
        enemies = self.enemies
        n = len(enemies)
        for i in range(n):
            a = enemies[i]
            if not a.alive:
                continue
            for j in range(i + 1, n):
                b = enemies[j]
                if not b.alive:
                    continue

                dx = b.x - a.x
                dy = b.y - a.y
                nx, ny, dist = normalize(dx, dy)
                min_dist = (a.size + b.size) * 0.5

                if dist <= 0.0001:
                    nx, ny = random.uniform(-1, 1), random.uniform(-1, 1)
                    nx, ny, _ = normalize(nx, ny)
                    dist = 0.01

                if dist < min_dist:
                    overlap = (min_dist - dist) * 0.5
                    a.x -= nx * overlap
                    a.y -= ny * overlap
                    b.x += nx * overlap
                    b.y += ny * overlap

    def update_camera(self, dt: float) -> None:
        if self.shake_time > 0.0:
            self.shake_time -= dt
            decay = clamp(self.shake_time * 6.0, 0.0, 1.0)
            strength = self.shake_strength * decay
            self.camera_x = random.uniform(-strength, strength)
            self.camera_y = random.uniform(-strength, strength)
            self.shake_strength = max(0.0, self.shake_strength - dt * 18.0)
        else:
            self.camera_x = 0.0
            self.camera_y = 0.0
            self.shake_strength = 0.0

    def update_background(self, dt: float) -> None:
        t = self.elapsed_time

        for rid_i, rid in enumerate(self.gradient_layers):
            bright = 1.0 + math.sin(t * 0.5 + rid_i * 0.35) * 0.05
            base = (5 + rid_i * 2, 8 + rid_i * 3, 15 + rid_i * 4)
            color = rgb_to_hex(
                (
                    int(clamp(base[0] * bright, 0, 255)),
                    int(clamp(base[1] * bright, 0, 255)),
                    int(clamp(base[2] * bright, 0, 255)),
                )
            )
            self.canvas.itemconfig(rid, fill=color)

        for line_id, mode, base in self.grid_items:
            if mode == "v":
                offset = math.sin(t * 0.7 + base * 0.01) * 8.0
                x = base + offset
                self.canvas.coords(line_id, x + self.camera_x * 0.2, 0, x + self.camera_x * 0.2, HEIGHT)
            else:
                offset = math.cos(t * 0.7 + base * 0.01) * 8.0
                y = base + offset
                self.canvas.coords(line_id, 0, y + self.camera_y * 0.2, WIDTH, y + self.camera_y * 0.2)

        grid_color = scale_color(THEME["grid"], 0.7 + math.sin(t * 0.8) * 0.15 + 0.2)
        for line_id, _, _ in self.grid_items:
            self.canvas.itemconfig(line_id, fill=grid_color)

        for star in self.star_items:
            sid, sx, sy, size, speed = star
            sy += speed * dt
            sx += math.sin(t * speed * 0.02) * dt * 10.0
            if sy > HEIGHT + 10:
                sy = -10
                sx = random.uniform(0, WIDTH)
            star[1], star[2] = sx, sy
            self.canvas.coords(
                sid,
                sx + self.camera_x * 0.1,
                sy + self.camera_y * 0.1,
                sx + size + self.camera_x * 0.1,
                sy + size + self.camera_y * 0.1,
            )

    def update(self, dt: float) -> None:
        self.elapsed_time += dt
        self.update_background(dt)

        if self.transition_flash > 0.0:
            self.transition_flash -= dt

        if self.state == "menu":
            pulse = 1.0 + math.sin(self.elapsed_time * 4.0) * 0.12
            self.canvas.itemconfig(self.ui.menu_play, fill=scale_color(THEME["neon_green"], 0.9 + pulse * 0.2))
            return

        if self.state == "paused":
            pulse = 1.0 + math.sin(self.elapsed_time * 3.0) * 0.12
            self.canvas.itemconfig(
                self.ui.pause_title, fill=scale_color(THEME["neon_orange"], 0.9 + pulse * 0.25)
            )
            return

        if self.state in ("game_over", "victory"):
            pulse = 1.0 + math.sin(self.elapsed_time * 2.5) * 0.1
            self.canvas.itemconfig(self.ui.restart_text, fill=scale_color(THEME["neon_cyan"], 0.9 + pulse * 0.2))
            self.canvas.itemconfig(self.ui.restart_btn, outline=scale_color(THEME["neon_cyan"], 0.85 + pulse * 0.3))
            return

        self.player.update(dt, self.keys_down)

        for enemy in self.enemies:
            enemy.update(dt, self.player, self.enemies)

        self.resolve_enemy_overlaps()

        # Remove defeated enemies after they flashed for feedback.
        alive_enemies = []
        for enemy in self.enemies:
            if enemy.alive or enemy.flash > 0.0:
                alive_enemies.append(enemy)
            else:
                enemy.destroy()
        self.enemies = alive_enemies

        self.wave_manager.update(dt)

        new_particles = []
        for p in self.particles:
            if p.update(dt):
                new_particles.append(p)
            else:
                p.destroy()
        self.particles = new_particles

        self.update_camera(dt)

    def render(self) -> None:
        t = self.elapsed_time

        self.player.draw(self.camera_x, self.camera_y, t)

        for enemy in self.enemies:
            enemy.draw(self.camera_x, self.camera_y, t)

        for p in self.particles:
            p.draw(self.camera_x, self.camera_y)

        self.ui.update_hud(FRAME_MS / 1000.0)

        if self.transition_flash > 0.0:
            amount = clamp(self.transition_flash / 0.22, 0.0, 1.0)
            color = scale_color(self.transition_color, 0.35 + amount * 0.65)
            if not hasattr(self, "flash_rect"):
                self.flash_rect = self.canvas.create_rectangle(0, 0, WIDTH, HEIGHT, fill=color, outline="")
            self.canvas.itemconfig(self.flash_rect, state="normal", fill=color)
            self.canvas.tag_raise(self.flash_rect)
        else:
            if hasattr(self, "flash_rect"):
                self.canvas.itemconfig(self.flash_rect, state="hidden")

        # Keep HUD and overlays always on top.
        for item in (
            self.ui.hud_panel,
            self.ui.hp_bg,
            self.ui.hp_fg,
            self.ui.hp_text,
            self.ui.score_text,
            self.ui.wave_text,
            self.ui.fps_text,
            self.ui.combo_text,
            self.ui.message_text,
            self.ui.menu_overlay,
            self.ui.menu_title,
            self.ui.menu_sub,
            self.ui.menu_play,
            self.ui.pause_overlay,
            self.ui.pause_title,
            self.ui.pause_sub,
            self.ui.end_overlay,
            self.ui.end_title,
            self.ui.end_score,
            self.ui.restart_btn,
            self.ui.restart_text,
        ):
            self.canvas.tag_raise(item)

    def game_loop(self) -> None:
        now = time.perf_counter()
        dt = now - self.last_time
        self.last_time = now
        dt = clamp(dt, 0.0, MAX_DT)

        fps = 1.0 / dt if dt > 0 else TARGET_FPS
        self.smoothed_fps = fps if self.smoothed_fps == 0 else lerp(self.smoothed_fps, fps, 0.08)

        self.update(dt)
        self.render()

        self.root.after(FRAME_MS, self.game_loop)

    def run(self) -> None:
        self.last_time = time.perf_counter()
        self.root.after(FRAME_MS, self.game_loop)
        self.root.mainloop()


if __name__ == "__main__":
    Game().run()
