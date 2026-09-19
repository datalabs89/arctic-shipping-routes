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

# 2. Build Earth Texture
print("Rendering editorial Earth texture...")
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

# Editorial Color Palette
BG_COLOR = np.array([255, 241, 229], dtype=np.float32)       # Warm paper (#FFF1E5)
OCEAN_COLOR = np.array([214, 229, 238], dtype=np.float32)    # Soft blue (#D6E5EE)
LAND_BASE = np.array([224, 219, 210], dtype=np.float32)      # Stone (#E0DBD2)
ICE_COLOR = np.array([248, 250, 252], dtype=np.float32)      # Snow white (#F8FAFC)

land_lum = (sampled_topo[:, :, 0] * 0.299 + sampled_topo[:, :, 1] * 0.587 + sampled_topo[:, :, 2] * 0.114)
relief = np.clip(land_lum / 120.0, 0.75, 1.25)

texture = np.zeros((HEIGHT, WIDTH, 3), dtype=np.float32)
for c in range(3):
    land_col = LAND_BASE[c] * (0.80 + 0.20 * relief)
    ocean_col = OCEAN_COLOR[c] * (0.96 + 0.04 * cos_c)
    base_val = np.where(is_ocean, ocean_col, land_col)
    blended_val = np.where(effective_ice_weight > 0.05,
                           base_val * (1.0 - effective_ice_weight) + ICE_COLOR[c] * effective_ice_weight,
                           base_val)
    texture[:, :, c] = blended_val

globe_shading = np.clip(0.65 + 0.35 * (cos_c**0.25), 0.65, 1.0)
texture *= globe_shading[:, :, np.newaxis]

canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.float32)
canvas[:, :, :] = BG_COLOR
canvas[disk_mask] = texture[disk_mask]

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
NSR_COLOR = (205, 18, 55, 255)       # Northern Sea Route (Crimson)
SUEZ_COLOR = (12, 80, 142, 255)      # Suez Canal Route (Deep Navy)
CAPE_COLOR = (218, 105, 18, 255)     # Cape of Good Hope Route (Burnt Amber)

# Pure Solid Flat Lines (No casing, no glow, no effects)
ROUTE_WIDTH = 5
draw.line(cape_px, fill=CAPE_COLOR, width=ROUTE_WIDTH, joint="curve")
draw.line(suez_px, fill=SUEZ_COLOR, width=ROUTE_WIDTH, joint="curve")
draw.line(nsr_px, fill=NSR_COLOR, width=ROUTE_WIDTH, joint="curve")

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

draw_arrows(nsr_px, NSR_COLOR, [0.08, 0.22, 0.48, 0.70, 0.88], size=13)
draw_arrows(suez_px, SUEZ_COLOR, [0.15, 0.45, 0.75], size=12)
draw_arrows(cape_px, CAPE_COLOR, [0.18, 0.42, 0.65, 0.85], size=12)

# Port Markers
xj, yj, _ = ortho_project(106.88, -6.10)
pxj, pyj = to_pixel(xj, yj)
draw.ellipse([pxj - 10, pyj - 10, pxj + 10, pyj + 10], fill=(255, 255, 255, 255), outline=(30, 30, 35), width=3)
draw.ellipse([pxj - 5, pyj - 5, pxj + 5, pyj + 5], fill=NSR_COLOR)

xcape, ycape, _ = ortho_project(18.5, -34.5)
pxcape, pycape = to_pixel(xcape, ycape)
draw.ellipse([pxcape - 7, pycape - 7, pxcape + 7, pycape + 7], fill=CAPE_COLOR, outline=(255, 255, 255, 255), width=2)

xuk, yuk, _ = ortho_project(-1.15, 54.60)
pxuk, pyuk = to_pixel(xuk, yuk)
draw.ellipse([pxuk - 10, pyuk - 10, pxuk + 10, pyuk + 10], fill=(255, 255, 255, 255), outline=NSR_COLOR, width=3)
draw.ellipse([pxuk - 4, pyuk - 4, pxuk + 4, pyuk + 4], fill=(30, 30, 35))

# 5. Typography Definitions
font_kicker = ImageFont.truetype("arialbd.ttf", 15)
font_title = ImageFont.truetype("georgiab.ttf", 36)
font_subtitle = ImageFont.truetype("georgia.ttf", 19)
font_section_h2 = ImageFont.truetype("georgiab.ttf", 18)
font_body = ImageFont.truetype("arial.ttf", 15)
font_body_bold = ImageFont.truetype("arialbd.ttf", 15)
font_callout_bold = ImageFont.truetype("arialbd.ttf", 17)
font_callout_sub = ImageFont.truetype("arial.ttf", 14)
font_tag = ImageFont.truetype("arialbd.ttf", 12)

font_country = ImageFont.truetype("georgiab.ttf", 20)
font_country_large = ImageFont.truetype("georgiab.ttf", 26)
font_water = ImageFont.truetype("georgiai.ttf", 17)

# 6. Top Header Banner
draw.text((70, 48), "GLOBAL MARITIME LOGISTICS & GEOECONOMIC INTELLIGENCE", font=font_kicker, fill=(135, 95, 80, 255))
draw.text((70, 76), "The Equatorial Dilemma: Jakarta to Europe Shipping Corridors", font=font_title, fill=(20, 20, 25, 255))
draw.text((70, 126), "A comparative evaluation of navigational efficiency, chokepoint vulnerabilities, and operational economics across three global routes", font=font_subtitle, fill=(85, 75, 70, 255))
draw.line([(70, 168), (WIDTH - 70, 168)], fill=(210, 190, 175, 255), width=2)

# Helper to draw Storytelling Insight Panels
def draw_story_card(pos, tag, title, body_paragraphs, accent_color, width=640, height=235):
    x, y = pos
    draw.rounded_rectangle([x, y, x + width, y + height], radius=6,
                           fill=(255, 255, 255, 245), outline=(215, 195, 180, 255), width=1)
    draw.rounded_rectangle([x, y, x + 6, y + height], radius=3, fill=accent_color)
    
    tag_w = draw.textlength(tag, font=font_tag) + 16
    draw.rounded_rectangle([x + 20, y + 16, x + 20 + tag_w, y + 36], radius=4,
                           fill=accent_color)
    draw.text((x + 28, y + 19), tag, font=font_tag, fill=(255, 255, 255, 255))
    
    draw.text((x + 20, y + 46), title, font=font_section_h2, fill=(20, 20, 25, 255))
    
    curr_y = y + 78
    for line in body_paragraphs:
        if line.startswith("**"):
            draw.text((x + 20, curr_y), line.replace("**", ""), font=font_body_bold, fill=accent_color)
            curr_y += 22
        else:
            draw.text((x + 20, curr_y), line, font=font_body, fill=(65, 60, 55, 255))
            curr_y += 21

# LEFT COLUMN: 4 Storytelling Insight Panels (No repetitive numbers from right cards)
# Card 1: The Geographic Reality
draw_story_card(
    pos=(70, 195),
    tag="ANALYSIS 1 • THE LATITUDINAL REALITY",
    title="Why Equatorial Origin Negates the Arctic Proximity Advantage",
    body_paragraphs=[
        "While polar melting provides northern ports in China and Japan a direct shortcut,",
        "vessels from Indonesia must spend over a week sailing through the South China Sea",
        "**and Sea of Japan just to reach the Arctic entrance at the Bering Strait.**",
        "By the time a ship reaches the ice pack, an equivalent vessel on the western corridor",
        "is already crossing the Arabian Sea, eliminating any navigational distance benefit."
    ],
    accent_color=NSR_COLOR,
    width=640, height=215
)

# Card 2: The Red Sea Security Surcharge
draw_story_card(
    pos=(70, 435),
    tag="ANALYSIS 2 • CHOKEPOINT VULNERABILITY",
    title="The Economic Surcharge of Middle Eastern Flashpoints",
    body_paragraphs=[
        "The passage through the Bab-el-Mandeb Strait exposes modern container vessels",
        "to asymmetric regional threats, drone strikes, and maritime harassment.",
        "**Underwriters have levied war-risk insurance surcharges of up to 1% of hull value,**",
        "confronting global shipping alliances with a stark choice between catastrophic",
        "vessel liability and the schedule disruption of rounding the African continent."
    ],
    accent_color=SUEZ_COLOR,
    width=640, height=215
)

# Card 3: The Southern Ocean Swells
draw_story_card(
    pos=(70, 675),
    tag="ANALYSIS 3 • MARITIME WEATHER HAZARDS",
    title="The Physical Toll of Circumnavigating South Africa",
    body_paragraphs=[
        "The Cape diversion offers complete geopolitical safety but presents severe oceanographic",
        "challenges around the southern tip of Africa (latitudes 34°S to 36°S).",
        "**Vessels endure relentless Roaring Forties swells and intense Agulhas current shears,**",
        "leading to higher hull fatigue, damaged container lashings, and mandatory speed",
        "reductions alongside an absence of intermediate emergency repair berths."
    ],
    accent_color=CAPE_COLOR,
    width=640, height=215
)

# Card 4: Polar Commercial Viability
draw_story_card(
    pos=(70, 915),
    tag="ANALYSIS 4 • POLAR FLEET ECONOMICS",
    title="Institutional & Governance Barriers along the Siberian Coast",
    body_paragraphs=[
        "Beyond climatic limitations, commercial operations along the Russian Northern Sea Route",
        "require adherence to the Northern Sea Route Administration (NSRA) framework.",
        "**Mandatory Russian nuclear icebreaker booking fees and stringent Western sanctions**",
        "restrict international carrier participation, confining the corridor predominantly to",
        "domestic Russian Arctic hydrocarbon logistics rather than regular liner shipping."
    ],
    accent_color=(135, 35, 75, 255),
    width=640, height=215
)

# RIGHT COLUMN: Single Source of Truth for Route Specifications (x=2170, width=460)
def draw_route_card(pos, title, metrics, badge_color, width=460, height=205):
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
        draw.text((x + 125, curr_y), val, font=font_body_bold, fill=val_color)
        curr_y += 26

# Right Card 1: NSR
draw_route_card(
    pos=(2170, 195),
    title="Northern Sea Route (NSR)",
    metrics=[
        ("Distance:", "± 8,400 nm (~15,550 km)", False),
        ("Est. Transit:", "± 27 – 30 Days (Summer Window)", False),
        ("Seasonality:", "July – October (90-day window)", True),
        ("Chokepoint:", "Bering & Vilkitsky Straits (Ice floes)", False),
        ("Fleet Specs:", "Arc4 / Arc7 Ice-Class Strengthened Hull", False)
    ],
    badge_color=NSR_COLOR,
    width=460, height=205
)

# Right Card 2: Suez
draw_route_card(
    pos=(2170, 430),
    title="Suez Canal Route",
    metrics=[
        ("Distance:", "± 8,400 nm (~15,550 km)", False),
        ("Est. Transit:", "± 28 – 32 Days (Continuous Service)", False),
        ("Seasonality:", "Year-Round Navigability (12 Months)", False),
        ("Chokepoint:", "Bab-el-Mandeb Strait & Suez Canal", True),
        ("Fleet Specs:", "Standard Ocean-Going Commercial Vessels", False)
    ],
    badge_color=SUEZ_COLOR,
    width=460, height=205
)

# Right Card 3: Cape
draw_route_card(
    pos=(2170, 665),
    title="Cape of Good Hope Route",
    metrics=[
        ("Distance:", "± 11,600 nm (+38% Distance Penalty)", True),
        ("Est. Transit:", "± 38 – 43 Days (+10 to 14 Days Delay)", True),
        ("Seasonality:", "Year-Round Navigability (12 Months)", False),
        ("Chokepoint:", "Cape Agulhas & Southern Ocean Swells", False),
        ("Fleet Specs:", "High Bunker Reserves (+40% Fuel Budget)", True)
    ],
    badge_color=CAPE_COLOR,
    width=460, height=205
)

# Right Card 4: Cartographic & Navigation Modeling Parameters
draw.rounded_rectangle([2170, 900, 2630, 1150], radius=6, fill=(255, 255, 255, 240), outline=(215, 195, 180, 255), width=1)
draw.text((2190, 920), "MODELING PARAMETERS", font=font_section_h2, fill=(25, 25, 30, 255))
draw.line([(2190, 948), (2610, 948)], fill=(210, 190, 175, 255), width=1)
specs = [
    ("Projection:", "Azimuthal Orthographic (3D Hemisphere)"),
    ("Vantage Center:", "30.0° N, 55.0° E (Zero Distortion Disc)"),
    ("Origin Port:", "Tanjung Priok, Jakarta (-6.10° S, 106.88° E)"),
    ("Destination:", "Teesport, United Kingdom (54.60° N, -1.15° W)"),
    ("Cruising Speed:", "14.5 kts open sea; 9.5 kts Arctic ice convoy")
]
sy = 965
for label, val in specs:
    draw.text((2190, sy), label, font=font_body_bold, fill=(90, 80, 75, 255))
    draw.text((2310, sy), val, font=font_body, fill=(40, 40, 45, 255))
    sy += 25

# Starting Point: Jakarta Callout
draw.line([(pxj, pyj), (pxj + 45, pyj + 30), (pxj + 90, pyj + 30)], fill=(40, 40, 45, 255), width=2)
draw.text((pxj + 100, pyj + 10), "STARTING POINT", font=font_callout_bold, fill=NSR_COLOR)
draw.text((pxj + 100, pyj + 30), "Jakarta, Indonesia", font=font_callout_bold, fill=(25, 25, 30, 255))
draw.text((pxj + 100, pyj + 50), "Port of Tanjung Priok", font=font_callout_sub, fill=(90, 80, 75, 255))

# Destination Point: UK Callout
draw.line([(pxuk, pyuk), (pxuk - 40, pyuk - 30), (pxuk - 85, pyuk - 30)], fill=(40, 40, 45, 255), width=2)
draw.text((pxuk - 275, pyuk - 75), "DESTINATION", font=font_callout_bold, fill=NSR_COLOR)
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

# 7. BOTTOM COMPARATIVE STRIP: 3 Strategic Pillars
draw.line([(70, 1465), (WIDTH - 70, 1465)], fill=(210, 190, 175, 255), width=2)
draw.text((70, 1480), "STRATEGIC DECISION MATRIX • MULTI-CRITERIA CORRIDOR ASSESSMENT", font=font_kicker, fill=(130, 95, 80, 255))

pillar_w = (WIDTH - 140 - 40) // 3
pillars = [
    ("1. GEOPOLITICAL & REGULATORY REGIME", (135, 35, 75, 255), [
        ("• Suez Corridor:", "Multi-state flashpoint; vulnerable to asymmetric drone strikes & regional blockades."),
        ("• Cape Corridor:", "Unrestricted international waters; maximum geopolitical neutrality under UNCLOS."),
        ("• Arctic Corridor:", "100% within Russian exclusive jurisdiction; subject to Western sanctions & escort mandates.")
    ]),
    ("2. ENVIRONMENTAL & DECARBONIZATION IMPACT", SUEZ_COLOR, [
        ("• Suez Corridor:", "Lowest baseline CO2 footprint per TEU under normal sailing; zero ice impact."),
        ("• Cape Corridor:", "+38% gross GHG emissions resulting from 3,200 nm additional marine fuel burn."),
        ("• Arctic Corridor:", "Black carbon deposition accelerates ice melt; stringent IMO Polar Code compliance.")
    ]),
    ("3. SUPPLY CHAIN & CARGO VIABILITY", CAPE_COLOR, [
        ("• Suez Corridor:", "Essential for time-critical container liner networks, electronics, textiles & retail."),
        ("• Cape Corridor:", "Best suited for bulk dry commodities, minerals, crude oil, and buffered container loops."),
        ("• Arctic Corridor:", "Niche seasonal corridor for Siberian LNG & bulk minerals; non-viable for regular liner loops.")
    ])
]

px_start = 70
for p_title, p_col, p_rows in pillars:
    draw.rounded_rectangle([px_start, 1505, px_start + pillar_w, 1780], radius=6,
                           fill=(255, 255, 255, 245), outline=(215, 195, 180, 255), width=1)
    draw.rounded_rectangle([px_start, 1505, px_start + pillar_w, 1511], radius=3, fill=p_col)
    draw.text((px_start + 20, 1525), p_title, font=font_section_h2, fill=(20, 20, 25, 255))
    
    ry = 1565
    for lbl, desc in p_rows:
        draw.text((px_start + 20, ry), lbl, font=font_body_bold, fill=p_col)
        # Word wrap description
        words = desc.split()
        l1, l2 = "", ""
        for w in words:
            if len(l1 + " " + w) < 46:
                l1 = (l1 + " " + w).strip()
            else:
                l2 = (l2 + " " + w).strip()
        draw.text((px_start + 20, ry + 22), l1, font=font_body, fill=(55, 50, 45, 255))
        if l2:
            draw.text((px_start + 20, ry + 42), l2, font=font_body, fill=(55, 50, 45, 255))
        ry += 66
    px_start += pillar_w + 20

# Footer (Clean attribution)
draw.line([(70, HEIGHT - 55), (WIDTH - 70, HEIGHT - 55)], fill=(210, 190, 175, 255), width=1)
draw.text((70, HEIGHT - 42), "Sources: International Maritime Organization (IMO), Arctic Institute, Suez Canal Authority, MarineTraffic • Cartography: DataLabs", font=font_callout_sub, fill=(130, 115, 105, 255))
draw.text((WIDTH - 280, HEIGHT - 42), "GEOECONOMIC INTELLIGENCE", font=font_kicker, fill=(135, 95, 80, 255))

final_img = Image.alpha_composite(base_img.convert("RGBA"), overlay)

out_file = os.path.join(out_dir, "arctic_shipping_infographic_ft.png")
final_img.save(out_file, "PNG", quality=95)

# Copy to artifact dir
artifact_img_path = os.path.join(artifact_dir, "arctic_shipping_infographic_ft.png")
shutil.copyfile(out_file, artifact_img_path)
print(f"Infographic saved to {out_file} and copied to {artifact_img_path}!")
