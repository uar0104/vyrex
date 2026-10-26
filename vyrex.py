import heapq
import json
import math
import os
import random
import sys
from array import array

import pygame

if "ANDROID_ARGUMENT" in os.environ or "ANDROID_ROOT" in os.environ:
    os.environ["SDL_ORIENTATIONS"] = "LandscapeLeft LandscapeRight"
try:
    pygame.mixer.pre_init(22050, -16, 1, 512)
except Exception:
    pass
pygame.init()

# ---------------------------------------------------------------- setup
LW, LH = 800, 450
ANDROID = "ANDROID_ARGUMENT" in os.environ or "ANDROID_ROOT" in os.environ
if ANDROID:
    win = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
else:
    win = pygame.display.set_mode((LW, LH), pygame.RESIZABLE)
GAME_NAME = "VYREX"
pygame.display.set_caption(GAME_NAME)
view = pygame.Surface((LW, LH))
clock = pygame.time.Clock()
font = pygame.font.Font(None, 30)
small = pygame.font.Font(None, 22)
big = pygame.font.Font(None, 72)
huge = pygame.font.Font(None, 118)
GOLD = (242, 193, 78)
DARK = (31, 41, 51)
# If the screen stays portrait the game is rotated; flip to 90 if upside down
PORTRAIT_ROTATE = -90

TW, TH, HZ = 64, 32, 22  # tile width, tile height, height of one level

# ---------------------------------------------------------------- audio
SR, CH = 22050, 1
AUDIO = False
MUTED = False
SND = {}
MUSIC = None
try:
    _init = pygame.mixer.get_init()
    if _init and _init[1] == -16:
        SR, CH = int(_init[0]), int(_init[2])
        AUDIO = True
except Exception:
    AUDIO = False


def to_sound(samples):
    buf = array("h")
    for v in samples:
        v = int(max(-0.95, min(0.95, v)) * 32767)
        for _ in range(CH):
            buf.append(v)
    return pygame.mixer.Sound(buffer=buf.tobytes())


def tone_seq(parts):
    out = []
    for f0, f1, dur, vol, wave in parts:
        n = max(1, int(dur * SR))
        ph = 0.0
        for i in range(n):
            t = i / n
            ph += (f0 + (f1 - f0) * t) / SR
            ph -= int(ph)
            if wave == "sq":
                v = 1.0 if ph < 0.5 else -1.0
            elif wave == "sin":
                v = math.sin(6.2832 * ph)
            else:
                v = random.uniform(-1, 1)
            out.append(v * vol * (1 - t) ** 1.3)
    return out


def gen_music():
    beat = 0.5
    n_total = int(16 * beat * SR)
    track = [0.0] * n_total

    def note(freq, start, beats, vol, duty):
        s = int(start * beat * SR)
        n = int(beats * beat * SR * 0.9)
        step, ph = freq / SR, 0.0
        for i in range(n):
            if s + i >= n_total:
                break
            ph += step
            if ph >= 1.0:
                ph -= 1.0
            env = 1.0 - 0.6 * i / n
            if i < 40:
                env *= i / 40
            track[s + i] += (1.0 if ph < duty else -1.0) * vol * env

    E5, D5, C5, A4, G4, E4 = 659.25, 587.33, 523.25, 440.0, 392.0, 329.63
    lead = [(E5, .5), (D5, .5), (C5, .5), (A4, .5), (C5, 1), (D5, 1),
            (E5, .5), (G4, .5), (A4, 1), (C5, .5), (A4, .5), (G4, 1),
            (D5, .5), (C5, .5), (A4, .5), (G4, .5), (A4, 1), (E4, 1),
            (G4, .5), (A4, .5), (C5, .5), (D5, .5), (E5, 2)]
    pos = 0.0
    for f, b in lead:
        note(f, pos, b, 0.13, 0.5)
        pos += b
    bass = [110, 110, 82.4, 110, 87.3, 87.3, 130.8, 87.3,
            98, 98, 146.8, 98, 110, 110, 82.4, 82.4]
    for i, f in enumerate(bass):
        note(f, i, 1, 0.16, 0.25)
    hat = int(0.03 * SR)
    for k in range(32):
        s = int(k * 0.5 * beat * SR)
        for i in range(hat):
            if s + i < n_total:
                track[s + i] += random.uniform(-1, 1) * 0.05 * (1 - i / hat)
    return to_sound(track)


def init_audio():
    global MUSIC, AUDIO
    if not AUDIO:
        return
    try:
        SND["hop"] = to_sound(tone_seq([(330, 520, 0.07, 0.25, "sq")]))
        SND["leap"] = to_sound(tone_seq([(300, 900, 0.16, 0.25, "sq")]))
        SND["coin"] = to_sound(tone_seq([(988, 988, 0.06, 0.22, "sq"),
                                         (1319, 1319, 0.14, 0.22, "sq")]))
        SND["hurt"] = to_sound(tone_seq([(300, 80, 0.3, 0.35, "sq"),
                                         (0, 0, 0.12, 0.2, "noise")]))
        SND["clear"] = to_sound(tone_seq([(523, 523, 0.1, 0.25, "sq"),
                                          (659, 659, 0.1, 0.25, "sq"),
                                          (784, 784, 0.1, 0.25, "sq"),
                                          (1047, 1047, 0.35, 0.25, "sq")]))
        SND["click"] = to_sound(tone_seq([(700, 700, 0.04, 0.2, "sq")]))
        MUSIC = gen_music()
        MUSIC.set_volume(0.0 if MUTED else 0.35)
        MUSIC.play(-1)
    except Exception:
        AUDIO = False


def sfx(name):
    if AUDIO and not MUTED and name in SND:
        try:
            SND[name].play()
        except Exception:
            pass


def toggle_mute():
    global MUTED
    MUTED = not MUTED
    if AUDIO and MUSIC is not None:
        try:
            MUSIC.set_volume(0.0 if MUTED else 0.35)
        except Exception:
            pass


# ---------------------------------------------------------------- sprites
def make_sprite(rows, pal, scale):
    h, w = len(rows), len(rows[0])
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in pal:
                s.set_at((x, y), pal[ch])
    return pygame.transform.scale(s, (w * scale, h * scale))


ROBOT = [
    ".......CC.......",
    ".......OO.......",
    "...OOOOOOOOOO...",
    "...OGGGGGGGGO...",
    "..COGVVVVVVGOC..",
    "..COGVEVVEVGOC..",
    "...OGVVVVVVGO...",
    "...OGGGGGGGGO...",
    "...OGGOOOOGGO...",
    "...OOOOOOOOOO...",
    "....OOOOOOOO....",
    ".OGGOGGCCGGOGGO.",
    ".OGGOGGCCGGOGGO.",
    "..CCOOOOOOOOCC..",
    "....OGGOOGGO....",
    "...OOOO..OOOO...",
]
ROBOT_PAL = {
    "O": (31, 41, 51), "G": (184, 194, 204), "C": (217, 119, 87),
    "V": (11, 22, 32), "E": (92, 225, 230),
}
ENEMY = [
    "..O..O..",
    "...OO...",
    "..PPPP..",
    ".PPPPPP.",
    "PPWPPWPP",
    "PPKPPKPP",
    ".PPPPPP.",
    ".P.PP.P.",
]
ENEMY_PAL = {
    "O": (31, 41, 51), "P": (155, 93, 229), "W": (255, 255, 255),
    "K": (31, 41, 51),
}
SPR_R = make_sprite(ROBOT, ROBOT_PAL, 3)
SPR_L = pygame.transform.flip(SPR_R, True, False)
SPR_E = make_sprite(ENEMY, ENEMY_PAL, 4)

GAME_NAME_PLACEHOLDER = None
_BODY = ROBOT[10:]
CAT_HEAD = ["...OO......OO...", "..OGGO....OGGO..", "..OGGGOOOOGGGO..", "..OGGGGGGGGGGO..",
            "..OGVVGGGGVVGO..", "..OGVEGGGGEVGO..", "..OGGGGCCGGGGO..", "..OGGGGOOGGGGO..",
            "...OGGGGGGGGO...", "....OOOOOOOO...."]
ALIEN_HEAD = ["...E........E...", "....O......O....", "...OOOOOOOOOO...", "..OGGGGGGGGGGO..",
              "..OGGVVGGVVGGO..", "..OGGVEGGEVGGO..", "..OGGVVGGVVGGO..", "..OGGGGGGGGGGO..",
              "...OGGGOOGGGO...", "....OOOOOOOO...."]
NINJA_HEAD = ["................", "....OOOOOOOO....", "...OGGGGGGGGO...", "..OCCCCCCCCCCO..",
              "..OGGGGGGGGGGO..", "..OGVVEGGEVVGO..", "..OGVVVVVVVVGO..", "..OGGGGGGGGGGO..",
              "...OGGGGGGGGO...", "....OOOOOOOO...."]
CHARS = [
    {"name": "Robo", "rows": ROBOT, "pal": ROBOT_PAL, "unlock": 0},
    {"name": "Kitty", "rows": CAT_HEAD + _BODY, "unlock": 5,
     "pal": {"O": (60, 36, 24), "G": (240, 160, 70), "C": (255, 235, 200),
             "V": (40, 30, 30), "E": (120, 240, 150)}},
    {"name": "Alien", "rows": ALIEN_HEAD + _BODY, "unlock": 10,
     "pal": {"O": (20, 50, 30), "G": (120, 220, 120), "C": (250, 120, 200),
             "V": (20, 30, 40), "E": (255, 255, 120)}},
    {"name": "Ninja", "rows": NINJA_HEAD + _BODY, "unlock": 20,
     "pal": {"O": (10, 10, 20), "G": (52, 58, 84), "C": (230, 70, 70),
             "V": (10, 14, 24), "E": (255, 255, 255)}},
]
_CS = {}


def char_sprite(i, scale=3, flip=False, dark=False):
    key = (i, scale, flip, dark)
    if key not in _CS:
        c = CHARS[i]
        pal = {k: (30, 36, 50) for k in c["pal"]} if dark else c["pal"]
        spr = make_sprite(c["rows"], pal, scale)
        _CS[key] = pygame.transform.flip(spr, True, False) if flip else spr
    return _CS[key]


SLIME = ["........", "..OOOO..", ".OGGGGO.", "OGWKGWKO", "OGGGGGGO", "OGGGGGGO", "OOGGGGOO", ".OOOOOO."]
SPIDER = ["O..OO..O", ".O.RR.O.", "..RRRR..", "ORWRRWRO", "..RRRR..", ".O.RR.O.", "O..OO..O", "........"]
GHOST = ["..BBBB..", ".BBBBBB.", "BBWKBWKB", "BBWKBWKB", "BBBBBBBB", "BBBBBBBB", "BBBBBBBB", "B.BB.BB."]
SKINS = {
    "bug": SPR_E,
    "slime": make_sprite(SLIME, {"O": (31, 41, 51), "G": (90, 200, 110), "W": (255, 255, 255), "K": (31, 41, 51)}, 4),
    "spider": make_sprite(SPIDER, {"O": (31, 41, 51), "R": (200, 70, 70), "W": (255, 255, 255)}, 4),
    "ghost": make_sprite(GHOST, {"B": (150, 170, 255), "W": (255, 255, 255), "K": (31, 41, 51)}, 4),
}

# ---------------------------------------------------------------- levels
# . void | 1 2 3 tile height | S start | G goal | c C D coin on height 1/2/3
# ^ spikes | e enemy patrolling along x | v enemy patrolling along y
# The first levels are hand made; from level 5 on they are generated
# (and verified solvable by a built-in solver), so the game never ends.
HAND = [
    # 1: first steps
    ["S1c1.",
     "..1..",
     ".c1c.",
     "..1..",
     "..1G."],
    # 2: heights
    ["S12D21",
     "1...1.",
     "cc2.1G"],
    # 3: spikes
    ["S1^1^G",
     "c.1.c.",
     "1c1c1."],
    # 4: enemy
    ["S1c1c1",
     "1.1.1.",
     "c11e1c",
     "1.1.1.",
     "c1c11G"],
]
LEVELS = [
    ["S1c1.",
     "..1..",
     ".c1c.",
     "..1..",
     "..1G."],
    ["S12D21",
     "1...1.",
     "cc2.1G"],
    ["S1^1^G",
     "c.1.c.",
     "1c1c1."],
    ["S1c1c1",
     "1.1.1.",
     "c11e1c",
     "1.1.1.",
     "c1c11G"],
    ["S1c1c1G",
     "1.c1c.1",
     "11cvc11",
     "1.c1c.1",
     "c1c1c1c"],
    ["S1c1^1c1",
     "1.1.1.1.",
     "c1e1^11c",
     "1.1.1.1.",
     "c11e12cG"],
    ["S12D21c",
     "1.2.1.1",
     "c^2D2^c",
     "1.2.1.1",
     "c12c21G"],
    ["S1c1c1.",
     "1.1.1.1",
     "c1e11c1",
     "1.1.1.1",
     "c1c11e1",
     "..1.1.G"],
    ["S12D21^G",
     "1.1.1.1.",
     "c1e1^1c1",
     "1.1.1.1.",
     "c1^1c1^1"],
    ["S1c2D2c1.",
     "1.1.1.1.",
     "c1e1^1c1",
     "1.1.1.1.",
     "c1^1v1^1",
     "..1.1.cG"],
]
HINTS = {0: "h0", 1: "h1", 2: "h2", 3: "h3"}
MENU_ROWS = ["11111",
             "11211",
             "12S21",
             "11211",
             "11111"]
DIRS = {"UL": (-1, 0), "UR": (0, -1), "DL": (0, 1), "DR": (1, 0)}
VEC = {"UL": (-1, -1), "UR": (1, -1), "DL": (-1, 1), "DR": (1, 1)}
BTN = {
    "UL": pygame.Rect(12, LH - 164, 72, 72),
    "UR": pygame.Rect(92, LH - 164, 72, 72),
    "DL": pygame.Rect(12, LH - 84, 72, 72),
    "DR": pygame.Rect(92, LH - 84, 72, 72),
    "LEAP": pygame.Rect(LW - 132, LH - 132, 108, 108),
}


# ---------------------------------------------------------------- generator
D4 = [(-1, 0), (0, -1), (0, 1), (1, 0)]


def _links(T, t):
    for dx, dy in D4:
        n = (t[0] + dx, t[1] + dy)
        if n in T:
            yield n
        else:
            m = (t[0] + 2 * dx, t[1] + 2 * dy)
            if m in T:
                yield m


def _relax(T, h):
    changed = True
    while changed:
        changed = False
        for t in T:
            for nb in _links(T, t):
                if h[t] > h[nb] + 1:
                    h[t] = h[nb] + 1
                    changed = True


def _bfs(T, h, start, blocked=(), doors=()):
    dist = {start: 0}
    q = [start]
    i = 0
    while i < len(q):
        c = q[i]
        i += 1
        for dx, dy in D4:
            for k in (1, 2):
                if k == 2 and (c[0] + dx, c[1] + dy) in doors:
                    continue
                n = (c[0] + dx * k, c[1] + dy * k)
                if n in T and n not in blocked and n not in dist \
                        and abs(h[n] - h[c]) <= 1:
                    dist[n] = dist[c] + 1
                    q.append(n)
    return dist


def _validate(T, h, a, b, hazard, doors, keys):
    opened, got = set(), set()
    while True:
        closed = set(doors) - opened
        R = _bfs(T, h, a, hazard | closed, closed)
        got |= {k for k in keys if k in R}
        if b in R:
            return True
        if len(got) - len(opened) <= 0:
            return False
        for d in sorted(closed):
            if any((d[0] + dx * k, d[1] + dy * k) in R
                   and abs(h[d] - h[(d[0] + dx * k, d[1] + dy * k)]) <= 1
                   for dx, dy in D4 for k in (1, 2)):
                opened.add(d)
                break
        else:
            return False


def _rand_path(rng, W, H, a, b):
    cost = {(x, y): 1 + rng.random() * 3 for x in range(W) for y in range(H)}
    dist, prev, pq = {a: 0.0}, {}, [(0.0, a)]
    while pq:
        d, c = heapq.heappop(pq)
        if c == b:
            break
        if d > dist.get(c, 1e9):
            continue
        for dx, dy in D4:
            n = (c[0] + dx, c[1] + dy)
            if 0 <= n[0] < W and 0 <= n[1] < H:
                nd = d + cost[n]
                if nd < dist.get(n, 1e9):
                    dist[n], prev[n] = nd, c
                    heapq.heappush(pq, (nd, n))
    path = [b]
    while path[-1] != a:
        path.append(prev[path[-1]])
    return path[::-1]


def _runs(T, a, b, min_len):
    runs = []
    for axis in (0, 1):
        for t in sorted(T):
            back = (t[0] - (axis == 0), t[1] - (axis == 1))
            if back in T:
                continue
            run, c = [t], t
            while True:
                c = (c[0] + (axis == 0), c[1] + (axis == 1))
                if c not in T:
                    break
                run.append(c)
            if len(run) >= min_len and a not in run and b not in run:
                runs.append((axis, run))
    return runs


def _try_gen(rng, n):
    diff = min(52.0, 6 + (n - 10) * 1.0)
    if diff < 12:
        W, H = rng.choice([6, 7, 7]), rng.choice([4, 5, 5])
    elif diff < 24:
        W, H = rng.choice([7, 8, 8]), rng.choice([5, 5, 6])
    else:
        W, H = rng.choice([8, 9, 9]), rng.choice([5, 6, 6])
    a = (0, rng.randrange(H))
    b = (W - 1, rng.randrange(H))
    pts = [a] + [(rng.randrange(1, W - 1), rng.randrange(H))
                 for _ in range(1 + (diff > 10))] + [b]
    T = {a, b}
    for p, q in zip(pts, pts[1:]):
        if p != q:
            T.update(_rand_path(rng, W, H, p, q))
    target = int(W * H * rng.uniform(0.6, 0.8))
    for _ in range(400):
        if len(T) >= target:
            break
        t = rng.choice(sorted(T))
        dx, dy = rng.choice(D4)
        nb = (t[0] + dx, t[1] + dy)
        if 0 <= nb[0] < W and 0 <= nb[1] < H:
            T.add(nb)
    gaps = int(diff / 9) + (1 if rng.random() < 0.4 else 0)
    for t in rng.sample(sorted(T - {a, b}), min(gaps, len(T) - 2)):
        T.discard(t)
    # gates: a two-column cut with a single door tile in it
    doors, n_g, cols = [], (0 if diff < 8 else (1 if diff < 22 else 2)), []
    for c in rng.sample(range(2, W - 3), len(range(2, W - 3))) if n_g else []:
        if len(cols) < n_g and all(abs(c - o) >= 3 for o in cols):
            cols.append(c)
    for c in sorted(cols):
        rr = [y for y in range(H) if (c - 1, y) in T and (c + 2, y) in T]
        if not rr:
            continue
        r = rng.choice(rr)
        T.update({(c, r), (c + 1, r)})
        for y in range(H):
            if y != r:
                T.discard((c, y))
                T.discard((c + 1, y))
        doors.append((c, r))
    dset = set(doors)
    h = {t: 1 for t in T}
    cap = 3 if diff >= 6 else 2
    for _ in range(rng.randint(1, 2 if diff < 12 else 3)):
        c = rng.choice(sorted(T))
        k = rng.randint(1, cap)
        for t in T:
            v = 1 + max(0, k - abs(t[0] - c[0]) - abs(t[1] - c[1]))
            h[t] = max(h[t], min(cap, v))
    for t in dset | {a, b}:
        h[t] = 1
    _relax(T, h)
    reach = _bfs(T, h, a)
    if b not in reach:
        return None
    T = set(reach)
    doors = [d for d in doors if d in T]
    dset = set(doors)
    h = {t: h[t] for t in T}
    near = dset | {(d[0] + dx, d[1] + dy) for d in doors for dx, dy in D4}
    hazard, enemies = set(), []
    n_en = 0 if diff < 3 else min(5, 1 + int(diff / 8))
    runs = [(ax, rn) for ax, rn in (_runs(T, a, b, 4) or _runs(T, a, b, 3))
            if not (set(rn) & near)]
    rng.shuffle(runs)
    used = set()
    for axis, run in runs:
        if len(enemies) >= n_en:
            break
        if used & set(run):
            continue
        used.update(run)
        enemies.append((rng.choice(run), axis))
        hazard.update(run)
    en_starts = {s for s, _ in enemies}
    cand = [t for t in sorted(T) if t not in (a, b) and t not in en_starts and t not in near]
    n_sp = min(int(diff * 0.35), len(cand) // 4)
    spikes = set(rng.sample(cand, n_sp)) if n_sp > 0 else set()
    c2 = [t for t in cand if t not in spikes and t not in hazard]
    n_f = 0 if diff < 8 else min(4, 1 + int((diff - 8) / 7))
    fires = set(rng.sample(c2, min(n_f, len(c2))))
    c3 = [t for t in c2 if t not in fires]
    n_x = 0 if diff < 5 else min(4, 1 + int((diff - 5) / 8))
    crumbs = set(rng.sample(c3, min(n_x, len(c3))))
    hazard |= spikes | fires
    for t in hazard | crumbs | dset | {a, b}:
        h[t] = 1
    _relax(T, h)
    dist = _bfs(T, h, a, hazard)
    if b not in dist or dist[b] < 5:
        return None
    # keys: each key sits in the region reachable before its gate opens
    keys = []
    avoid = hazard | crumbs | dset | {a, b} | en_starts
    for i in range(len(doors)):
        closed = set(sorted(doors)[i:])
        reg = _bfs(T, h, a, hazard | closed, closed)
        pool = [t for t in sorted(reg) if t not in avoid and t not in keys]
        far = [t for t in pool if abs(t[0] - a[0]) + abs(t[1] - a[1]) >= 3]
        if not (far or pool):
            return None
        keys.append(rng.choice(far or pool))
    for t in keys:
        h[t] = 1
    _relax(T, h)
    chasers = set()
    n_h = 0 if diff < 12 else min(2, 1 + int((diff - 12) / 12))
    if n_h:
        db = _bfs(T, h, b, hazard)
        c4 = [t for t in c3 if t not in crumbs and t not in keys and t in dist and t in db
              and dist[t] + db[t] >= dist[b] + 3
              and abs(t[0] - a[0]) + abs(t[1] - a[1]) >= 4
              and all(abs(t[0] - q[0]) + abs(t[1] - q[1]) >= 4 for q in keys + doors)]
        chasers = set(rng.sample(c4, min(n_h, len(c4))))
        for t in chasers:
            h[t] = 1
        _relax(T, h)
    if not _validate(T, h, a, b, hazard, doors, keys):
        return None
    if b not in _bfs(T, h, a, hazard) or _bfs(T, h, a, hazard)[b] < 5:
        return None
    ccand = [t for t in sorted(T) if t not in (a, b) and t not in spikes
             and t not in fires and t not in en_starts and t not in chasers
             and t not in crumbs and t not in dset and t not in keys]
    coins = set(rng.sample(ccand, min(len(ccand), 3 + int(diff / 4), 12)))
    kinds = dict(enemies)
    rows = []
    for y in range(H):
        row = ""
        for x in range(W):
            t = (x, y)
            if t not in T:
                row += "."
            elif t == a:
                row += "S"
            elif t == b:
                row += "G"
            elif t in dset:
                row += "g"
            elif t in keys:
                row += "k"
            elif t in spikes:
                row += "^"
            elif t in fires:
                row += "f"
            elif t in chasers:
                row += "h"
            elif t in crumbs:
                row += "x"
            elif t in en_starts:
                row += "e" if kinds[t] == 0 else "v"
            elif t in coins:
                row += "cCD"[h[t] - 1]
            else:
                row += str(h[t])
        rows.append(row)
    return rows


def gen_level(n):
    for attempt in range(80):
        rng = random.Random(n * 7919 + attempt * 104729 + 12345)
        rows = _try_gen(rng, n)
        if rows:
            return rows
    return LEVELS[3]


def rows_for(i):
    return LEVELS[i] if i < len(LEVELS) else gen_level(i)


class Level:
    def __init__(self, rows):
        self.tiles, self.coins, self.spikes = {}, set(), set()
        self.fires, self.crumbles, self.chasers = set(), set(), []
        self.keys, self.doors = set(), set()
        self.enemy_defs = []
        self.start = self.goal = (0, 0)
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch == ".":
                    continue
                h = int(ch) if ch.isdigit() else 1
                if ch in "CD":
                    h = 2 if ch == "C" else 3
                if ch in "cCD":
                    self.coins.add((x, y))
                elif ch == "^":
                    self.spikes.add((x, y))
                elif ch == "f":
                    self.fires.add((x, y))
                elif ch == "x":
                    self.crumbles.add((x, y))
                elif ch == "k":
                    self.keys.add((x, y))
                elif ch == "g":
                    self.doors.add((x, y))
                elif ch == "h":
                    self.chasers.append((x, y))
                elif ch == "S":
                    self.start = (x, y)
                elif ch == "G":
                    self.goal = (x, y)
                elif ch in "ev":
                    self.enemy_defs.append((x, y, ch))
                self.tiles[(x, y)] = h
        self.order = sorted(self.tiles, key=lambda k: (k[0] + k[1], k[0]))
        self.maxd = max(x + y for x, y in self.tiles)
        xs, ys = [], []
        for (x, y), h in self.tiles.items():
            sx = (x - y) * TW / 2
            xs += [sx - TW / 2, sx + TW / 2]
            ys += [(x + y) * TH / 2 - h * HZ - TH / 2 - 40,
                   (x + y) * TH / 2 + TH / 2]
        self.bounds = (min(xs), max(xs), min(ys), max(ys))


def proj(x, y, h, ox, oy):
    return ox + (x - y) * TW / 2, oy + (x + y) * TH / 2 - h * HZ


# ---------------------------------------------------------------- themes
THEMES = [
    {"name": "Meadow", "sky": ((70, 130, 215), (190, 225, 245)),
     "tiles": {1: (104, 190, 96), 2: (214, 176, 102), 3: (150, 170, 215)},
     "sun": (255, 244, 190), "cloud": (250, 252, 255), "amb": (255, 255, 255)},
    {"name": "Desert", "sky": ((245, 150, 80), (255, 228, 170)),
     "tiles": {1: (230, 196, 118), 2: (206, 144, 84), 3: (172, 112, 72)},
     "sun": (255, 250, 225), "cloud": (255, 240, 222), "amb": (255, 225, 170)},
    {"name": "Frost", "sky": ((50, 90, 165), (190, 222, 246)),
     "tiles": {1: (205, 232, 246), 2: (150, 200, 236), 3: (112, 160, 222)},
     "sun": (235, 245, 255), "cloud": (240, 248, 255), "amb": (255, 255, 255)},
    {"name": "Volcano", "sky": ((52, 20, 38), (196, 74, 48)),
     "tiles": {1: (126, 104, 104), 2: (168, 74, 62), 3: (226, 114, 52)},
     "sun": (255, 190, 100), "cloud": (120, 70, 80), "amb": (255, 160, 70)},
    {"name": "Night", "sky": ((12, 12, 46), (74, 52, 124)),
     "tiles": {1: (92, 112, 184), 2: (142, 102, 192), 3: (194, 122, 202)},
     "sun": (238, 240, 255), "cloud": (70, 70, 130), "amb": (230, 235, 255)},
]
BGS = {}


def get_bg(w, ti):
    key = (w, ti)
    if key in BGS:
        return BGS[key]
    th = THEMES[ti]
    s = pygame.Surface((w, LH))
    (r0, g0, b0), (r1, g1, b1) = th["sky"]
    for y in range(LH):
        t = y / LH
        pygame.draw.line(s, (int(r0 + (r1 - r0) * t), int(g0 + (g1 - g0) * t),
                             int(b0 + (b1 - b0) * t)), (0, y), (w, y))
    sx, sy = int(w * 0.8), 92
    halo = tuple(int(c * 0.35 + th["sky"][0][i] * 0.65)
                 for i, c in enumerate(th["sun"]))
    pygame.draw.circle(s, halo, (sx, sy), 58)
    pygame.draw.circle(s, th["sun"], (sx, sy), 38)
    if ti == 4:
        pygame.draw.circle(s, th["sky"][0], (sx + 14, sy - 8), 32)
    BGS[key] = s
    return s


def draw_decor(s, ti, cx, cy, k):
    dx = -14 if k == 0 else 12
    px, py = int(cx + dx), int(cy + (1 if k == 0 else 3))
    if ti == 0:
        pygame.draw.line(s, (60, 140, 70), (px, py), (px, py + 5), 2)
        pygame.draw.circle(s, (240, 90, 120) if k == 0 else (252, 222, 90),
                           (px, py), 3)
    elif ti == 1:
        pygame.draw.rect(s, (70, 150, 90), (px, py - 8, 4, 11))
        pygame.draw.rect(s, (70, 150, 90), (px - 3, py - 5, 3, 3))
        pygame.draw.rect(s, (70, 150, 90), (px + 4, py - 7, 3, 3))
    elif ti == 2:
        pygame.draw.circle(s, (255, 255, 255), (px, py), 3)
        pygame.draw.circle(s, (255, 255, 255), (px + 5, py + 2), 2)
    elif ti == 3:
        pygame.draw.line(s, (255, 150, 60), (px - 5, py), (px, py + 2), 2)
        pygame.draw.line(s, (255, 190, 90), (px, py + 2), (px + 5, py - 1), 2)
    else:
        pygame.draw.circle(s, (230, 235, 255), (px, py), 2)
        pygame.draw.line(s, (200, 210, 255), (px - 4, py), (px + 4, py), 1)


# ---------------------------------------------------------------- entities
class Robot:
    def __init__(self, lv):
        self.tx, self.ty = lv.start
        self.x, self.y = float(self.tx), float(self.ty)
        self.h = float(lv.tiles[lv.start])
        self.fx, self.fy = 1, 0
        self.mv = None
        self.lift = 0.0
        self.leap = False
        self.inv = 0
        self.shield = 0
        self.squash = 0

    def safe(self):
        return self.inv > 0 or self.shield > 0

    def start(self, lv, dx, dy, dist, fast=False):
        self.fx, self.fy = dx, dy
        ex, ey = self.tx + dx * dist, self.ty + dy * dist
        if (ex, ey) not in lv.tiles:
            return False
        h0, h1 = lv.tiles[(self.tx, self.ty)], lv.tiles[(ex, ey)]
        if abs(h1 - h0) > 1:
            return False
        self.leap = dist == 2
        dur = (12 if fast else 17) if self.leap else (6 if fast else 9)
        self.mv = [self.tx, self.ty, h0, ex, ey, h1, 0, dur, 36 if self.leap else 14]
        return True

    def update(self):
        if self.squash:
            self.squash -= 1
        m = self.mv
        if not m:
            return False
        m[6] += 1
        t = m[6] / m[7]
        if t >= 1:
            self.tx, self.ty = m[3], m[4]
            self.x, self.y, self.h = float(m[3]), float(m[4]), float(m[5])
            self.mv, self.lift, self.leap = None, 0.0, False
            self.squash = 7
            return True
        e = t * t * (3 - 2 * t)
        self.x = m[0] + (m[3] - m[0]) * e
        self.y = m[1] + (m[4] - m[1]) * e
        self.h = m[2] + (m[5] - m[2]) * e
        self.lift = math.sin(math.pi * t) * m[8]
        return False

    def airborne(self):
        if not (self.mv and self.leap):
            return False
        return 0.2 < self.mv[6] / self.mv[7] < 0.8


class Enemy:
    def __init__(self, x, y, kind, lv, d, skin="bug"):
        self.chase = kind == "h"
        self.skin = "ghost" if self.chase else skin
        self.ax, self.ay = (0, 1) if kind == "v" else (1, 0)
        self.tx, self.ty = x, y
        self.x, self.y = float(x), float(y)
        self.h = float(lv.tiles[(x, y)])
        self.d, self.t = d, 0
        self.nx, self.ny = x, y
        if not self.chase:
            self.pick(lv)

    def pick(self, lv):
        for d in (self.d, -self.d):
            nx, ny = self.tx + self.ax * d, self.ty + self.ay * d
            if (nx, ny) in lv.tiles and \
                    lv.tiles[(nx, ny)] == lv.tiles.get((self.tx, self.ty), 1):
                self.d, self.nx, self.ny = d, nx, ny
                return
        self.nx, self.ny = self.tx, self.ty

    def arrive(self, lv):
        self.tx, self.ty, self.t = self.nx, self.ny, 0
        self.x, self.y = float(self.tx), float(self.ty)
        self.h = float(lv.tiles.get((self.tx, self.ty), 1))

    def update(self, lv, rb, frozen=False):
        if frozen:
            return
        self.t += 1
        if self.chase:
            if (self.nx, self.ny) != (self.tx, self.ty):
                k = min(1.0, self.t / 24)
                self.x = self.tx + (self.nx - self.tx) * k
                self.y = self.ty + (self.ny - self.ty) * k
                if self.t >= 24:
                    self.arrive(lv)
            elif self.t >= 36:
                cur = abs(rb.tx - self.tx) + abs(rb.ty - self.ty)
                best = None
                if cur <= 5:
                    h0 = lv.tiles.get((self.tx, self.ty), 1)
                    for dx, dy in D4:
                        n = (self.tx + dx, self.ty + dy)
                        if n in lv.tiles and abs(lv.tiles[n] - h0) <= 1:
                            dd = abs(rb.tx - n[0]) + abs(rb.ty - n[1])
                            if dd < cur and (best is None or dd < best[0]):
                                best = (dd, n)
                if best:
                    self.nx, self.ny = best[1]
                    self.t = 0
            return
        k = min(1.0, self.t / 28)
        self.x = self.tx + (self.nx - self.tx) * k
        self.y = self.ty + (self.ny - self.ty) * k
        if self.t >= 28:
            self.arrive(lv)
            self.pick(lv)


# ---------------------------------------------------------------- UI helpers
mid = pygame.font.Font(None, 42)
CORAL, BLUE, GREEN, RED = (217, 119, 87), (74, 111, 165), (76, 168, 108), (200, 84, 90)
_CACHE = {}


# ---------------------------------------------------------------- language
import unicodedata

LANG = "en"
STR = {
    "tagline": ("an endless puzzle adventure", "ماجراجویی معمایی بی‌پایان"),
    "play": ("PLAY", "شروع بازی"), "continue": ("CONTINUE", "ادامه"),
    "levels": ("LEVELS", "مرحله‌ها"), "hero": ("HERO", "قهرمان"),
    "newgame": ("NEW GAME", "بازی جدید"),
    "level_n": ("Level %d", "مرحله %d"), "select_title": ("Select level", "انتخاب مرحله"),
    "world": ("World %d - %s", "دنیای %d - %s"),
    "w_Meadow": ("Meadow", "چمنزار"), "w_Desert": ("Desert", "بیابان"), "w_Frost": ("Frost", "یخبندان"),
    "w_Volcano": ("Volcano", "آتشفشان"), "w_Night": ("Night", "شب"),
    "choose_hero": ("Choose your hero", "قهرمانت را انتخاب کن"),
    "selected": ("SELECTED", "انتخاب شده"), "tap_pick": ("Tap to pick", "برای انتخاب لمس کن"),
    "clear_n": ("Clear %d levels", "%d مرحله را تمام کن"),
    "confirm_title": ("Start a new game?", "بازی جدید شروع شود؟"),
    "confirm_sub": ("Your saved progress will be erased.", "پیشرفت ذخیره‌شده‌ات پاک می‌شود."),
    "yes_reset": ("YES, RESET", "بله، پاک کن"), "cancel": ("CANCEL", "انصراف"),
    "level_big": ("LEVEL %d", "مرحله %d"), "out_lives": ("OUT OF LIVES", "جان‌هایت تمام شد"),
    "tap_retry": ("Tap to retry", "برای تلاش دوباره لمس کن"), "clear": ("LEVEL CLEAR!", "مرحله تمام شد!"),
    "tap_next": ("Tap for next level", "برای مرحله بعد لمس کن"),
    "coins": ("Coins %d / %d", "سکه‌ها %d / %d"), "score": ("Score %d", "امتیاز %d"),
    "leap": ("LEAP", "جهش"),
    "m_life": ("+1 LIFE", "یک جان اضافه"), "m_shield": ("SHIELD", "سپر"), "m_haste": ("HASTE", "سرعت"),
    "m_freeze": ("FREEZE", "یخ‌زدگی"), "m_key": ("KEY", "کلید"), "m_open": ("OPEN!", "باز شد!"),
    "m_locked": ("LOCKED", "قفل است"),
    "h0": ("Reach the glowing tile!", "به خانه‌ی درخشان برس!"),
    "h1": ("You can step up or down one level", "هر بار فقط یک طبقه بالا یا پایین می‌روی"),
    "h2": ("Hold LEAP + a direction to jump 2 tiles", "جهش را نگه دار و یک جهت بزن تا دو خانه بپری"),
    "h3": ("Purple robots patrol: time it, or LEAP over!", "دشمن‌ها گشت می‌زنند؛ زمان‌بندی کن یا از رویشان بپر!"),
    "h_crumble": ("Crumbling tiles fall if you stand still!", "بلوک‌های ریزشی اگر بایستی می‌افتند!"),
    "h_fire": ("Fire jets: wait until the flames die", "فواره‌های آتش: صبر کن تا خاموش شوند"),
    "h_ghost": ("Ghosts chase you when you get close!", "روح‌ها وقتی نزدیکشان شوی دنبالت می‌آیند!"),
    "h_items": ("Items: heart, shield, haste and freeze", "آیتم‌ها: جان، سپر، سرعت و یخ"),
    "h_key": ("Grab the key to open the gate!", "کلید را بردار تا دروازه باز شود!"),
    "font_missing": ("Persian font not found. Put font.ttf next to the game.", ""),
    "help_title": ("How to play", "راهنمای بازی"),
    "tab_basics": ("Basics", "اصول بازی"), "tab_items": ("Items", "آیتم‌ها"), "tab_enemies": ("Enemies", "دشمن‌ها"),
    "tab_traps": ("Traps", "تله‌ها"), "tab_puzzle": ("Puzzles", "معماها"), "tab_heroes": ("Heroes", "قهرمان‌ها"),
    "hp_move": ("Move", "حرکت"), "hd_move": ("Use the four arrow buttons. You move diagonally on the board.", "با چهار دکمه‌ی جهت‌دار حرکت کن. ربات روی صفحه قطری حرکت می‌کند."),
    "hp_leap": ("Leap", "جهش"), "hd_leap": ("Hold LEAP and press a direction to jump two tiles over gaps, traps and enemies.", "جهش را نگه دار و یک جهت بزن تا دو خانه بپری؛ از روی چاله، تله و دشمن."),
    "hp_goal": ("Goal", "هدف"), "hd_goal": ("Reach the glowing tile. Collect every coin to earn three stars.", "به خانه‌ی درخشان برس. همه‌ی سکه‌ها را جمع کن تا سه ستاره بگیری."),
    "hp_height": ("Heights", "ارتفاع"), "hd_height": ("You can climb or drop only one level at a time.", "هر بار فقط می‌توانی یک طبقه بالا یا پایین بروی."),
    "hp_heart": ("Heart", "جان"), "hd_heart": ("+1 life (up to 5).", "یک جان اضافه می‌دهد (حداکثر ۵)."),
    "hp_shield": ("Shield", "سپر"), "hd_shield": ("Protects you from hits for a while.", "مدتی تو را از هر برخوردی حفظ می‌کند."),
    "hp_haste": ("Haste", "سرعت"), "hd_haste": ("You move much faster for a short time.", "مدتی کوتاه خیلی سریع‌تر حرکت می‌کنی."),
    "hp_freeze": ("Freeze", "یخ"), "hd_freeze": ("All enemies freeze in place for a few seconds.", "همه‌ی دشمن‌ها چند ثانیه در جا یخ می‌زنند."),
    "sub_items": ("Items appear in random places every time a level starts.", "آیتم‌ها هر بار که مرحله شروع می‌شود در جاهای تصادفی ظاهر می‌شوند."),
    "hp_patrol": ("Patrollers", "گشتی‌ها"), "hd_patrol": ("Bugs, slimes and spiders walk along a line. Learn the rhythm, then slip past.", "حشره، لجن و عنکبوت روی یک خط می‌روند. ریتمشان را یاد بگیر و رد شو."),
    "hp_ghost": ("Ghost", "روح"), "hd_ghost": ("Slowly chases you when you get close. Keep moving or leap over it.", "وقتی نزدیکش شوی آرام دنبالت می‌آید. حرکت کن یا از رویش بپر."),
    "hp_air": ("In the air", "در هوا"), "hd_air": ("While you are leaping, enemies cannot hurt you.", "وقتی در حال جهش هستی دشمن‌ها نمی‌توانند آسیبت بزنند."),
    "hp_spikes": ("Spikes", "خار"), "hd_spikes": ("They rise and hide in a rhythm. Step on them only when they are down.", "با ریتم بالا و پایین می‌روند. فقط وقتی پایین‌اند رویشان برو."),
    "hp_fire": ("Fire jets", "فواره‌ی آتش"), "hd_fire": ("A red warning, then a burst of flame. Wait until it dies.", "اول هشدار قرمز، بعد شعله. صبر کن تا خاموش شود."),
    "hp_crumble": ("Crumbling tile", "بلوک ریزشی"), "hd_crumble": ("It falls if you stand on it too long. Keep moving!", "اگر زیاد رویش بایستی می‌افتد. حرکت کن!"),
    "hp_key": ("Key", "کلید"), "hd_key": ("Pick it up to unlock a gate.", "برش دار تا یک دروازه باز شود."),
    "hp_gate": ("Gate", "دروازه"), "hd_gate": ("Blocks the way and cannot be jumped over. Find a key first!", "راه را می‌بندد و نمی‌شود از رویش پرید. اول کلید را پیدا کن!"),
    "hp_coin": ("Coins", "سکه"), "hd_coin": ("Collect them all for three stars. Some sit in risky places.", "همه را جمع کن تا سه ستاره بگیری. بعضی‌ها در جاهای خطرناک‌اند."),
    "char_Robo": ("Robo", "روبو"), "char_Kitty": ("Kitty", "گربه"), "char_Alien": ("Alien", "فضایی"), "char_Ninja": ("Ninja", "نینجا"),
    "hd_starter": ("Your first hero.", "قهرمان اولت."),
    "unlock_n": ("Clear %d levels to unlock.", "با تمام‌کردن %d مرحله باز می‌شود."),
}


def T(key):
    pair = STR.get(key)
    if not pair:
        return key
    return pair[1] if LANG == "fa" and pair[1] else pair[0]


_FORMS = {}
for _cp in list(range(0xFB50, 0xFDFF)) + list(range(0xFE70, 0xFF00)):
    _d = unicodedata.decomposition(chr(_cp)).split()
    if len(_d) == 2 and _d[0] in ("<isolated>", "<final>", "<initial>", "<medial>"):
        _FORMS.setdefault(chr(int(_d[1], 16)), {})[_d[0][1:-1]] = chr(_cp)
_LIG = {"ا": ("\ufefb", "\ufefc"), "آ": ("\ufef5", "\ufef6"), "أ": ("\ufef7", "\ufef8"), "إ": ("\ufef9", "\ufefa")}


def _is_ar(c):
    return "\u0600" <= c <= "\u06ff"


def _shape_word(w):
    out, n = [], len(w)
    i = 0
    while i < n:
        c = w[i]
        f = _FORMS.get(c)
        prev_j = i > 0 and "initial" in _FORMS.get(w[i - 1], {}) and out and out[-1] != "\u200c"
        if c == "ل" and i + 1 < n and w[i + 1] in _LIG:
            iso, fin = _LIG[w[i + 1]]
            out.append(fin if prev_j else iso)
            i += 2
            continue
        if not f or "final" not in f:
            out.append(f["isolated"] if f and "isolated" in f else c)
            i += 1
            continue
        next_j = "initial" in f and i + 1 < n and "final" in _FORMS.get(w[i + 1], {})
        form = "medial" if prev_j and next_j else "final" if prev_j else "initial" if next_j else "isolated"
        out.append(f.get(form, f.get("isolated", c)))
        i += 1
    return "".join(out)


def fa_shape(s):
    words = []
    for w in s.split(" "):
        if any(_is_ar(c) for c in w):
            words.append(_shape_word(w.replace("\u200c", "\u200c"))[::-1].replace("\u200c", ""))
        else:
            words.append(w)
    return " ".join(reversed(words))


FA_OK, FA = False, {}


def init_fa_fonts():
    global FA_OK
    paths = []
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        here = "."
    for nme in ("font.ttf", "vyrex_font.ttf", "Vazirmatn.ttf"):
        paths.append(os.path.join(here, nme))
    for nme in ("NotoNaskhArabic-Regular", "NotoNaskhArabicUI-Regular", "NotoSansArabic-Regular",
                "NotoSansArabicUI-Regular", "DroidNaskh-Regular", "Vazirmatn-Regular"):
        paths.append("/system/fonts/" + nme + ".ttf")
    paths += ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf"]
    try:
        mp = pygame.font.match_font("notonaskharabic,vazirmatn,dejavusans,tahoma,arial")
        if mp:
            paths.append(mp)
    except Exception:
        pass
    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            test = pygame.font.Font(p, 24)
            if any(m is None for m in test.metrics("\ufe91\ufbfe\ufeaa")):
                continue
            FA.update({f: pygame.font.Font(p, int(sz * 1.1))
                       for f, sz in ((font, 30), (small, 22), (big, 72), (huge, 118), (mid, 42))})
            FA_OK = True
            return
        except Exception:
            continue


def set_lang(code):
    global LANG
    LANG = "fa" if (code == "fa" and FA_OK) else "en"


def _prep(s, f):
    if FA_OK and any(_is_ar(c) for c in s):
        return FA.get(f, f), fa_shape(s)
    return f, s


def render_label(s, f, color):
    f2, s2 = _prep(s, f)
    return f2.render(s2, True, color)


def text_w(s, f):
    f2, s2 = _prep(s, f)
    return f2.size(s2)[0]


def wrap(s, f, width):
    lines, cur = [], ""
    for w in s.split(" "):
        t = (cur + " " + w).strip()
        if cur and text_w(t, f) > width:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def text(surf, s, pos, f=font, color=(255, 255, 255), center=False, sh=2,
         outline=False, right=False):
    f2, s2 = _prep(s, f)
    img = f2.render(s2, True, color)
    r = img.get_rect()
    if center:
        r.center = pos
    elif right:
        r.topright = pos
    else:
        r.topleft = pos
    dark = f2.render(s2, True, (20, 25, 40))
    if outline:
        for ox_, oy_ in ((-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2), (-2, 2), (2, -2)):
            surf.blit(dark, (r.x + ox_, r.y + oy_ + 2))
    else:
        surf.blit(dark, (r.x + sh, r.y + sh))
    surf.blit(img, r)


def lighten(c, k):
    return tuple(min(255, int(v + (255 - v) * k)) for v in c)


def darken(c, k):
    return tuple(int(v * (1 - k)) for v in c)


def draw_star(s, cx, cy, r, color, outline=DARK):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    pygame.draw.polygon(s, color, pts)
    pygame.draw.polygon(s, outline, pts, 2)


def draw_heart(s, cx, cy, r, color):
    pygame.draw.circle(s, color, (cx - r // 2, cy), r // 2 + 2)
    pygame.draw.circle(s, color, (cx + r // 2, cy), r // 2 + 2)
    pygame.draw.polygon(s, color, [(cx - r - 1, cy + 2), (cx + r + 1, cy + 2),
                                   (cx, cy + r + 5)])
    pygame.draw.line(s, lighten(color, 0.6), (cx - r // 2 - 2, cy - 3),
                     (cx - r // 2 + 1, cy - 4), 2)


def draw_icon(s, kind, cx, cy, r, color=(255, 255, 255)):
    if kind == "play":
        pygame.draw.polygon(s, color, [(cx - r * 0.6, cy - r), (cx + r, cy),
                                       (cx - r * 0.6, cy + r)])
    elif kind == "list":
        for k in (-1, 0, 1):
            pygame.draw.rect(s, color, (cx - r, cy + k * r * 0.7 - 2, r * 2, 4),
                             border_radius=2)
    elif kind == "new":
        pygame.draw.line(s, color, (cx - r, cy), (cx + r, cy), 4)
        pygame.draw.line(s, color, (cx, cy - r), (cx, cy + r), 4)
    elif kind == "back":
        pygame.draw.lines(s, color, False, [(cx + r * 0.5, cy - r),
                                            (cx - r * 0.5, cy),
                                            (cx + r * 0.5, cy + r)], 5)
    elif kind == "next":
        pygame.draw.lines(s, color, False, [(cx - r * 0.5, cy - r),
                                            (cx + r * 0.5, cy),
                                            (cx - r * 0.5, cy + r)], 5)
    elif kind == "lock":
        pygame.draw.rect(s, color, (cx - r, cy - 2, r * 2, r + 6),
                         border_radius=4)
        pygame.draw.circle(s, color, (cx, cy - 3), r - 3, 3)
    elif kind == "sound":
        pygame.draw.polygon(s, color, [(cx - 12, cy - 5), (cx - 6, cy - 5),
                                       (cx + 2, cy - 12), (cx + 2, cy + 12),
                                       (cx - 6, cy + 5), (cx - 12, cy + 5)])
    elif kind == "star":
        draw_star(s, cx, cy, r + 3, GOLD)
    elif kind == "coin":
        pygame.draw.circle(s, GOLD, (cx, cy), r)
        pygame.draw.circle(s, (180, 130, 30), (cx, cy), r, 2)


def draw_panel(s, rect, color=(14, 22, 40), alpha=170, radius=16):
    key = ("pn", rect.w, rect.h, color, alpha, radius)
    surf = _CACHE.get(key)
    if surf is None:
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, color + (alpha,), surf.get_rect(),
                         border_radius=radius)
        pygame.draw.rect(surf, (255, 255, 255, 90), surf.get_rect(), 2,
                         border_radius=radius)
        _CACHE[key] = surf
    s.blit(surf, rect.topleft)


def draw_pill(s, rect, label, color, icon=None, sub=None, f=font, press=0):
    r = rect.move(0, press)
    pygame.draw.rect(s, darken(color, 0.45), rect.move(0, 6), border_radius=18)
    pygame.draw.rect(s, color, r, border_radius=18)
    gloss = pygame.Rect(r.x + 5, r.y + 5, r.w - 10, r.h // 2 - 3)
    pygame.draw.rect(s, lighten(color, 0.28), gloss, border_radius=14)
    pygame.draw.rect(s, color, (r.x + 5, r.y + r.h // 2 - 4, r.w - 10, 8))
    pygame.draw.rect(s, DARK, r, 3, border_radius=18)
    tx = r.centerx
    if icon:
        draw_icon(s, icon, r.x + 28, r.centery - (4 if sub else 0), 11)
        tx += 12
    ty = r.centery - (9 if sub else 0)
    text(s, label, (tx, ty), f, (255, 255, 255), True, 2, True)
    if sub:
        text(s, sub, (tx, r.centery + 15), small, (255, 245, 225), True, 1)


def draw_icon_button(s, rect, kind, on=True):
    pygame.draw.rect(s, darken(BLUE, 0.5), rect.move(0, 4), border_radius=12)
    pygame.draw.rect(s, BLUE, rect, border_radius=12)
    pygame.draw.rect(s, DARK, rect, 3, border_radius=12)
    cx, cy = rect.center
    if kind == "sound":
        draw_icon(s, "sound", cx - 4, cy, 10)
        if on:
            pygame.draw.arc(s, (255, 255, 255), (cx + 2, cy - 7, 10, 14), -1, 1, 3)
            pygame.draw.arc(s, (255, 255, 255), (cx + 5, cy - 12, 14, 24), -1, 1, 3)
        else:
            pygame.draw.line(s, (255, 110, 110), (cx + 6, cy - 7), (cx + 17, cy + 7), 3)
            pygame.draw.line(s, (255, 110, 110), (cx + 17, cy - 7), (cx + 6, cy + 7), 3)
    elif kind == "menu":
        draw_icon(s, "list", cx, cy, 10)
    elif kind.startswith("t:"):
        text(s, kind[2:], (cx, cy + 1), small, (255, 255, 255), True, 1)
    else:
        draw_icon(s, kind, cx, cy, 10)


def dpad_surface(vec, size, down):
    key = ("dp", vec, size, down)
    s = _CACHE.get(key)
    if s is not None:
        return s
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size // 2
    base = (255, 150, 105, 235) if down else (16, 26, 46, 150)
    pygame.draw.circle(s, base, (c, c), c - 2)
    pygame.draw.circle(s, (255, 255, 255, 110 if down else 60), (c, c - 5), c - 12)
    pygame.draw.circle(s, (255, 255, 255, 235), (c, c), c - 2, 3)
    n = math.hypot(vec[0], vec[1])
    ux, uy = vec[0] / n, vec[1] / n
    px, py = -uy, ux
    tip = (c + ux * 19, c + uy * 19)
    a = (c - ux * 8 + px * 16, c - uy * 8 + py * 16)
    b = (c - ux * 8 - px * 16, c - uy * 8 - py * 16)
    pygame.draw.polygon(s, (255, 255, 255, 245), [tip, a, b])
    _CACHE[key] = s
    return s


def leap_surface(size, down):
    key = ("lp", size, down, LANG)
    s = _CACHE.get(key)
    if s is not None:
        return s
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size // 2
    base = (255, 150, 105, 240) if down else (217, 119, 87, 190)
    pygame.draw.circle(s, base, (c, c), c - 2)
    pygame.draw.circle(s, (255, 255, 255, 80), (c, c - 7), c - 14)
    pygame.draw.circle(s, (255, 255, 255, 240), (c, c), c - 2, 4)
    pygame.draw.lines(s, (255, 255, 255, 250), False,
                      [(c - 16, c - 2), (c, c - 18), (c + 16, c - 2)], 6)
    img = render_label(T("leap"), small, (255, 255, 255))
    s.blit(img, img.get_rect(center=(c, c + 20)))
    _CACHE[key] = s
    return s


def overlay(alpha, color=(0, 0, 0)):
    key = ("ov", LW, alpha, color)
    s = _CACHE.get(key)
    if s is None:
        s = pygame.Surface((LW, LH), pygame.SRCALPHA)
        s.fill(color + (alpha,))
        _CACHE[key] = s
    return s


def tile_surf(ti, h, chk, k, crumble=False):
    key = ("tile", ti, h, chk, k, crumble)
    c = _CACHE.get(key)
    if c:
        return c
    base = THEMES[ti]["tiles"][min(h, 3)]
    if crumble:
        base = tuple((a + b) // 2 for a, b in zip(base, (150, 105, 80)))
    top = tuple(min(255, v + chk) for v in base)
    left, right = darken(base, 0.4), darken(base, 0.22)
    hw, hh, drop = TW // 2, TH // 2, h * HZ
    s = pygame.Surface((TW + 2, TH + drop + 3), pygame.SRCALPHA)
    cx, cy = (TW + 2) // 2, hh + 1
    pl = [(cx - hw, cy), (cx, cy + hh), (cx, cy + hh + drop), (cx - hw, cy + drop)]
    pr = [(cx, cy + hh), (cx + hw, cy), (cx + hw, cy + drop), (cx, cy + hh + drop)]
    pt = [(cx, cy - hh), (cx + hw, cy), (cx, cy + hh), (cx - hw, cy)]
    pygame.draw.polygon(s, left, pl)
    pygame.draw.polygon(s, right, pr)
    pygame.draw.polygon(s, top, pt)
    for j in range(1, h):
        pygame.draw.line(s, darken(base, 0.5), (cx - hw, cy + j * HZ), (cx, cy + hh + j * HZ), 1)
        pygame.draw.line(s, darken(base, 0.35), (cx, cy + hh + j * HZ), (cx + hw, cy + j * HZ), 1)
    pygame.draw.lines(s, lighten(top, 0.35), False,
                      [(cx - hw + 2, cy), (cx, cy - hh + 1), (cx + hw - 2, cy)], 2)
    for poly in (pl, pr, pt):
        pygame.draw.polygon(s, DARK, poly, 1)
    if crumble:
        pygame.draw.lines(s, (60, 40, 30), False, [(cx - 14, cy - 2), (cx - 4, cy + 3), (cx + 2, cy - 4), (cx + 14, cy + 2)], 2)
    elif k is not None:
        draw_decor(s, ti, cx, cy, k)
    _CACHE[key] = (s, cx, cy)
    return _CACHE[key]


ITEM_COL = {"heart": (235, 70, 80), "shield": (90, 170, 255),
            "haste": (255, 215, 70), "freeze": (170, 235, 255)}


def draw_item_icon(s, kind, cx, cy, r=12):
    col = ITEM_COL[kind]
    if kind == "heart":
        draw_heart(s, cx, cy - 2, r - 2, col)
    elif kind == "shield":
        pts = [(cx - r, cy - r + 2), (cx + r, cy - r + 2), (cx + r, cy + 2), (cx, cy + r + 3), (cx - r, cy + 2)]
        pygame.draw.polygon(s, col, pts)
        pygame.draw.polygon(s, DARK, pts, 2)
        pygame.draw.line(s, (255, 255, 255), (cx, cy - r + 5), (cx, cy + r - 2), 2)
    elif kind == "haste":
        pts = [(cx + 3, cy - r), (cx - r + 3, cy + 2), (cx - 1, cy + 2), (cx - 3, cy + r), (cx + r - 3, cy - 3), (cx + 1, cy - 3)]
        pygame.draw.polygon(s, col, pts)
        pygame.draw.polygon(s, DARK, pts, 2)
    else:
        for a in range(3):
            ang = a * math.pi / 3
            dx, dy = math.cos(ang) * r, math.sin(ang) * r
            pygame.draw.line(s, col, (cx - dx, cy - dy), (cx + dx, cy + dy), 3)
        pygame.draw.circle(s, (255, 255, 255), (cx, cy), 3)


def draw_key_icon(s, cx, cy, r=11):
    pygame.draw.circle(s, GOLD, (cx - r // 2, cy), r // 2 + 2)
    pygame.draw.circle(s, DARK, (cx - r // 2, cy), r // 2 - 1)
    pygame.draw.rect(s, GOLD, (cx - 1, cy - 2, r + 4, 4))
    pygame.draw.rect(s, GOLD, (cx + r - 2, cy, 3, 6))
    pygame.draw.rect(s, GOLD, (cx + r - 7, cy, 3, 4))
    pygame.draw.circle(s, (180, 130, 30), (cx - r // 2, cy), r // 2 + 2, 2)


def draw_gate(s, cx, cy):
    hw, hh, hgt = TW // 2 - 4, TH // 2 - 2, 38
    left = [(cx - hw, cy), (cx, cy + hh), (cx, cy + hh - hgt), (cx - hw, cy - hgt)]
    right = [(cx, cy + hh), (cx + hw, cy), (cx + hw, cy - hgt), (cx, cy + hh - hgt)]
    top = [(cx, cy - hh - hgt), (cx + hw, cy - hgt), (cx, cy + hh - hgt), (cx - hw, cy - hgt)]
    pygame.draw.polygon(s, (110, 74, 52), left)
    pygame.draw.polygon(s, (140, 96, 66), right)
    pygame.draw.polygon(s, (170, 120, 84), top)
    for poly in (left, right, top):
        pygame.draw.polygon(s, DARK, poly, 2)
    pygame.draw.circle(s, GOLD, (cx + 10, cy - 12), 6)
    pygame.draw.rect(s, DARK, (cx + 9, cy - 12, 3, 8))


def draw_help_icon(s, kind, cx, cy, t):
    if kind in ITEM_COL:
        draw_item_icon(s, kind, cx, cy, 14)
    elif kind in SKINS:
        s.blit(SKINS[kind], (cx - 16, cy - 16 - int(abs(math.sin(t / 8)) * 3)))
    elif kind.startswith("char"):
        s.blit(char_sprite(int(kind[4:]), 2), (cx - 16, cy - 17))
    elif kind == "key":
        draw_key_icon(s, cx, cy, 14)
    elif kind == "gate":
        draw_gate(s, cx, cy + 14)
    elif kind == "coin":
        draw_icon(s, "coin", cx, cy, 13)
    elif kind == "dpad":
        s.blit(dpad_surface((1, -1), 48, False), (cx - 24, cy - 24))
    elif kind in ("leap", "air"):
        pygame.draw.circle(s, CORAL, (cx, cy), 20)
        pygame.draw.circle(s, (255, 255, 255), (cx, cy), 20, 3)
        pygame.draw.lines(s, (255, 255, 255), False, [(cx - 10, cy + 3), (cx, cy - 9), (cx + 10, cy + 3)], 5)
    elif kind == "goal":
        k = 0.5 + 0.5 * math.sin(t / 8)
        pygame.draw.polygon(s, (int(60 + 80 * k), int(200 + 40 * k), 230),
                            [(cx, cy - 14), (cx + 26, cy), (cx, cy + 14), (cx - 26, cy)])
        pygame.draw.polygon(s, (255, 255, 255), [(cx, cy - 14), (cx + 26, cy), (cx, cy + 14), (cx - 26, cy)], 2)
    elif kind == "height":
        for j in range(3):
            pygame.draw.rect(s, (104 + j * 40, 190 - j * 20, 96), (cx - 22 + j * 14, cy + 10 - j * 12, 14, 10 + j * 12))
            pygame.draw.rect(s, DARK, (cx - 22 + j * 14, cy + 10 - j * 12, 14, 10 + j * 12), 2)
    elif kind == "spikes":
        for dx in (-14, 0, 14):
            pygame.draw.polygon(s, (215, 220, 230), [(cx + dx - 7, cy + 12), (cx + dx, cy - 14), (cx + dx + 7, cy + 12)])
            pygame.draw.polygon(s, DARK, [(cx + dx - 7, cy + 12), (cx + dx, cy - 14), (cx + dx + 7, cy + 12)], 2)
    elif kind == "fire":
        for j, c in enumerate(((255, 120, 40), (255, 190, 60), (255, 240, 150))):
            hgt, w = 28 - j * 8 + int(3 * math.sin(t / 3 + j)), 13 - j * 3
            pygame.draw.polygon(s, c, [(cx - w, cy + 12), (cx, cy + 12 - hgt), (cx + w, cy + 12)])
    elif kind == "crumble":
        surf, a, b = tile_surf(0, 1, 0, None, True)
        s.blit(surf, (cx - a, cy - b))


# ---------------------------------------------------------------- save
def save_path():
    base = os.environ.get("ANDROID_PRIVATE")
    if not base:
        try:
            base = os.path.dirname(os.path.abspath(__file__))
        except Exception:
            base = "."
    return os.path.join(base, "vyrex_save.json")


def fresh_save():
    return {"unlocked": 1, "level": 0, "best": {}, "char": 0, "seen": [], "lang": "en"}


def load_save():
    data = fresh_save()
    try:
        with open(save_path()) as f:
            d = json.load(f)
        data["unlocked"] = max(1, int(d.get("unlocked", 1)))
        data["level"] = max(0, int(d.get("level", data["unlocked"] - 1)))
        data["best"] = {str(k): int(v) for k, v in d.get("best", {}).items()}
        data["char"] = max(0, int(d.get("char", 0)))
        data["seen"] = [str(x) for x in d.get("seen", [])]
        data["lang"] = "fa" if d.get("lang") == "fa" else "en"
    except Exception:
        pass
    return data


def write_save(data):
    try:
        with open(save_path(), "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def count_coins(rows):
    return sum(ch in "cCD" for row in rows for ch in row)


# ---------------------------------------------------------------- layout
def menu_rects(has):
    keys = ["cont", "levels", "hero", "new"] if has else ["cont", "levels", "hero"]
    n, gap = len(keys), 12
    bw = min(220, (LW - 40 - (n - 1) * gap) // n)
    x0 = (LW - (n * bw + (n - 1) * gap)) // 2
    r = {k: pygame.Rect(x0 + i * (bw + gap), 358, bw, 70) for i, k in enumerate(keys)}
    r["sound"] = pygame.Rect(LW - 56, 10, 44, 44)
    r["lang"] = pygame.Rect(LW - 108, 10, 44, 44)
    r["help"] = pygame.Rect(12, 10, 44, 44)
    return r


def help_rects():
    return {"back": pygame.Rect(12, 10, 64, 44), "lang": pygame.Rect(LW - 56, 10, 44, 44),
            "prev": pygame.Rect(LW // 2 - 150, 388, 80, 48), "next": pygame.Rect(LW // 2 + 70, 388, 80, 48)}


def chars_rects():
    cw = min(170, (LW - 60 - 36) // 4)
    x0 = (LW - (4 * cw + 36)) // 2
    return {"back": pygame.Rect(12, 10, 64, 44),
            "cards": [pygame.Rect(x0 + i * (cw + 12), 108, cw, 250) for i in range(4)]}


def select_rects():
    cw, ch, gap = 90, 96, 12
    x0 = (LW - (5 * cw + 4 * gap)) // 2
    cells = [pygame.Rect(x0 + (i % 5) * (cw + gap),
                         118 + (i // 5) * (ch + gap), cw, ch)
             for i in range(10)]
    return {"back": pygame.Rect(12, 10, 64, 44),
            "sound": pygame.Rect(LW - 56, 10, 44, 44),
            "prev": pygame.Rect(max(4, x0 - 56), 190, 46, 70),
            "next": pygame.Rect(min(LW - 50, x0 + 5 * cw + 4 * gap + 10), 190, 46, 70),
            "cells": cells}


def confirm_rects():
    panel = pygame.Rect(LW // 2 - 230, 110, 460, 220)
    return {"panel": panel,
            "yes": pygame.Rect(panel.x + 28, panel.bottom - 82, 190, 60),
            "no": pygame.Rect(panel.right - 218, panel.bottom - 82, 190, 60)}


def play_rects():
    return {"menu": pygame.Rect(LW - 56, 10, 44, 44),
            "sound": pygame.Rect(LW - 108, 10, 44, 44)}


# ---------------------------------------------------------------- game
ITEMS = ["heart", "shield", "shield", "haste", "haste", "freeze", "freeze", "heart"]
HINT_NEW = [("k", "h_key"), ("x", "h_crumble"), ("f", "h_fire"), ("h", "h_ghost"), ("i", "h_items")]
MENU_STATES = ("menu", "select", "confirm", "chars", "help")
HELP_PAGES = [
    ("tab_basics", None, [("dpad", "hp_move", "hd_move"), ("leap", "hp_leap", "hd_leap"),
                          ("goal", "hp_goal", "hd_goal"), ("height", "hp_height", "hd_height")]),
    ("tab_items", "sub_items", [("heart", "hp_heart", "hd_heart"), ("shield", "hp_shield", "hd_shield"),
                                ("haste", "hp_haste", "hd_haste"), ("freeze", "hp_freeze", "hd_freeze")]),
    ("tab_enemies", None, [("bug", "hp_patrol", "hd_patrol"), ("ghost", "hp_ghost", "hd_ghost"),
                           ("air", "hp_air", "hd_air")]),
    ("tab_traps", None, [("spikes", "hp_spikes", "hd_spikes"), ("fire", "hp_fire", "hd_fire"),
                         ("crumble", "hp_crumble", "hd_crumble")]),
    ("tab_puzzle", None, [("key", "hp_key", "hd_key"), ("gate", "hp_gate", "hd_gate"),
                          ("coin", "hp_coin", "hd_coin")]),
    ("tab_heroes", None, [("char0", "char_Robo", "hd_starter"), ("char1", "char_Kitty", 5),
                          ("char2", "char_Alien", 10), ("char3", "char_Ninja", 20)]),
]


class Game:
    def __init__(self):
        self.save = load_save()
        self.t = 0
        self.parts, self.texts = [], []
        self.shake = self.flash = self.cool = self.fade = self.pulse = 0
        self.score = self.leap_buf = self.timer = self.stars = 0
        self.lives, self.idx, self.page = 3, 0, 0
        self.theme_i = 0
        self.haste = self.freeze = 0
        self.items, self.falling, self.crumb, self.gone = [], [], {}, {}
        self.hint = ""
        self.keys = self.lock_cd = self.toast = self.help_page = 0
        self.char = min(self.save.get("char", 0), len(CHARS) - 1)
        set_lang(self.save.get("lang", "en"))
        self.go_menu()

    # --------------------------------------------------------- states
    def has_progress(self):
        return self.save["level"] > 0 or bool(self.save["best"])

    def _scene(self, lv, state, theme=0):
        self.lv = lv
        self.rb = Robot(lv)
        self.state = state
        self.tick = self.timer = 0
        self.cool, self.fade = 12, 16
        self.intro = lv.maxd * 4 + 30
        self.parts, self.texts, self.falling = [], [], []
        self.crumb, self.gone = {}, {}
        self.items, self.hint = [], ""
        self.haste = self.freeze = self.keys = 0
        self.theme_i = theme
        self.theme = THEMES[theme]
        self.enemies, self.coins, self.got = [], set(), 0

    def go_menu(self):
        self._scene(Level(MENU_ROWS), "menu")

    def go_select(self):
        self._scene(Level(MENU_ROWS), "select")
        self.page = min(self.save["level"], self.save["unlocked"] - 1) // 10

    def go_chars(self):
        self._scene(Level(MENU_ROWS), "chars")

    def load(self, i):
        self.idx = i
        rows = rows_for(i)
        self.total_coins = count_coins(rows)
        self._scene(Level(rows), "play", (i // 10) % len(THEMES))
        lv = self.lv
        self.rb.inv, self.lives, self.leap_buf = 60, 3, 0
        skins = ["bug", "slime", "spider"]
        self.enemies = [Enemy(x, y, k, lv, 1 if n % 2 == 0 else -1, skins[(i + n) % 3])
                        for n, (x, y, k) in enumerate(lv.enemy_defs)]
        self.enemies += [Enemy(x, y, "h", lv, 1) for x, y in lv.chasers]
        self.coins = set(lv.coins)
        taken = (set(lv.coins) | lv.spikes | lv.fires | lv.crumbles
                 | {lv.start, lv.goal} | {(e.tx, e.ty) for e in self.enemies})
        free = [t for t in lv.order if t not in taken]
        random.shuffle(free)
        n = random.choice([1, 1, 2, 2, 3]) if len(free) > 5 else 0
        self.items = [[t[0], t[1], random.choice(ITEMS)] for t in free[:n]]
        self.hint = HINTS.get(i, "")
        if not self.hint:
            have = {"k": lv.doors, "x": lv.crumbles, "f": lv.fires, "h": lv.chasers, "i": self.items}
            for key, msg in HINT_NEW:
                if have[key] and key not in self.save.setdefault("seen", []):
                    self.hint = msg
                    self.save["seen"].append(key)
                    write_save(self.save)
                    break

    def start_fresh(self, i):
        self.score = 0
        self.load(i)

    def new_game(self):
        keep = (self.save.get("char", 0), self.save.get("seen", []), self.save.get("lang", "en"))
        self.save = fresh_save()
        self.save["char"], self.save["seen"], self.save["lang"] = keep
        write_save(self.save)
        self.start_fresh(0)

    def back(self):
        if self.state == "menu":
            return True
        if self.state in ("select", "confirm", "chars", "help"):
            self.go_menu()
        else:
            self.go_select()
        return False

    # --------------------------------------------------------- helpers
    def spike_up(self, x, y):
        return (self.tick // 60 + x + y) % 2 == 0

    def spike_soon(self, x, y):
        return (not self.spike_up(x, y)) and self.tick % 60 >= 45

    def fire_phase(self, x, y):
        ph = (self.tick + x * 37 + y * 53) % 110
        return 2 if ph >= 80 else (1 if ph >= 60 else 0)

    def burst(self, x, y, color, n, speed=4, size=4, up=1):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            sp = random.uniform(1, speed)
            self.parts.append([x, y, math.cos(a) * sp, math.sin(a) * sp - up,
                               random.randint(15, 32), color, size])

    def hurt(self, sx, sy):
        self.lives -= 1
        self.shake, self.flash = 14, 14
        self.burst(sx, sy, (255, 80, 80), 18)
        sfx("hurt")
        if self.lives <= 0:
            self.state, self.timer, self.cool = "over", 0, 12
        else:
            self.rb = Robot(self.lv)
            self.rb.inv = 90

    def origin(self):
        x0, x1, y0, y1 = self.lv.bounds
        ox = LW / 2 - (x0 + x1) / 2
        oy = (212 if self.state in MENU_STATES else LH / 2 - 14) - (y0 + y1) / 2
        return ox, oy

    def tile_p(self, x, y):
        return max(0.0, min(1.0, (self.tick - (x + y) * 4) / 22))

    def tile_dy(self, x, y):
        return -((1 - self.tile_p(x, y)) ** 3) * 180

    def next_level(self):
        self.load(self.idx + 1)

    def drop_tile(self, t):
        h = self.lv.tiles.pop(t)
        self.gone[t] = (h, self.tick + 260)
        self.falling.append([t[0], t[1], h, 0])
        self.crumb.pop(t, None)
        self.burst(*proj(t[0], t[1], h, *self.origin()), (150, 105, 80), 8, 3, 4)

    def move(self, dx, dy, dist, fast):
        rb, lv = self.rb, self.lv
        tgt = (rb.tx + dx * dist, rb.ty + dy * dist)
        mid = (rb.tx + dx, rb.ty + dy)
        if (dist == 2 and mid in lv.doors) or (tgt in lv.doors and self.keys <= 0):
            rb.fx, rb.fy = dx, dy
            if not self.lock_cd:
                self.lock_cd = 40
                sx, sy = proj(rb.x, rb.y, rb.h, *self.origin())
                self.texts.append([sx, sy - 50, T("m_locked"), 36, (255, 120, 120)])
            return False
        was_door = tgt in lv.doors
        ok = rb.start(lv, dx, dy, dist, fast)
        if ok:
            sfx("leap" if dist == 2 else "hop")
            if was_door:
                self.keys -= 1
                lv.doors.discard(tgt)
                px, py = proj(tgt[0], tgt[1], 1, *self.origin())
                self.burst(px, py - 10, GOLD, 14, 3, 4)
                self.texts.append([px, py - 40, T("m_open"), 44, GOLD])
        return ok

    def switch_lang(self):
        if not FA_OK:
            self.toast = 150
            return
        self.save["lang"] = "en" if LANG == "fa" else "fa"
        set_lang(self.save["lang"])
        write_save(self.save)
        sfx("click")

    def apply_item(self, kind, sx, sy):
        rb = self.rb
        msg = T({"heart": "m_life", "shield": "m_shield", "haste": "m_haste", "freeze": "m_freeze"}[kind])
        if kind == "heart":
            self.lives = min(5, self.lives + 1)
        elif kind == "shield":
            rb.shield = 480
        elif kind == "haste":
            self.haste = 420
        else:
            self.freeze = 300
        self.burst(sx, sy - 24, ITEM_COL[kind], 12, 3, 4)
        self.texts.append([sx, sy - 48, msg, 50, ITEM_COL[kind]])
        sfx("coin")

    # --------------------------------------------------------- update
    def update(self, direction, leap_edge, leap_held, taps=(), confirm=False):
        self.t += 1
        for k in ("cool", "fade", "pulse", "shake", "flash", "lock_cd", "toast"):
            if getattr(self, k):
                setattr(self, k, getattr(self, k) - 1)
        for q in self.parts:
            q[0] += q[2]
            q[1] += q[3]
            q[3] += 0.15
            q[4] -= 1
        self.parts = [q for q in self.parts if q[4] > 0]
        for q in self.texts:
            q[1] -= 0.8
            q[3] -= 1
        self.texts = [q for q in self.texts if q[3] > 0]
        self.tick += 1
        self.handle_taps(taps, confirm)
        st = self.state
        if st in MENU_STATES:
            rb = self.rb
            if self.tick > self.intro and rb.mv is None and self.tick % 40 == 0:
                ds = list(DIRS.values())
                random.shuffle(ds)
                for dx, dy in ds:
                    if rb.start(self.lv, dx, dy, 1):
                        break
            rb.update()
            return
        if st == "over":
            self.timer += 1
            return
        if st == "clear":
            self.timer += 1
            if self.timer % 6 == 0 and self.timer < 60:
                self.burst(random.randint(100, LW - 100), -10,
                           random.choice([GOLD, CORAL, (92, 225, 230), (155, 93, 229)]), 6, 3, 5, -2)
            if self.timer > 150:
                self.next_level()
            return
        if self.tick < self.intro:
            return
        rb, lv = self.rb, self.lv
        if leap_edge:
            self.leap_buf = 10
        elif self.leap_buf:
            self.leap_buf -= 1
        fast = self.haste > 0
        if rb.mv is None:
            if direction and leap_held:
                self.leap_buf = 0
                self.move(direction[0], direction[1], 2, fast)
            elif direction:
                self.move(direction[0], direction[1], 1, fast)
            elif 0 < self.leap_buf <= 6:
                self.leap_buf = 0
                self.move(rb.fx, rb.fy, 2, fast)
        ox, oy = self.origin()
        if rb.update():
            fx, fy = proj(rb.x, rb.y, rb.h, ox, oy)
            self.burst(fx, fy + 6, (235, 235, 225), 5, 1.6, 3, 0.2)
        for k in ("inv", "shield"):
            if getattr(rb, k):
                setattr(rb, k, getattr(rb, k) - 1)
        if self.haste:
            self.haste -= 1
        if self.freeze:
            self.freeze -= 1
        for e in self.enemies:
            e.update(lv, rb, self.freeze > 0)
        for t, (h, at) in list(self.gone.items()):
            if self.tick >= at:
                lv.tiles[t] = h
                del self.gone[t]
        for f in self.falling:
            f[3] += 1
        self.falling = [f for f in self.falling if f[3] < 30]
        cur = (rb.tx, rb.ty) if rb.mv is None else None
        for t in list(self.crumb):
            if t != cur:
                del self.crumb[t]
        if cur in lv.crumbles and cur in lv.tiles:
            self.crumb[cur] = self.crumb.get(cur, 0) + 1
            if self.crumb[cur] >= 42:
                self.drop_tile(cur)
        sx, sy = proj(rb.x, rb.y, rb.h, ox, oy)
        gx, gy = proj(lv.goal[0], lv.goal[1], lv.tiles[lv.goal], ox, oy)
        if self.tick % 7 == 0:
            self.parts.append([gx + random.randint(-14, 14), gy, 0, -1.2, 30, (200, 250, 255), 3])
        if rb.mv is None:
            tile = (rb.tx, rb.ty)
            if tile not in lv.tiles:
                self.hurt(sx, sy - 20)
                return
            if tile in self.coins:
                self.coins.discard(tile)
                self.got += 1
                self.pulse = 10
                self.score += 10
                self.burst(sx, sy - 24, GOLD, 10, 3, 3)
                self.texts.append([sx, sy - 40, "+10", 40, GOLD])
                sfx("coin")
            if tile in lv.keys:
                lv.keys.discard(tile)
                self.keys += 1
                self.burst(sx, sy - 24, GOLD, 12, 3, 4)
                self.texts.append([sx, sy - 48, T("m_key"), 50, GOLD])
                sfx("coin")
            for it in self.items[:]:
                if (it[0], it[1]) == tile:
                    self.items.remove(it)
                    self.apply_item(it[2], sx, sy)
            if not rb.safe():
                if (tile in lv.spikes and self.spike_up(*tile)) or \
                        (tile in lv.fires and self.fire_phase(*tile) == 2):
                    self.hurt(sx, sy - 20)
                    return
            if tile == lv.goal:
                self.score += 100
                self.state, self.timer = "clear", 0
                ratio = self.got / max(1, self.total_coins)
                self.stars = 3 if ratio >= 1 else (2 if ratio >= 0.5 else 1)
                self.save["unlocked"] = max(self.save["unlocked"], self.idx + 2)
                self.save["level"] = max(self.save["level"], self.idx + 1)
                key = str(self.idx)
                self.save["best"][key] = max(self.save["best"].get(key, 0), self.got)
                write_save(self.save)
                sfx("clear")
                return
        if not rb.safe() and not rb.airborne():
            for e in self.enemies:
                if abs(e.x - rb.x) + abs(e.y - rb.y) < 0.6 and abs(e.h - rb.h) < 0.9:
                    self.hurt(sx, sy - 20)
                    return

    def handle_taps(self, taps, confirm):
        st = self.state
        if self.cool:
            return
        if confirm:
            if st == "menu":
                sfx("click")
                self.start_fresh(self.save["level"] if self.has_progress() else 0)
            elif st == "confirm":
                sfx("click")
                self.new_game()
            elif st == "over" and self.timer > 40:
                sfx("click")
                self.load(self.idx)
            elif st == "clear" and self.timer > 25:
                self.next_level()
            return
        for p in taps:
            if st == "over" and self.timer > 40:
                sfx("click")
                self.load(self.idx)
                return
            if st == "clear" and self.timer > 25:
                self.next_level()
                return
            if st == "menu":
                r = menu_rects(self.has_progress())
                if r["cont"].collidepoint(p):
                    sfx("click")
                    self.start_fresh(self.save["level"] if self.has_progress() else 0)
                    return
                if r["levels"].collidepoint(p):
                    sfx("click")
                    self.go_select()
                    return
                if r["hero"].collidepoint(p):
                    sfx("click")
                    self.go_chars()
                    return
                if "new" in r and r["new"].collidepoint(p):
                    sfx("click")
                    self.state, self.cool = "confirm", 10
                    return
                if r["sound"].collidepoint(p):
                    toggle_mute()
                    sfx("click")
                elif r["help"].collidepoint(p):
                    sfx("click")
                    self.help_page = 0
                    self._scene(Level(MENU_ROWS), "help")
                    return
                elif r["lang"].collidepoint(p):
                    self.switch_lang()
            elif st == "help":
                r = help_rects()
                if r["back"].collidepoint(p):
                    sfx("click")
                    self.go_menu()
                    return
                if r["lang"].collidepoint(p):
                    self.switch_lang()
                elif r["prev"].collidepoint(p):
                    self.help_page = (self.help_page - 1) % len(HELP_PAGES)
                    sfx("click")
                elif r["next"].collidepoint(p):
                    self.help_page = (self.help_page + 1) % len(HELP_PAGES)
                    sfx("click")
            elif st == "chars":
                r = chars_rects()
                if r["back"].collidepoint(p):
                    sfx("click")
                    self.go_menu()
                    return
                for i, c in enumerate(r["cards"]):
                    if c.collidepoint(p) and self.save["level"] >= CHARS[i]["unlock"]:
                        self.char = i
                        self.save["char"] = i
                        write_save(self.save)
                        sfx("coin")
            elif st == "confirm":
                r = confirm_rects()
                if r["yes"].collidepoint(p):
                    sfx("click")
                    self.new_game()
                    return
                if r["no"].collidepoint(p):
                    sfx("click")
                    self.state, self.cool = "menu", 10
                    return
            elif st == "select":
                r = select_rects()
                maxpage = (self.save["unlocked"] - 1) // 10
                if r["back"].collidepoint(p):
                    sfx("click")
                    self.go_menu()
                    return
                if r["sound"].collidepoint(p):
                    toggle_mute()
                    sfx("click")
                elif r["prev"].collidepoint(p) and self.page > 0:
                    self.page -= 1
                    sfx("click")
                elif r["next"].collidepoint(p) and self.page < maxpage:
                    self.page += 1
                    sfx("click")
                else:
                    for i, c in enumerate(r["cells"]):
                        n = self.page * 10 + i
                        if c.collidepoint(p) and n < self.save["unlocked"]:
                            sfx("click")
                            self.start_fresh(n)
                            return
            elif st == "play":
                r = play_rects()
                if r["menu"].collidepoint(p):
                    sfx("click")
                    self.go_select()
                    return
                if r["sound"].collidepoint(p):
                    toggle_mute()
                    sfx("click")

    # --------------------------------------------------------- drawing
    def draw_tile(self, s, x, y, ox, oy):
        lv = self.lv
        if (x, y) not in lv.tiles or self.tile_p(x, y) <= 0:
            return
        h = lv.tiles[(x, y)]
        special = (x, y) in lv.spikes or (x, y) in lv.fires or \
            (x, y) == lv.goal or (x, y) == lv.start
        k = (x * 5 + y * 3) % 4
        k = k if (k in (0, 2) and not special and self.state != "menu") else None
        crumble = (x, y) in lv.crumbles
        surf, cx0, cy0 = tile_surf(self.theme_i, h, 12 if (x + y) % 2 else 0, k, crumble)
        cx, cy = proj(x, y, h, ox, oy + self.tile_dy(x, y))
        if crumble and self.crumb.get((x, y)):
            cx += 2 if (self.tick // 2) % 2 else -2
        s.blit(surf, (int(cx - cx0), int(cy - cy0)))
        hw, hh = TW // 2, TH // 2
        pt = [(cx, cy - hh), (cx + hw, cy), (cx, cy + hh), (cx - hw, cy)]
        if (x, y) == lv.goal and self.state in ("play", "clear", "over"):
            kk = 0.5 + 0.5 * math.sin(self.tick / 8)
            pygame.draw.polygon(s, (int(60 + 80 * kk), int(200 + 40 * kk), 230), pt)
            r = 6 + int(4 * kk)
            pygame.draw.polygon(s, (255, 255, 255), [(cx, cy - hh + r), (cx + hw - 2 * r, cy),
                                                     (cx, cy + hh - r), (cx - hw + 2 * r, cy)], 2)
            pygame.draw.polygon(s, DARK, pt, 1)
        if (x, y) == lv.start and self.state == "play":
            pygame.draw.polygon(s, (255, 255, 255), [(cx, cy - hh + 6), (cx + hw - 12, cy),
                                                     (cx, cy + hh - 6), (cx - hw + 12, cy)], 1)
        if (x, y) in lv.spikes:
            up, soon = self.spike_up(x, y), self.spike_soon(x, y)
            for dx, dy in ((-14, 2), (0, -4), (14, 2)):
                if up:
                    tri = [(cx + dx - 6, cy + dy + 4), (cx + dx, cy + dy - 18), (cx + dx + 6, cy + dy + 4)]
                    pygame.draw.polygon(s, (215, 220, 230), tri)
                    pygame.draw.polygon(s, DARK, tri, 1)
                else:
                    col = (230, 90, 90) if soon and (self.tick // 4) % 2 else (60, 70, 60)
                    pygame.draw.circle(s, col, (int(cx + dx), int(cy + dy + 2)), 3)
        if (x, y) in lv.doors:
            draw_gate(s, cx, cy)
        if (x, y) in lv.fires:
            ph = self.fire_phase(x, y)
            pygame.draw.ellipse(s, (40, 30, 30), (int(cx - 12), int(cy - 5), 24, 12))
            if ph == 1:
                r = 8 + int(3 * math.sin(self.tick / 3))
                pygame.draw.circle(s, (255, 120, 60), (int(cx), int(cy)), r, 2)
            elif ph == 2:
                for j, c in enumerate(((255, 120, 40), (255, 190, 60), (255, 240, 150))):
                    hgt = (34 - j * 9) + int(5 * math.sin(self.tick / 2 + j))
                    w = 12 - j * 3
                    pygame.draw.polygon(s, c, [(cx - w, cy), (cx, cy - hgt), (cx + w, cy)])

    def draw_entity(self, s, kind, obj, ox, oy):
        if kind in ("coin", "item", "key"):
            x, y = obj[0], obj[1]
            if self.tile_p(x, y) < 1 or (x, y) not in self.lv.tiles:
                return
            cx, cy = proj(x, y, self.lv.tiles[(x, y)], ox, oy)
            bob = math.sin(self.tick / 10 + x + y) * 3
            pygame.draw.ellipse(s, (60, 100, 60), (int(cx - 8), int(cy - 2), 16, 6))
            if kind == "key":
                draw_key_icon(s, int(cx), int(cy - 22 + bob), 11)
                return
            if kind == "item":
                pygame.draw.circle(s, ITEM_COL[obj[2]], (int(cx), int(cy - 22 + bob)),
                                   17 + int(2 * math.sin(self.tick / 8)), 2)
                draw_item_icon(s, obj[2], int(cx), int(cy - 22 + bob), 11)
                return
            w = max(3, int(abs(math.cos(self.tick / 12 + x)) * 9))
            r = (int(cx - w), int(cy - 26 + bob), w * 2, 18)
            pygame.draw.ellipse(s, GOLD, r)
            pygame.draw.ellipse(s, (180, 130, 30), r, 2)
        elif kind == "enemy":
            oy2 = oy + self.tile_dy(int(round(obj.x)), int(round(obj.y)))
            cx, cy = proj(obj.x, obj.y, obj.h, ox, oy2)
            hop = abs(math.sin(self.tick / 7 + obj.tx)) * 6 if self.freeze == 0 else 0
            if obj.chase:
                hop = 6 + math.sin(self.tick / 9) * 5
            pygame.draw.ellipse(s, (30, 60, 40), (int(cx - 14 + hop / 2), int(cy - 4), int(28 - hop), 9))
            s.blit(SKINS[obj.skin], (int(cx - 16), int(cy - 22 - hop)))
            if self.freeze:
                pygame.draw.circle(s, (170, 235, 255), (int(cx), int(cy - 12 - hop)), 20, 2)
        else:
            rb = obj
            oy2 = oy + self.tile_dy(int(round(rb.x)), int(round(rb.y)))
            cx, cy = proj(rb.x, rb.y, rb.h, ox, oy2)
            sh = max(8, 20 - rb.lift / 3)
            pygame.draw.ellipse(s, (20, 50, 30), (int(cx - sh), int(cy - 5), int(sh * 2), 11))
            if rb.inv and (rb.inv // 4) % 2:
                return
            w = h = 48
            if rb.squash:
                q = rb.squash / 7
                w, h = int(48 * (1 + 0.22 * q)), int(48 * (1 - 0.22 * q))
            elif rb.mv:
                w, h = 44, 52
            spr = char_sprite(self.char, 3, (rb.fx - rb.fy) < 0)
            if (w, h) != (48, 48):
                key = ("sq", self.char, (rb.fx - rb.fy) < 0, w, h)
                if key not in _CACHE:
                    _CACHE[key] = pygame.transform.scale(spr, (w, h))
                spr = _CACHE[key]
            bob = 0 if rb.mv else int(round(math.sin(self.tick / 9) * 1.5))
            if rb.shield:
                pygame.draw.circle(s, (120, 190, 255), (int(cx), int(cy - 20 - rb.lift)),
                                   30 + int(2 * math.sin(self.tick / 5)), 2)
            s.blit(spr, (int(cx - w / 2), int(cy + 6 - h - rb.lift + bob)))

    def draw_world(self, s, ox, oy):
        ents = [(c[0] + c[1], "coin", c) for c in self.coins]
        ents += [(it[0] + it[1], "item", it) for it in self.items]
        ents += [(k[0] + k[1], "key", k) for k in self.lv.keys]
        for e in self.enemies:
            if self.tick >= self.intro or self.tile_p(e.tx, e.ty) > 0:
                ents.append((int(math.floor(e.x + e.y + 0.5)), "enemy", e))
        rb = self.rb
        if self.state != "over":
            ents.append((int(math.floor(rb.x + rb.y + 0.5)), "robot", rb))
        ents.sort(key=lambda e: e[0])
        i = 0
        for (x, y) in self.lv.order:
            d = x + y
            while i < len(ents) and ents[i][0] < d:
                self.draw_entity(s, ents[i][1], ents[i][2], ox, oy)
                i += 1
            self.draw_tile(s, x, y, ox, oy)
        while i < len(ents):
            self.draw_entity(s, ents[i][1], ents[i][2], ox, oy)
            i += 1
        for fx, fy, fh, age in self.falling:
            surf, cx0, cy0 = tile_surf(self.theme_i, fh, 0, None, True)
            cx, cy = proj(fx, fy, fh, ox, oy + age * age * 0.45)
            s.blit(surf, (int(cx - cx0), int(cy - cy0)))

    def draw_bg(self, s):
        s.blit(get_bg(LW, self.theme_i), (0, 0))
        th = self.theme
        for i in range(5):
            x = (i * 260 + self.t * 0.25) % (LW + 220) - 110
            y = 40 + (i * 53) % 90
            pygame.draw.ellipse(s, th["cloud"], (int(x), y, 96, 28))
            pygame.draw.ellipse(s, th["cloud"], (int(x) + 22, y - 13, 52, 28))
        ti = self.theme_i
        for i in range(16):
            if ti == 4:
                r = 1 + int(abs(math.sin(self.t / 25 + i)) * 2)
                pygame.draw.circle(s, th["amb"], ((i * 131) % LW, (i * 71) % (LH - 120)), r)
                continue
            vx = (0.5 if ti in (0, 1) else 0.15) * (1 + i % 3)
            vy = {0: 0.3, 1: 0.1, 2: 0.7, 3: -0.6}[ti] * (1 + i % 2)
            pygame.draw.rect(s, th["amb"], (int((i * 131 + self.t * vx) % LW), int((i * 71 + self.t * vy) % LH), 3, 3))

    def draw(self, s, pressed):
        self.draw_bg(s)
        ox, oy = self.origin()
        if self.shake:
            ox += random.randint(-3, 3)
            oy += random.randint(-3, 3)
        if self.state not in ("select", "chars", "help"):
            self.draw_world(s, ox, oy)
        for q in self.parts:
            pygame.draw.rect(s, q[5], (int(q[0]), int(q[1]), q[6], q[6]))
        for q in self.texts:
            text(s, q[2], (int(q[0]), int(q[1])), font, q[4], True)
        st = self.state
        if st == "menu":
            self.draw_menu(s)
        elif st == "select":
            self.draw_select(s)
        elif st == "chars":
            self.draw_chars(s)
        elif st == "help":
            self.draw_help(s)
        elif st == "confirm":
            self.draw_menu(s)
            self.draw_confirm(s)
        else:
            self.draw_hud(s, pressed)
        if self.fade:
            s.blit(overlay(min(255, self.fade * 16)), (0, 0))

    def draw_menu(self, s):
        bob = math.sin(self.t / 20) * 4
        text(s, GAME_NAME, (LW // 2, int(66 + bob)), huge, GOLD, True, 5, True)
        text(s, T("tagline"), (LW // 2, 122), small, (255, 255, 255), True)
        has = self.has_progress()
        r = menu_rects(has)
        if has:
            draw_pill(s, r["cont"], T("continue"), CORAL, "play", T("level_n") % (self.save["level"] + 1))
            draw_pill(s, r["new"], T("newgame"), RED, "new")
        else:
            draw_pill(s, r["cont"], T("play"), CORAL, "play")
        draw_pill(s, r["levels"], T("levels"), BLUE, "list")
        draw_pill(s, r["hero"], T("hero"), GREEN, "star")
        draw_icon_button(s, r["sound"], "sound", not MUTED)
        draw_icon_button(s, r["lang"], "t:" + ("FA" if LANG == "fa" else "EN"))
        draw_icon_button(s, r["help"], "t:?")
        if self.toast:
            draw_panel(s, pygame.Rect(LW // 2 - 260, 318, 520, 30), (120, 30, 30), 220, 10)
            text(s, T("font_missing"), (LW // 2, 333), small, (255, 255, 255), True, 1)

    def draw_help(self, s):
        name, sub, rows = HELP_PAGES[self.help_page]
        r = help_rects()
        draw_icon_button(s, r["back"], "back")
        draw_icon_button(s, r["lang"], "t:" + ("FA" if LANG == "fa" else "EN"))
        text(s, T("help_title"), (LW // 2, 30), mid, GOLD, True, 3, True)
        text(s, T(name), (LW // 2, 64), font, (255, 255, 255), True)
        if sub:
            text(s, T(sub), (LW // 2, 84), small, (255, 235, 180), True, 1)
        rtl = LANG == "fa"
        rw = min(LW - 40, 660)
        x0 = (LW - rw) // 2
        y = 100
        for icon, tk, dk in rows:
            box = pygame.Rect(x0, y, rw, 66)
            draw_panel(s, box, (14, 22, 40), 205, 14)
            ix = box.right - 40 if rtl else box.x + 40
            draw_help_icon(s, icon, ix, box.centery, self.t)
            tx = box.right - 80 if rtl else box.x + 80
            desc = T(dk) if isinstance(dk, str) else T("unlock_n") % dk
            text(s, T(tk), (tx, box.y + 6), font, GOLD, False, 1, False, rtl)
            for j, ln in enumerate(wrap(desc, small, rw - 100)[:2]):
                text(s, ln, (tx, box.y + 33 + j * 18), small, (255, 255, 255), False, 1, False, rtl)
            y += 70
        draw_pill(s, r["prev"], "", BLUE)
        draw_icon(s, "back", r["prev"].centerx, r["prev"].centery, 10)
        draw_pill(s, r["next"], "", BLUE)
        draw_icon(s, "next", r["next"].centerx, r["next"].centery, 10)
        for i in range(len(HELP_PAGES)):
            pygame.draw.circle(s, GOLD if i == self.help_page else (90, 100, 120), (LW // 2 - 40 + i * 16, 412), 5)

    def draw_chars(self, s):
        text(s, T("choose_hero"), (LW // 2, 50), big, GOLD, True, 3, True)
        r = chars_rects()
        draw_icon_button(s, r["back"], "back")
        cleared = self.save["level"]
        for i, c in enumerate(r["cards"]):
            ch = CHARS[i]
            ok = cleared >= ch["unlock"]
            draw_panel(s, c, (14, 22, 40), 215, 18)
            if i == self.char:
                pygame.draw.rect(s, GOLD, c, 4, border_radius=18)
            bob = int(math.sin(self.t / 12 + i) * 4) if ok else 0
            s.blit(char_sprite(i, 5, False, not ok), (c.centerx - 40, c.y + 24 + bob))
            text(s, T("char_" + ch["name"]), (c.centerx, c.y + 150), mid, (255, 255, 255), True)
            if not ok:
                draw_icon(s, "lock", c.centerx, c.y + 188, 10, (235, 235, 240))
                text(s, T("clear_n") % ch["unlock"], (c.centerx, c.y + 224), small, (255, 220, 160), True)
            else:
                text(s, T("selected") if i == self.char else T("tap_pick"), (c.centerx, c.y + 200), small,
                     GOLD if i == self.char else (255, 255, 255), True)

    def draw_confirm(self, s):
        s.blit(overlay(150), (0, 0))
        r = confirm_rects()
        draw_panel(s, r["panel"], (14, 22, 40), 235)
        p = r["panel"]
        text(s, T("confirm_title"), (p.centerx, p.y + 44), mid, GOLD, True)
        text(s, T("confirm_sub"), (p.centerx, p.y + 92), font, (255, 255, 255), True)
        draw_pill(s, r["yes"], T("yes_reset"), RED)
        draw_pill(s, r["no"], T("cancel"), BLUE)

    def draw_select(self, s):
        th = THEMES[self.page % len(THEMES)]
        text(s, T("select_title"), (LW // 2, 50), big, GOLD, True, 3, True)
        text(s, T("world") % (self.page + 1, T("w_" + th["name"])), (LW // 2, 92), font, (255, 255, 255), True)
        r = select_rects()
        maxpage = (self.save["unlocked"] - 1) // 10
        draw_icon_button(s, r["back"], "back")
        draw_icon_button(s, r["sound"], "sound", not MUTED)
        if self.page > 0:
            draw_pill(s, r["prev"], "", BLUE, None)
            draw_icon(s, "back", r["prev"].centerx, r["prev"].centery, 11)
        if self.page < maxpage:
            draw_pill(s, r["next"], "", BLUE, None)
            draw_icon(s, "next", r["next"].centerx, r["next"].centery, 11)
        for i, c in enumerate(r["cells"]):
            n = self.page * 10 + i
            if n < self.save["unlocked"]:
                draw_pill(s, c, str(n + 1), darken(th["tiles"][1], 0.15), None, None, big)
                best = self.save["best"].get(str(n))
                total = count_coins(rows_for(n))
                k = 0 if best is None else (3 if best >= total else (2 if best / max(1, total) >= 0.5 else 1))
                for j in range(3):
                    draw_star(s, c.centerx - 22 + j * 22, c.bottom - 18, 8, GOLD if j < k else (70, 78, 92))
            else:
                draw_pill(s, c, "", (110, 120, 135))
                draw_icon(s, "lock", c.centerx, c.centery - 6, 12, (235, 235, 240))
        text(s, "%d / %d" % (self.page + 1, maxpage + 1), (LW // 2, 352), small, (255, 255, 255), True)

    def draw_card(self, s, title, color, lines, stars=None, hint=None):
        s.blit(overlay(120), (0, 0))
        panel = pygame.Rect(LW // 2 - 190, 96, 380, 250)
        draw_panel(s, panel, (14, 22, 40), 230)
        text(s, title, (panel.centerx, panel.y + 46), big, color, True, 3, True)
        y = panel.y + 96
        if stars is not None:
            for j in range(3):
                draw_star(s, panel.centerx - 54 + j * 54, y + 12, 22, GOLD if j < stars else (70, 78, 92))
            y += 56
        for ln in lines:
            text(s, ln, (panel.centerx, y), font, (255, 255, 255), True)
            y += 32
        if hint:
            text(s, hint, (panel.centerx, panel.bottom - 28), small, (255, 245, 200), True)

    def draw_hud(self, s, pressed):
        th = self.theme["tiles"][1]
        pc = darken(th, 0.75)
        pygame.draw.circle(s, DARK, (38, 38), 30)
        pygame.draw.circle(s, th, (38, 38), 27)
        pygame.draw.circle(s, GOLD, (38, 38), 27, 3)
        text(s, str(self.idx + 1), (38, 40), mid if self.idx < 99 else font, (255, 255, 255), True, 2, True)
        draw_panel(s, pygame.Rect(72, 14, 118, 36), pc, 190, 18)
        draw_icon(s, "coin", 92, 32, 11 + (3 if self.pulse else 0))
        text(s, "%d/%d" % (self.got, len(self.lv.coins)), (108, 22), font, GOLD)
        n = max(3, self.lives)
        pr = pygame.Rect(LW // 2 - (n * 34 + 16) // 2, 10, n * 34 + 16, 40)
        draw_panel(s, pr, pc, 190, 18)
        for k in range(n):
            col = (235, 70, 80) if k < self.lives else (66, 56, 66)
            draw_heart(s, pr.x + 26 + k * 34, 28, 10, col)
        y = 70
        if self.keys or self.lv.keys or self.lv.doors:
            draw_key_icon(s, 28, y, 11)
            text(s, "x%d" % self.keys, (46, y - 10), font, GOLD)
            y += 28
        for kind, val, mx in (("shield", self.rb.shield, 480), ("haste", self.haste, 420), ("freeze", self.freeze, 300)):
            if val:
                draw_item_icon(s, kind, 28, y, 10)
                pygame.draw.rect(s, (20, 25, 40), (46, y - 5, 84, 10), border_radius=5)
                pygame.draw.rect(s, ITEM_COL[kind], (46, y - 5, int(84 * val / mx), 10), border_radius=5)
                y += 28
        r = play_rects()
        draw_icon_button(s, r["menu"], "menu")
        draw_icon_button(s, r["sound"], "sound", not MUTED)
        if self.tick < self.intro:
            text(s, T("level_big") % (self.idx + 1), (LW // 2, 130), huge, GOLD, True, 4, True)
            text(s, T("world") % (self.idx // 10 + 1, T("w_" + self.theme["name"])), (LW // 2, 180), mid,
                 (255, 255, 255), True)
        elif self.hint and self.tick < 420 and self.state == "play":
            draw_panel(s, pygame.Rect(LW // 2 - 250, 62, 500, 36), pc, 200, 12)
            text(s, T(self.hint), (LW // 2, 80), font, (255, 255, 255), True)
        for k in ("UL", "UR", "DL", "DR"):
            s.blit(dpad_surface(VEC[k], BTN[k].w, pressed.get(k, False)), BTN[k].topleft)
        s.blit(leap_surface(BTN["LEAP"].w, pressed.get("LEAP", False)), BTN["LEAP"].topleft)
        if self.flash:
            s.blit(overlay(self.flash * 9, (255, 40, 40)), (0, 0))
        if self.state == "over":
            self.draw_card(s, T("out_lives"), (255, 110, 110), [T("coins") % (self.got, len(self.lv.coins))], None,
                           T("tap_retry") if self.timer > 40 else None)
        elif self.state == "clear":
            self.draw_card(s, T("clear"), GOLD, [T("coins") % (self.got, len(self.lv.coins)), T("score") % self.score],
                           self.stars, T("tap_next") if self.timer > 25 else None)


# ---------------------------------------------------------------- main
def set_width(w):
    global LW, view
    if w != LW:
        LW = w
        view = pygame.Surface((LW, LH))
    BTN["LEAP"].x = LW - 132


def main():
    set_width(LW)
    win0 = pygame.display.get_surface()
    win0.fill((20, 25, 40))
    text(win0, "Loading...", (win0.get_width() // 2, win0.get_height() // 2),
         font, (255, 255, 255), True)
    pygame.display.flip()
    init_audio()
    init_fa_fonts()
    game = Game()
    fingers = {}
    prev_leap = False
    last_tap = (-1000, (0, 0))
    running = True
    acc, last_t = 0.0, pygame.time.get_ticks()
    pend_taps, pend_conf, pend_edge = [], False, False
    while running:
        win = pygame.display.get_surface()
        ww, wh = win.get_size()
        portrait = wh > ww
        ew, eh = (wh, ww) if portrait else (ww, wh)
        set_width(max(640, min(1100, int(LH * ew / eh))))
        sw, sh = (LH, LW) if portrait else (LW, LH)
        scale = min(ww / sw, wh / sh)
        ox, oy = (ww - sw * scale) / 2, (wh - sh * scale) / 2

        def to_view(px, py):
            rx, ry = (px - ox) / scale, (py - oy) / scale
            if not portrait:
                return int(rx), int(ry)
            if PORTRAIT_ROTATE < 0:
                return int(ry), int(LH - rx)
            return int(LW - ry), int(rx)

        taps = []
        confirm = back = False

        def add_tap(p):
            nonlocal last_tap
            now = pygame.time.get_ticks()
            lt, lp = last_tap
            if now - lt < 300 and abs(p[0] - lp[0]) < 40 and abs(p[1] - lp[1]) < 40:
                return
            last_tap = (now, p)
            taps.append(p)

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    back = True
                elif e.key == pygame.K_RETURN:
                    confirm = True
            elif e.type in (pygame.FINGERDOWN, pygame.FINGERMOTION):
                fingers[e.finger_id] = to_view(e.x * ww, e.y * wh)
                if e.type == pygame.FINGERDOWN:
                    add_tap(fingers[e.finger_id])
            elif e.type == pygame.FINGERUP:
                fingers.pop(e.finger_id, None)
            elif e.type == pygame.MOUSEBUTTONDOWN:
                add_tap(to_view(*e.pos))
        if back and game.back():
            running = False

        pts = list(fingers.values())
        if pygame.mouse.get_pressed()[0]:
            pts.append(to_view(*pygame.mouse.get_pos()))
        keys = pygame.key.get_pressed()
        pressed = {k: any(BTN[k].collidepoint(q) for q in pts) for k in BTN}
        pressed["UL"] = pressed["UL"] or keys[pygame.K_q]
        pressed["UR"] = pressed["UR"] or keys[pygame.K_e]
        pressed["DL"] = pressed["DL"] or keys[pygame.K_a]
        pressed["DR"] = pressed["DR"] or keys[pygame.K_d]
        pressed["LEAP"] = pressed["LEAP"] or keys[pygame.K_SPACE]
        direction = None
        for k in ("UL", "UR", "DL", "DR"):
            if pressed[k]:
                direction = DIRS[k]
                break
        leap_edge = pressed["LEAP"] and not prev_leap
        prev_leap = pressed["LEAP"]

        now = pygame.time.get_ticks()
        acc += min(100, now - last_t)
        last_t = now
        pend_taps += taps
        pend_conf = pend_conf or confirm
        pend_edge = pend_edge or leap_edge
        steps = 0
        while acc >= 16.6 and steps < 3:
            game.update(direction, pend_edge, pressed["LEAP"], pend_taps, pend_conf)
            pend_taps, pend_conf, pend_edge = [], False, False
            acc -= 16.6
            steps += 1
        game.draw(view, pressed)

        src = pygame.transform.rotate(view, PORTRAIT_ROTATE) if portrait else view
        win.fill((0, 0, 0))
        size = (int(sw * scale), int(sh * scale))
        win.blit(pygame.transform.scale(src, size), (int(ox), int(oy)))
        pygame.display.flip()
        clock.tick(60)
    pygame.quit()


main()
