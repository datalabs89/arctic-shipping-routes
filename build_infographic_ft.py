import os
import math
import json
import shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont

out_dir = r"C:\Users\User\ArcticShippingRoute"
os.makedirs(out_dir, exist_ok=True)
artifact_dir = r"C:\Users\User\.gemini\antigravity-cli\brain\d707f0b4-74df-4408-8b6b-21491274467b"

# 1. Canvas and Globe Geometry
# Elegant widescreen editorial infographic layout
WIDTH = 2700
HEIGHT = 1920
CX = 1445
CY = 820
RADIUS = 615

LAT_0 = 30.0
LON_0 = 55.0

phi0 = math.radians(LAT_0)
lam0 = math.radians(LON_0)

def ortho_project(lon, lat):
    """Orthographic forward projection from (lon, lat) to (x, y) normalized [-1, 1]"""
    phi = math.radians(lat)
    lam = math.radians(lon)
    dlam = lam - lam0
    cos_c = math.sin(phi0) * math.sin(phi) + math.cos(phi0) * math.cos(phi) * math.cos(dlam)
    if cos_c < -0.01:
        return None, None, False
    x = math.cos(phi) * math.sin(dlam)
    y = math.cos(phi0) * math.sin(phi) - math.sin(phi0) * math.cos(phi) * math.cos(dlam)
    dist2 = x**2 + y**2
    if dist2 > 1.02:
        return None, None, False
    return x, y, True

def to_pixel(x, y):
    return CX + x * RADIUS, CY - y * RADIUS

# 2. Build FT Earth Texture
print("Rendering Financial Times Earth texture...")
img_topo = Image.open(os.path.join(out_dir, "land_topo_2048.jpg")).convert("RGB")
img_winter = Image.open(os.path.join(out_dir, "earth_5400.jpg")).resize(img_topo.size).convert("RGB")

arr_topo = np.array(img_topo, dtype=np.float32)
arr_winter = np.array(img_winter, dtype=np.float32)
src_h, src_w, _ = arr_topo.shape

y_idx, x_idx = np.indices((HEIGHT, WIDTH))
nx = (x_idx - CX) / RADIUS
ny = -(y_idx - CY) / RADIUS

rho2 = nx**2 + ny**2
disk_mask = rho2 <= 1.00
rho = np.sqrt(np.where(disk_mask, rho2, 0.0))
rho_safe = np.where(rho == 0, 1e-9, rho)

cos_c = np.sqrt(np.maximum(0.0, 1.0 - np.where(disk_mask, rho2, 0.0)))
sin_c = rho

lat = np.arcsin(np.clip(cos_c * np.sin(phi0) + (ny * sin_c * np.cos(phi0) / rho_safe), -1.0, 1.0))
lon = lam0 + np.arctan2(nx * sin_c, rho_safe * np.cos(phi0) * cos_c - ny * np.sin(phi0) * sin_c)
lon = (lon + np.pi) % (2 * np.pi) - np.pi

src_px = np.clip(((lon + np.pi) / (2 * np.pi) * (src_w - 1)).astype(np.int32), 0, src_w - 1)
src_py = np.clip(((np.pi / 2 - lat) / np.pi * (src_h - 1)).astype(np.int32), 0, src_h - 1)

sampled_topo = arr_topo[src_py, src_px]
sampled_winter = arr_winter[src_py, src_px]

lat_deg = np.degrees(lat)
lon_deg = np.degrees(lon)

is_ocean = (sampled_topo[:, :, 2] > sampled_topo[:, :, 0] + 10) & (sampled_topo[:, :, 1] < 90)

ice_weight = np.clip((lat_deg - 66.0) / 8.0, 0.0, 1.0)
is_greenland = (lat_deg > 58.0) & (lat_deg < 84.0) & (lon_deg > -55.0) & (lon_deg < -15.0)
ice_weight = np.where(is_greenland, 1.0, ice_weight)

winter_brightness = (sampled_winter[:, :, 0] + sampled_winter[:, :, 1] + sampled_winter[:, :, 2]) / 3.0
is_snow = winter_brightness > 130
effective_ice_weight = ice_weight * np.where(is_snow, 1.0, 0.20)

# Colors
FT_BG = np.array([255, 241, 229], dtype=np.float32)       # #FFF1E5
FT_OCEAN = np.array([214, 229, 238], dtype=np.float32)    # #D6E5EE
FT_LAND_BASE = np.array([224, 219, 210], dtype=np.float32)# #E0DBD2
FT_ICE = np.array([248, 250, 252], dtype=np.float32)      # #F8FAFC

land_lum = (sampled_topo[:, :, 0] * 0.299 + sampled_topo[:, :, 1] * 0.587 + sampled_topo[:, :, 2] * 0.114)
relief = np.clip(land_lum / 120.0, 0.75, 1.25)

ft_texture = np.zeros((HEIGHT, WIDTH, 3), dtype=np.float32)
for c in range(3):
    land_col = FT_LAND_BASE[c] * (0.80 + 0.20 * relief)
    ocean_col = FT_OCEAN[c] * (0.96 + 0.04 * cos_c)
    base_val = np.where(is_ocean, ocean_col, land_col)
    blended_val = np.where(effective_ice_weight > 0.05,
                           base_val * (1.0 - effective_ice_weight) + FT_ICE[c] * effective_ice_weight,
                           base_val)
    ft_texture[:, :, c] = blended_val

globe_shading = np.clip(0.65 + 0.35 * (cos_c**0.25), 0.65, 1.0)
ft_texture *= globe_shading[:, :, np.newaxis]

canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.float32)
canvas[:, :, :] = FT_BG
canvas[disk_mask] = ft_texture[disk_mask]

base_img = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), mode="RGB")

# Crisp globe rim (Pure flat, no halo)
rim_draw = ImageDraw.Draw(base_img)
rim_draw.ellipse([CX - RADIUS, CY - RADIUS, CX + RADIUS, CY + RADIUS],
                 outline=(160, 145, 135), width=2)

# Graticule Lines (Parallels & Meridians every 30°)
graticule_img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
grat_draw = ImageDraw.Draw(graticule_img)
GRAT_COLOR = (140, 165, 185, 85)

for grat_lat in range(-60, 85, 30):
    grat_pts = []
    for grat_lon in range(-180, 181, 2):
        x, y, vis = ortho_project(grat_lon, grat_lat)
        if vis and x is not None:
            grat_pts.append(to_pixel(x, y))
        else:
            if len(grat_pts) > 1: grat_draw.line(grat_pts, fill=GRAT_COLOR, width=1)
            grat_pts = []
    if len(grat_pts) > 1: grat_draw.line(grat_pts, fill=GRAT_COLOR, width=1)

for grat_lon in range(-180, 181, 30):
    grat_pts = []
    for grat_lat in range(-80, 85, 2):
        x, y, vis = ortho_project(grat_lon, grat_lat)
        if vis and x is not None:
            grat_pts.append(to_pixel(x, y))
        else:
            if len(grat_pts) > 1: grat_draw.line(grat_pts, fill=GRAT_COLOR, width=1)
            grat_pts = []
    if len(grat_pts) > 1: grat_draw.line(grat_pts, fill=GRAT_COLOR, width=1)

base_img.paste(graticule_img, (0, 0), graticule_img)

# 3. Routes & Densification
with open(os.path.join(out_dir, "northern_sea_route.geojson"), "r") as f:
    nsr_coords = json.load(f)["features"][0]["geometry"]["coordinates"]

with open(os.path.join(out_dir, "suez_route.geojson"), "r") as f:
    suez_coords = json.load(f)["features"][0]["geometry"]["coordinates"]

with open(os.path.join(out_dir, "cape_route.geojson"), "r") as f:
    cape_coords = json.load(f)["features"][0]["geometry"]["coordinates"]

def interpolate_dense(coords, steps=35):
    fine = []
    for i in range(len(coords) - 1):
        p1, p2 = coords[i], coords[i+1]
        dlon = p2[0] - p1[0]
        if dlon > 180: dlon -= 360
        elif dlon < -180: dlon += 360
        for s in range(steps):
            t = s / float(steps)
            lo = p1[0] + t * dlon
            if lo > 180: lo -= 360
            elif lo < -180: lo += 360
            la = p1[1] + t * (p2[1] - p1[1])
            fine.append((lo, la))
    fine.append(coords[-1])
    return fine

nsr_dense = interpolate_dense(nsr_coords, 35)
suez_dense = interpolate_dense(suez_coords, 35)
cape_dense = interpolate_dense(cape_coords, 35)

def project_list(coords):
    res = []
    for lo, la in coords:
        x, y, vis = ortho_project(lo, la)
        if vis and x is not None:
            res.append(to_pixel(x, y))
    return res

nsr_px = project_list(nsr_dense)
suez_px = project_list(suez_dense)
cape_px = project_list(cape_dense)

# 4. Overlay & Drawing
overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
draw = ImageDraw.Draw(overlay)

# Route Colors
FT_RED = (205, 18, 55, 255)       # Northern Sea Route
FT_NAVY = (12, 80, 142, 255)      # Suez Canal Route
FT_AMBER = (218, 105, 18, 255)    # Cape of Good Hope Route

# Pure Solid Flat Lines (No casing, no glow, no effects)
ROUTE_WIDTH = 5
draw.line(cape_px, fill=FT_AMBER, width=ROUTE_WIDTH, joint="curve")
draw.line(suez_px, fill=FT_NAVY, width=ROUTE_WIDTH, joint="curve")
draw.line(nsr_px, fill=FT_RED, width=ROUTE_WIDTH, joint="curve")

# Clean Flat Arrow Chevrons
def draw_arrows(px_list, color, fractions, size=13):
    for f in fractions:
        idx = int(len(px_list) * f)
        if idx < len(px_list) - 5:
            p1 = px_list[idx]
            p2 = px_list[idx + 5]
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            dist = math.hypot(dx, dy)
            if dist > 0:
                ux, uy = dx / dist, dy / dist
                vx, vy = -uy, ux
                tip = p2
                left_w = (tip[0] - size * ux + size * 0.55 * vx, tip[1] - size * uy + size * 0.55 * vy)
                right_w = (tip[0] - size * ux - size * 0.55 * vx, tip[1] - size * uy - size * 0.55 * vy)
                draw.polygon([tip, left_w, right_w], fill=color)

draw_arrows(nsr_px, FT_RED, [0.08, 0.22, 0.48, 0.70, 0.88], size=13)
draw_arrows(suez_px, FT_NAVY, [0.15, 0.45, 0.75], size=12)
draw_arrows(cape_px, FT_AMBER, [0.18, 0.42, 0.65, 0.85], size=12)

# Port Markers
xj, yj, _ = ortho_project(106.88, -6.10)
pxj, pyj = to_pixel(xj, yj)
draw.ellipse([pxj - 10, pyj - 10, pxj + 10, pyj + 10], fill=(255, 255, 255, 255), outline=(30, 30, 35), width=3)
draw.ellipse([pxj - 5, pyj - 5, pxj + 5, pyj + 5], fill=FT_RED)

xcape, ycape, _ = ortho_project(18.5, -34.5)
pxcape, pycape = to_pixel(xcape, ycape)
draw.ellipse([pxcape - 7, pycape - 7, pxcape + 7, pycape + 7], fill=FT_AMBER, outline=(255, 255, 255, 255), width=2)

xuk, yuk, _ = ortho_project(-1.15, 54.60)
pxuk, pyuk = to_pixel(xuk, yuk)
draw.ellipse([pxuk - 10, pyuk - 10, pxuk + 10, pyuk + 10], fill=(255, 255, 255, 255), outline=FT_RED, width=3)
draw.ellipse([pxuk - 4, pyuk - 4, pxuk + 4, pyuk + 4], fill=(30, 30, 35))

# 5. Typography Definitions
font_brand = ImageFont.truetype("arialbd.ttf", 15)
font_kicker = ImageFont.truetype("arialbd.ttf", 15)
font_title = ImageFont.truetype("georgiab.ttf", 36)
font_subtitle = ImageFont.truetype("georgia.ttf", 19)
font_section_h1 = ImageFont.truetype("georgiab.ttf", 22)
font_section_h2 = ImageFont.truetype("georgiab.ttf", 18)
font_body = ImageFont.truetype("arial.ttf", 15)
font_body_bold = ImageFont.truetype("arialbd.ttf", 15)
font_callout_bold = ImageFont.truetype("arialbd.ttf", 17)
font_callout_sub = ImageFont.truetype("arial.ttf", 14)
font_tag = ImageFont.truetype("arialbd.ttf", 12)

font_country = ImageFont.truetype("georgiab.ttf", 20)
font_country_large = ImageFont.truetype("georgiab.ttf", 26)
font_water = ImageFont.truetype("georgiai.ttf", 17)

# 6. Top Header Banner (Classic FT Broadsheet style)
draw.text((70, 45), "FINANCIAL TIMES", font=font_brand, fill=(155, 35, 50, 255))
draw.line([(70, 70), (480, 70)], fill=(185, 160, 145, 255), width=1)
draw.text((70, 82), "INFOGRAPHIC REPORT • GLOBAL MARITIME GEOPOLITICS", font=font_kicker, fill=(120, 95, 80, 255))
draw.text((70, 106), "The Equatorial Dilemma: Jakarta to Europe Shipping Routes", font=font_title, fill=(20, 20, 25, 255))
draw.text((70, 154), "Evaluating transit speed, geopolitical risks, and economic realities across the Arctic, Suez, and the Cape of Good Hope", font=font_subtitle, fill=(85, 75, 70, 255))
draw.line([(70, 192), (WIDTH - 70, 192)], fill=(210, 190, 175, 255), width=2)

# Helper to draw Storytelling Insight Panels
def draw_story_card(pos, tag, title, body_paragraphs, accent_color, width=640, height=270):
    x, y = pos
    # Card base
    draw.rounded_rectangle([x, y, x + width, y + height], radius=6,
                           fill=(255, 255, 255, 245), outline=(215, 195, 180, 255), width=1)
    # Left accent bar
    draw.rounded_rectangle([x, y, x + 6, y + height], radius=3, fill=accent_color)
    
    # Category Tag Pill
    tag_w = draw.textlength(tag, font=font_tag) + 16
    draw.rounded_rectangle([x + 20, y + 16, x + 20 + tag_w, y + 36], radius=4,
                           fill=accent_color)
    draw.text((x + 28, y + 19), tag, font=font_tag, fill=(255, 255, 255, 255))
    
    # Title
    draw.text((x + 20, y + 46), title, font=font_section_h2, fill=(20, 20, 25, 255))
    
    # Paragraph text
    curr_y = y + 78
    for line in body_paragraphs:
        if line.startswith("**"):
            # Bold highlight line
            draw.text((x + 20, curr_y), line.replace("**", ""), font=font_body_bold, fill=accent_color)
            curr_y += 22
        else:
            draw.text((x + 20, curr_y), line, font=font_body, fill=(65, 60, 55, 255))
            curr_y += 21

# LEFT COLUMN: 4 Storytelling Insight Panels (width=640, x=70)
# Card 1: The Distance Paradox
draw_story_card(
    pos=(70, 220),
    tag="KEY INSIGHT 1 • THE DISTANCE PARADOX",
    title="Why the Arctic Thaw Yields Zero Nautical Mile Gain",
    body_paragraphs=[
        "For East Asian ports like Shanghai or Yokohama, the Northern Sea Route",
        "cuts transit by up to 4,000 nm (~35%). However, departing from Jakarta,",
        "**the NSR offers ZERO distance savings over the Suez Canal (both ~8,400 nm).**",
        "Indonesian vessels must spend 9–11 days sailing 3,500 nm northward through",
        "the South China Sea and Sea of Japan just to reach the Arctic entrance."
    ],
    accent_color=FT_RED,
    width=640, height=210
)

# Card 2: The Suez & Red Sea Bottleneck
draw_story_card(
    pos=(70, 455),
    tag="KEY INSIGHT 2 • THE RED SEA DILEMMA",
    title="Speed vs Security: The Vulnerability of Global Chokepoints",
    body_paragraphs=[
        "The Suez corridor remains Southeast Asia's historical maritime highway,",
        "offering a standard transit of 28–32 days at a steady 14 knots.",
        "**Escalating security threats near Bab-el-Mandeb have surged insurance costs,**",
        "forcing container lines to weigh severe war-risk premiums against",
        "the immense scheduling delays of circumnavigating the African continent."
    ],
    accent_color=FT_NAVY,
    width=640, height=210
)

# Card 3: The 12-Day Cape Penalty
draw_story_card(
    pos=(70, 690),
    tag="KEY INSIGHT 3 • THE CAPE PENALTY",
    title="Circumnavigation: +3,200 Nautical Miles & +40% Fuel Burn",
    body_paragraphs=[
        "Diverting south of Africa completely bypasses Middle Eastern flashpoints",
        "but exacts a staggering logistical toll:",
        "**Adds 10 to 14 extra voyage days and +3,200 nm (+38% total distance).**",
        "Vessels consume ~40% additional bunker fuel and must navigate violent",
        "swells and winter gale fronts off the Cape of Good Hope (Roaring Forties)."
    ],
    accent_color=FT_AMBER,
    width=640, height=210
)

# Card 4: The 90-Day Seasonal Trap
draw_story_card(
    pos=(70, 925),
    tag="KEY INSIGHT 4 • THE OPERATIONAL WINDOW",
    title="The Arctic Fallacy: A 90-Day Window with Ice Escort Fees",
    body_paragraphs=[
        "While polar ice cap melt captures headlines, commercial NSR transit is",
        "restricted to a brief summer window (July–October).",
        "**Transit requires specialized Arc4/Arc7 ice-class hulls & Rosatomflot fees,**",
        "canceling out operational savings. For equatorial supply chains, Suez and",
        "the Cape remain the only reliable, year-round maritime options."
    ],
    accent_color=(140, 40, 80, 255),
    width=640, height=210
)

# LEFT COLUMN SUMMARY: Strategic Takeaways Box
draw.rounded_rectangle([70, 1160, 710, 1430], radius=6, fill=(248, 243, 235, 255), outline=(205, 185, 170, 255), width=1)
draw.text((95, 1180), "STRATEGIC LOGISTICS TAKEAWAYS", font=font_section_h2, fill=(25, 25, 30, 255))
draw.line([(95, 1208), (685, 1208)], fill=(210, 190, 175, 255), width=1)
takeaways = [
    ("• Standard Baseline:", "Suez Route is optimum for speed (28–32 d) when secure."),
    ("• Crisis Buffer:", "Cape Route adds 12 days & +$1M+ in fuel per round-trip."),
    ("• Arctic Reality:", "NSR is non-viable for Jakarta year-round container loops.")
]
ty = 1225
for label, desc in takeaways:
    draw.text((95, ty), label, font=font_body_bold, fill=(20, 20, 25, 255))
    draw.text((250, ty), desc, font=font_body, fill=(75, 70, 65, 255))
    ty += 32

# RIGHT COLUMN: Route Metric Cards (x=2170 to 2630, width=460)
def draw_route_card(pos, title, metrics, badge_color, width=460, height=195):
    x, y = pos
    draw.rounded_rectangle([x, y, x + width, y + height], radius=6,
                           fill=(255, 255, 255, 248), outline=(215, 195, 180, 255), width=1)
    draw.rounded_rectangle([x, y, x + width, y + 6], radius=3, fill=badge_color)
    
    draw.ellipse([x + 20, y + 20, x + 32, y + 32], fill=badge_color)
    draw.text((x + 40, y + 16), title, font=font_section_h2, fill=(20, 20, 25, 255))
    
    curr_y = y + 54
    for label, val, is_alert in metrics:
        draw.text((x + 20, curr_y), label, font=font_body, fill=(105, 95, 90, 255))
        val_color = badge_color if is_alert else (25, 25, 30, 255)
        draw.text((x + 130, curr_y), val, font=font_body_bold, fill=val_color)
        curr_y += 26

# Right Card 1: NSR
draw_route_card(
    pos=(2170, 220),
    title="Northern Sea Route (NSR)",
    metrics=[
        ("Total Distance:", "± 8,400 nm (~15,550 km)", False),
        ("Est. Transit:", "± 27 – 30 Days", False),
        ("Navigability:", "July – Oct (90-Day Window)", True),
        ("Key Chokepoint:", "Bering & Vilkitsky Straits (Ice floes)", False),
        ("Economic Cost:", "Arc-hull premium + Icebreaker fees", False)
    ],
    badge_color=FT_RED,
    width=460, height=205
)

# Right Card 2: Suez
draw_route_card(
    pos=(2170, 460),
    title="Suez Canal Route",
    metrics=[
        ("Total Distance:", "± 8,400 nm (~15,550 km)", False),
        ("Est. Transit:", "± 28 – 32 Days", False),
        ("Navigability:", "Year-Round (12 Months)", False),
        ("Key Chokepoint:", "Bab-el-Mandeb & Suez Canal", True),
        ("Economic Cost:", "Canal toll tariffs + War risk premiums", False)
    ],
    badge_color=FT_NAVY,
    width=460, height=205
)

# Right Card 3: Cape
draw_route_card(
    pos=(2170, 700),
    title="Cape of Good Hope Route",
    metrics=[
        ("Total Distance:", "± 11,600 nm (+3,200 nm)", True),
        ("Est. Transit:", "± 38 – 43 Days (+10–14 d)", True),
        ("Navigability:", "Year-Round (12 Months)", False),
        ("Key Chokepoint:", "Cape Agulhas & Roaring Forties", False),
        ("Economic Cost:", "+35–40% Bunker Fuel Consumption", True)
    ],
    badge_color=FT_AMBER,
    width=460, height=205
)

# Right Card 4: Methodological Note
draw.rounded_rectangle([2170, 940, 2630, 1180], radius=6, fill=(255, 255, 255, 240), outline=(215, 195, 180, 255), width=1)
draw.text((2190, 960), "CARTOGRAPHIC SPECIFICATIONS", font=font_section_h2, fill=(25, 25, 30, 255))
draw.line([(2190, 988), (2610, 988)], fill=(210, 190, 175, 255), width=1)
specs = [
    ("Projection:", "Azimuthal Orthographic (3D Globe)"),
    ("Vantage Center:", "30.0° N, 55.0° E"),
    ("Origin Port:", "Tanjung Priok, Jakarta (-6.10° S, 106.88° E)"),
    ("Destination:", "Teesport, United Kingdom (54.60° N, -1.15° W)"),
    ("Speed Model:", "14.5 kts cruising; 9.5 kts ice transit")
]
sy = 1005
for label, val in specs:
    draw.text((2190, sy), label, font=font_body_bold, fill=(90, 80, 75, 255))
    draw.text((2310, sy), val, font=font_body, fill=(40, 40, 45, 255))
    sy += 25

# Starting Point: Jakarta Callout
draw.line([(pxj, pyj), (pxj + 45, pyj + 30), (pxj + 90, pyj + 30)], fill=(40, 40, 45, 255), width=2)
draw.text((pxj + 100, pyj + 10), "STARTING POINT", font=font_callout_bold, fill=FT_RED)
draw.text((pxj + 100, pyj + 30), "Jakarta, Indonesia", font=font_callout_bold, fill=(25, 25, 30, 255))
draw.text((pxj + 100, pyj + 50), "Port of Tanjung Priok", font=font_callout_sub, fill=(90, 80, 75, 255))

# Destination Point: UK Callout
draw.line([(pxuk, pyuk), (pxuk - 40, pyuk - 30), (pxuk - 85, pyuk - 30)], fill=(40, 40, 45, 255), width=2)
draw.text((pxuk - 275, pyuk - 75), "DESTINATION", font=font_callout_bold, fill=FT_RED)
draw.text((pxuk - 275, pyuk - 55), "Teesport, United Kingdom", font=font_callout_bold, fill=(25, 25, 30, 255))
draw.text((pxuk - 275, pyuk - 35), "Western European Terminal", font=font_callout_sub, fill=(90, 80, 75, 255))

# Cape of Good Hope label
draw.text((pxcape - 170, pycape + 15), "Cape of Good Hope\n(South Africa)", font=font_water, fill=(130, 75, 20, 240))

# Geographic Country Labels on Globe
countries = [
    ("RUSSIA", 90.0, 60.0, font_country_large),
    ("CHINA", 104.0, 34.0, font_country),
    ("INDIA", 79.0, 21.0, font_country),
    ("SAUDI\nARABIA", 44.0, 23.0, font_country),
    ("AFRICA", 22.0, 4.0, font_country_large),
    ("INDONESIA", 118.0, -3.5, font_country),
    ("JAPAN", 142.0, 33.0, font_country)
]

for name, lo, la, f in countries:
    x, y, vis = ortho_project(lo, la)
    if vis and x is not None:
        px, py = to_pixel(x, y)
        draw.text((px - 35, py - 12), name, font=f, fill=(80, 70, 65, 220))

waters = [
    ("Bering Strait", -169.0, 66.0),
    ("Red Sea", 38.0, 19.0),
    ("Suez Canal", 32.5, 31.0),
    ("Indian Ocean", 78.0, -10.0),
    ("Atlantic Ocean", -5.0, -15.0),
]

for name, lo, la in waters:
    x, y, vis = ortho_project(lo, la)
    if vis and x is not None:
        px, py = to_pixel(x, y)
        draw.text((px - 30, py - 8), name, font=font_water, fill=(65, 105, 135, 220))

# 7. BOTTOM COMPARATIVE STRIP: 3 Comparative Data Pillars
draw.line([(70, 1475), (WIDTH - 70, 1475)], fill=(210, 190, 175, 255), width=2)
draw.text((70, 1490), "CROSS-CORRIDOR PERFORMANCE BENCHMARKS (JAKARTA DEPARTURE)", font=font_kicker, fill=(120, 95, 80, 255))

pillar_w = (WIDTH - 140 - 40) // 3
pillars = [
    ("🔴 NORTHERN SEA ROUTE (NSR)", FT_RED, [
        ("Transit Distance:", "± 8,400 nm (Equal to Suez)"),
        ("Transit Duration:", "± 27 – 30 Days (Fastest in summer)"),
        ("Primary Feasibility:", "Highly Constrained (July–Oct only)"),
        ("Bottlenecks / Risks:", "Polar ice floes, Vilkitsky Strait, Russian sanctions"),
        ("Fleet Requirements:", "Arc4–Arc7 Ice-class hull & mandatory escort")
    ]),
    ("🔵 SUEZ CANAL ROUTE", FT_NAVY, [
        ("Transit Distance:", "± 8,400 nm (Direct global trunkline)"),
        ("Transit Duration:", "± 28 – 32 Days (Standard cruising)"),
        ("Primary Feasibility:", "Year-Round Continuous Service"),
        ("Bottlenecks / Risks:", "Bab-el-Mandeb drone threats & canal congestion"),
        ("Fleet Requirements:", "Standard container vessels; high war-risk insurance")
    ]),
    ("🟠 CAPE OF GOOD HOPE ROUTE", FT_AMBER, [
        ("Transit Distance:", "± 11,600 nm (+38% distance penalty)"),
        ("Transit Duration:", "± 38 – 43 Days (+10 to 14 days delay)"),
        ("Primary Feasibility:", "Year-Round Conflict Bypass Route"),
        ("Bottlenecks / Risks:", "Cape storms, high swell, lack of emergency berths"),
        ("Fleet Requirements:", "Deep-sea long-range bunker tanks; +40% fuel budget")
    ])
]

px_start = 70
for p_title, p_col, p_rows in pillars:
    draw.rounded_rectangle([px_start, 1515, px_start + pillar_w, 1750], radius=6,
                           fill=(255, 255, 255, 245), outline=(215, 195, 180, 255), width=1)
    draw.rounded_rectangle([px_start, 1515, px_start + pillar_w, 1521], radius=3, fill=p_col)
    draw.text((px_start + 20, 1532), p_title, font=font_section_h2, fill=p_col)
    
    ry = 1568
    for lbl, val in p_rows:
        draw.text((px_start + 20, ry), lbl, font=font_body_bold, fill=(70, 65, 60, 255))
        draw.text((px_start + 180, ry), val, font=font_body, fill=(25, 25, 30, 255))
        ry += 27
    px_start += pillar_w + 20

# Footer
draw.line([(70, HEIGHT - 55), (WIDTH - 70, HEIGHT - 55)], fill=(210, 190, 175, 255), width=1)
draw.text((70, HEIGHT - 42), "Sources: International Maritime Organization (IMO), Arctic Institute, Suez Canal Authority, MarineTraffic • Cartography: DataLabs", font=font_callout_sub, fill=(130, 115, 105, 255))
draw.text((WIDTH - 280, HEIGHT - 42), "FINANCIAL TIMES INFOGRAPHIC", font=font_brand, fill=(155, 35, 50, 255))

final_img = Image.alpha_composite(base_img.convert("RGBA"), overlay)

out_file = os.path.join(out_dir, "arctic_shipping_infographic_ft.png")
final_img.save(out_file, "PNG", quality=95)

# Copy to artifact dir
artifact_img_path = os.path.join(artifact_dir, "arctic_shipping_infographic_ft.png")
shutil.copyfile(out_file, artifact_img_path)
print(f"Infographic saved to {out_file} and copied to {artifact_img_path}!")
