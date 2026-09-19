import os
import math
import json
import shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

out_dir = r"C:\Users\User\ArcticShippingRoute"
os.makedirs(out_dir, exist_ok=True)
artifact_dir = r"C:\Users\User\.gemini\antigravity-cli\brain\d707f0b4-74df-4408-8b6b-21491274467b"

# 1. Canvas and Globe Geometry
WIDTH = 2412
HEIGHT = 1756
CX = 1206
CY = 960
RADIUS = 725

# Center at 30N, 55E to show Cape of Good Hope, Jakarta, Arctic Ocean, and Europe
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

# 2. Build Editorial Broadsheet Themed Earth
print("Processing Editorial style Earth texture...")
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

# Detect ocean: in topo image, ocean is very dark blue/black
is_ocean = (sampled_topo[:, :, 2] > sampled_topo[:, :, 0] + 10) & (sampled_topo[:, :, 1] < 90)

# Ice detection for Arctic & Greenland
ice_weight = np.clip((lat_deg - 66.0) / 8.0, 0.0, 1.0)
is_greenland = (lat_deg > 58.0) & (lat_deg < 84.0) & (lon_deg > -55.0) & (lon_deg < -15.0)
ice_weight = np.where(is_greenland, 1.0, ice_weight)

winter_brightness = (sampled_winter[:, :, 0] + sampled_winter[:, :, 1] + sampled_winter[:, :, 2]) / 3.0
is_snow = winter_brightness > 130
effective_ice_weight = ice_weight * np.where(is_snow, 1.0, 0.20)

# FT Color Palette Definitions
# Background: Classic FT Warm Bisque/Salmon Paper
FT_BG = np.array([255, 241, 229], dtype=np.float32)  # #FFF1E5

# Ocean: Soft light editorial powder blue
FT_OCEAN = np.array([214, 229, 238], dtype=np.float32) # #D6E5EE
# Shallow ocean tint near shores
FT_OCEAN_SHALLOW = np.array([225, 237, 244], dtype=np.float32)

# Land: Warm muted slate/tan paper stone
FT_LAND_BASE = np.array([224, 219, 210], dtype=np.float32) # #E0DBD2

# Ice / Snow: Pure crisp arctic snow white
FT_ICE = np.array([248, 250, 252], dtype=np.float32) # #F8FAFC

# Calculate land topography relief brightness (normalized 0.85 to 1.15)
land_lum = (sampled_topo[:, :, 0] * 0.299 + sampled_topo[:, :, 1] * 0.587 + sampled_topo[:, :, 2] * 0.114)
relief = np.clip(land_lum / 120.0, 0.75, 1.25)

# Render texture per pixel
ft_texture = np.zeros((HEIGHT, WIDTH, 3), dtype=np.float32)

for c in range(3):
    # Base land with subtle relief shading
    land_col = FT_LAND_BASE[c] * (0.80 + 0.20 * relief)
    
    # Ocean color with slight spherical depth
    ocean_col = FT_OCEAN[c] * (0.96 + 0.04 * cos_c)
    
    # Base choice: ocean vs land
    base_val = np.where(is_ocean, ocean_col, land_col)
    
    # Blend ice/snow over both land and sea ice in Arctic
    blended_val = np.where(effective_ice_weight > 0.05,
                           base_val * (1.0 - effective_ice_weight) + FT_ICE[c] * effective_ice_weight,
                           base_val)
    
    ft_texture[:, :, c] = blended_val

# Subtle spherical edge vignette for 3D curvature feel
globe_shading = np.clip(0.65 + 0.35 * (cos_c**0.25), 0.65, 1.0)
ft_texture *= globe_shading[:, :, np.newaxis]

# Create Canvas
canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.float32)
canvas[:, :, :] = FT_BG
canvas[disk_mask] = ft_texture[disk_mask]

base_img = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), mode="RGB")

# 2B. Crisp globe outer rim (No shadow or halo effects)
rim_draw = ImageDraw.Draw(base_img)
rim_draw.ellipse([CX - RADIUS, CY - RADIUS, CX + RADIUS, CY + RADIUS],
                 outline=(165, 150, 138), width=2)

# 2C. Draw Graticule Lines (Parallels and Meridians - classic FT cartography)
graticule_img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
grat_draw = ImageDraw.Draw(graticule_img)
GRAT_COLOR = (140, 165, 185, 90)

# Parallels (Latitudes)
for grat_lat in range(-60, 85, 30):
    grat_pts = []
    for grat_lon in range(-180, 181, 2):
        x, y, vis = ortho_project(grat_lon, grat_lat)
        if vis and x is not None:
            grat_pts.append(to_pixel(x, y))
        else:
            if len(grat_pts) > 1:
                grat_draw.line(grat_pts, fill=GRAT_COLOR, width=1)
            grat_pts = []
    if len(grat_pts) > 1:
        grat_draw.line(grat_pts, fill=GRAT_COLOR, width=1)

# Meridians (Longitudes)
for grat_lon in range(-180, 181, 30):
    grat_pts = []
    for grat_lat in range(-80, 85, 2):
        x, y, vis = ortho_project(grat_lon, grat_lat)
        if vis and x is not None:
            grat_pts.append(to_pixel(x, y))
        else:
            if len(grat_pts) > 1:
                grat_draw.line(grat_pts, fill=GRAT_COLOR, width=1)
            grat_pts = []
    if len(grat_pts) > 1:
        grat_draw.line(grat_pts, fill=GRAT_COLOR, width=1)

base_img.paste(graticule_img, (0, 0), graticule_img)
print("Base FT globe ready.")

# 3. Load all 3 routes
with open(os.path.join(out_dir, "northern_sea_route.geojson"), "r") as f:
    nsr_coords = json.load(f)["features"][0]["geometry"]["coordinates"]

with open(os.path.join(out_dir, "suez_route.geojson"), "r") as f:
    suez_coords = json.load(f)["features"][0]["geometry"]["coordinates"]

with open(os.path.join(out_dir, "cape_route.geojson"), "r") as f:
    cape_coords = json.load(f)["features"][0]["geometry"]["coordinates"]

def interpolate_dense(coords, steps=35):
    fine = []
    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i+1]
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

# 4. Draw Overlay Elements
overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
draw = ImageDraw.Draw(overlay)

# FT Colors for Routes
FT_RED = (205, 18, 55, 255)       # Solid FT Claret / Crimson for Northern Sea Route
FT_NAVY = (12, 80, 142, 255)      # Solid FT Deep Blue for Suez Route
FT_AMBER = (218, 105, 18, 255)    # Solid FT Burnt Ochre/Amber for Cape Route

# Flat solid route lines (No glow, no casing, no effects)
ROUTE_WIDTH = 5
draw.line(cape_px, fill=FT_AMBER, width=ROUTE_WIDTH, joint="curve")
draw.line(suez_px, fill=FT_NAVY, width=ROUTE_WIDTH, joint="curve")
draw.line(nsr_px, fill=FT_RED, width=ROUTE_WIDTH, joint="curve")

# Clean directional arrows helper without backing or outlines
def draw_arrows(px_list, color, fractions, size=13):
    for f in fractions:
        idx = int(len(px_list) * f)
        if idx < len(px_list) - 5:
            p1 = px_list[idx]
            p2 = px_list[idx + 5]
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
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

# 5. Route Ports and Markers
# Jakarta
xj, yj, _ = ortho_project(106.88, -6.10)
pxj, pyj = to_pixel(xj, yj)
draw.ellipse([pxj - 12, pyj - 12, pxj + 12, pyj + 12], fill=(255, 255, 255, 255), outline=(30, 30, 35), width=3)
draw.ellipse([pxj - 6, pyj - 6, pxj + 6, pyj + 6], fill=FT_RED)

# Cape of Good Hope waypoint
xcape, ycape, _ = ortho_project(18.5, -34.5)
pxcape, pycape = to_pixel(xcape, ycape)
draw.ellipse([pxcape - 8, pycape - 8, pxcape + 8, pycape + 8], fill=FT_AMBER, outline=(255, 255, 255, 255), width=3)

# Teesport, UK
xuk, yuk, _ = ortho_project(-1.15, 54.60)
pxuk, pyuk = to_pixel(xuk, yuk)
draw.ellipse([pxuk - 11, pyuk - 11, pxuk + 11, pyuk + 11], fill=(255, 255, 255, 255), outline=FT_RED, width=4)
draw.ellipse([pxuk - 5, pyuk - 5, pxuk + 5, pyuk + 5], fill=(30, 30, 35))

# Fonts
font_brand = ImageFont.truetype("arialbd.ttf", 15)
font_kicker = ImageFont.truetype("arialbd.ttf", 16)
font_main_title = ImageFont.truetype("georgiab.ttf", 36)
font_subtitle = ImageFont.truetype("georgia.ttf", 20)

font_country = ImageFont.truetype("georgiab.ttf", 21)
font_country_large = ImageFont.truetype("georgiab.ttf", 27)
font_water = ImageFont.truetype("georgiai.ttf", 18)

font_card_title = ImageFont.truetype("georgiab.ttf", 19)
font_card_body = ImageFont.truetype("arial.ttf", 16)
font_card_bold = ImageFont.truetype("arialbd.ttf", 16)
font_callout_bold = ImageFont.truetype("arialbd.ttf", 18)
font_callout_sub = ImageFont.truetype("arial.ttf", 15)

# Editorial Header Block (Top-Left)
draw.text((70, 50), "GLOBAL MARITIME TRANSIT & CARTOGRAPHY", font=font_kicker, fill=(130, 95, 80, 255))
draw.text((70, 78), "Shipping Routes from Jakarta to Europe", font=font_main_title, fill=(20, 20, 25, 255))
draw.text((70, 126), "Comparing distance and voyage duration via the Arctic, Suez Canal, and Cape of Good Hope", font=font_subtitle, fill=(85, 75, 70, 255))
draw.line([(70, 168), (WIDTH - 70, 168)], fill=(210, 190, 175, 255), width=2)

# Helper to draw FT style informational cards
def draw_ft_card(pos, title, rows, badge_color, width=380, height=130):
    x, y = pos
    # Soft shadow for card
    draw.rounded_rectangle([x + 3, y + 4, x + width + 3, y + height + 4], radius=6,
                           fill=(195, 175, 160, 80))
    # Crisp white card background
    draw.rounded_rectangle([x, y, x + width, y + height], radius=6,
                           fill=(255, 255, 255, 248), outline=(215, 195, 180, 255), width=1)
    # Color accent bar on top
    draw.rounded_rectangle([x, y, x + width, y + 6], radius=3, fill=badge_color)
    
    # Title
    draw.ellipse([x + 18, y + 18, x + 28, y + 28], fill=badge_color)
    draw.text((x + 36, y + 14), title, font=font_card_title, fill=(20, 20, 25, 255))
    
    # Content rows
    curr_y = y + 46
    for label, val in rows:
        draw.text((x + 18, curr_y), label, font=font_card_body, fill=(105, 95, 90, 255))
        draw.text((x + 105, curr_y), val, font=font_card_bold, fill=(25, 25, 30, 255))
        curr_y += 24

# 6. Informational Cards for the 3 Routes (Floating cleanly in margins)
# Card 1: Northern Sea Route (Arctic)
draw_ft_card(
    pos=(1935, 230),
    title="Northern Sea Route (NSR)",
    rows=[
        ("Duration:", "± 27 – 30 Days"),
        ("Distance:", "± 8,400 nm"),
        ("Season:", "July – Oct (Summer Window)")
    ],
    badge_color=FT_RED,
    width=410, height=130
)

# Card 2: Suez Canal Route
draw_ft_card(
    pos=(60, 720),
    title="Suez Canal Route",
    rows=[
        ("Duration:", "± 28 – 32 Days"),
        ("Distance:", "± 8,400 nm"),
        ("Operation:", "Year-Round Standard Transit")
    ],
    badge_color=FT_NAVY,
    width=390, height=130
)

# Card 3: Cape of Good Hope Route
draw_ft_card(
    pos=(60, 1380),
    title="Cape of Good Hope Route",
    rows=[
        ("Duration:", "± 38 – 43 Days (+10–14 d)"),
        ("Distance:", "± 11,600 nm"),
        ("Status:", "Conflict Avoidance Route")
    ],
    badge_color=FT_AMBER,
    width=405, height=130
)

# Starting Point: Jakarta Callout
draw.line([(pxj, pyj), (pxj + 45, pyj + 30), (pxj + 90, pyj + 30)], fill=(40, 40, 45, 255), width=2)
draw.text((pxj + 100, pyj + 10), "STARTING POINT", font=font_callout_bold, fill=FT_RED)
draw.text((pxj + 100, pyj + 30), "Jakarta, Indonesia", font=font_callout_bold, fill=(25, 25, 30, 255))
draw.text((pxj + 100, pyj + 50), "Port of Tanjung Priok", font=font_callout_sub, fill=(90, 80, 75, 255))

# Destination Point: UK Callout
draw.line([(pxuk, pyuk), (pxuk - 40, pyuk - 30), (pxuk - 85, pyuk - 30)], fill=(40, 40, 45, 255), width=2)
draw.text((pxuk - 280, pyuk - 75), "DESTINATION", font=font_callout_bold, fill=FT_RED)
draw.text((pxuk - 280, pyuk - 55), "Teesport, United Kingdom", font=font_callout_bold, fill=(25, 25, 30, 255))
draw.text((pxuk - 280, pyuk - 35), "Western European Terminal", font=font_callout_sub, fill=(90, 80, 75, 255))

# Cape of Good Hope label
draw.text((pxcape - 170, pycape + 15), "Cape of Good Hope\n(South Africa)", font=font_water, fill=(130, 75, 20, 240))

# 7. Geographic Labels
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

# Footer
draw.line([(70, HEIGHT - 55), (WIDTH - 70, HEIGHT - 55)], fill=(210, 190, 175, 255), width=1)
draw.text((70, HEIGHT - 45), "Sources: IMO, Arctic Institute, Suez Canal Authority, MarineTraffic • Cartography: DataLabs", font=font_callout_sub, fill=(130, 115, 105, 255))
draw.text((WIDTH - 250, HEIGHT - 45), "EDITORIAL BROADSHEET", font=font_brand, fill=(135, 95, 80, 255))

final_img = Image.alpha_composite(base_img.convert("RGBA"), overlay)

out_file = os.path.join(out_dir, "arctic_shipping_route_ft.png")
final_img.save(out_file, "PNG", quality=95)

# Copy to artifact dir
artifact_img_path = os.path.join(artifact_dir, "arctic_shipping_route_ft.png")
shutil.copyfile(out_file, artifact_img_path)
print(f"Editorial Broadsheet map saved to {out_file} and copied to {artifact_img_path}!")
