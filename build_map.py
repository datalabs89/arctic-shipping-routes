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
CY = 878
RADIUS = 840

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

# 2. Build blended Earth texture
print("Processing Earth texture for 3-route global perspective...")
img_summer = Image.open(os.path.join(out_dir, "land_topo_2048.jpg")).convert("RGB")
img_winter = Image.open(os.path.join(out_dir, "earth_5400.jpg")).resize(img_summer.size).convert("RGB")

arr_summer = np.array(img_summer, dtype=np.float32)
arr_winter = np.array(img_winter, dtype=np.float32)
src_h, src_w, _ = arr_summer.shape

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

sampled_summer = arr_summer[src_py, src_px]
sampled_winter = arr_winter[src_py, src_px]

lat_deg = np.degrees(lat)
lon_deg = np.degrees(lon)

ice_weight = np.clip((lat_deg - 66.0) / 8.0, 0.0, 1.0)
is_greenland = (lat_deg > 58.0) & (lat_deg < 84.0) & (lon_deg > -55.0) & (lon_deg < -15.0)
ice_weight = np.where(is_greenland, 1.0, ice_weight)

winter_brightness = (sampled_winter[:, :, 0] + sampled_winter[:, :, 1] + sampled_winter[:, :, 2]) / 3.0
is_snow = winter_brightness > 130
effective_ice_weight = ice_weight * np.where(is_snow, 1.0, 0.20)

blended_texture = np.zeros_like(sampled_summer)
for c in range(3):
    blended_texture[:, :, c] = (1.0 - effective_ice_weight) * sampled_summer[:, :, c] + effective_ice_weight * sampled_winter[:, :, c]

is_ocean = (sampled_summer[:, :, 2] > sampled_summer[:, :, 0] + 12) & (sampled_summer[:, :, 1] < 90)
ocean_target = np.array([10, 16, 26], dtype=np.float32)
for c in range(3):
    blended_texture[:, :, c] = np.where(is_ocean & (effective_ice_weight < 0.35),
                                        blended_texture[:, :, c] * 0.15 + ocean_target[c] * 0.85,
                                        blended_texture[:, :, c])

limb_shading = np.clip(cos_c**0.32, 0.40, 1.0)
blended_texture *= limb_shading[:, :, np.newaxis]

canvas_arr = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
canvas_arr[:, :, :] = [6, 8, 11]
canvas_arr[disk_mask] = np.clip(blended_texture[disk_mask], 0, 255).astype(np.uint8)

base_img = Image.fromarray(canvas_arr, mode="RGB")

# Atmospheric halo
halo_img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
halo_draw = ImageDraw.Draw(halo_img)
halo_draw.ellipse([CX - RADIUS - 6, CY - RADIUS - 6, CX + RADIUS + 6, CY + RADIUS + 6],
                  outline=(65, 125, 195, 180), width=8)
halo_blurred = halo_img.filter(ImageFilter.GaussianBlur(16))
base_img.paste(halo_blurred, (0, 0), halo_blurred)

rim_draw = ImageDraw.Draw(base_img)
rim_draw.ellipse([CX - RADIUS, CY - RADIUS, CX + RADIUS, CY + RADIUS],
                 outline=(40, 65, 95), width=2)

print("Earth base ready.")

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

# Fonts
font_title = ImageFont.truetype("georgia.ttf", 28)
font_country = ImageFont.truetype("georgia.ttf", 22)
font_country_large = ImageFont.truetype("georgia.ttf", 28)
font_water = ImageFont.truetype("georgiai.ttf", 19)
font_card_title = ImageFont.truetype("arialbd.ttf", 20)
font_card_body = ImageFont.truetype("arial.ttf", 17)
font_card_bold = ImageFont.truetype("arialbd.ttf", 17)
font_bold_callout = ImageFont.truetype("arialbd.ttf", 19)

# Colors
NSR_COLOR = (248, 135, 45, 255)       # Orange
SUEZ_COLOR = (75, 155, 235, 240)      # Steel Blue
CAPE_COLOR = (245, 185, 35, 250)      # Amber / Gold

# 4A. Draw Solid Route Lines
# Cape Route
draw.line(cape_px, fill=CAPE_COLOR, width=7, joint="curve")

# Suez Route
draw.line(suez_px, fill=SUEZ_COLOR, width=7, joint="curve")

# Northern Sea Route (on top)
draw.line(nsr_px, fill=NSR_COLOR, width=8, joint="curve")

# Directional arrows helper with solid contrast outline
def draw_arrows(px_list, color, fractions, size=15):
    for f in fractions:
        idx = int(len(px_list) * f)
        if idx < len(px_list) - 6:
            p1 = px_list[idx]
            p2 = px_list[idx + 6]
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            dist = math.hypot(dx, dy)
            if dist > 0:
                ux, uy = dx / dist, dy / dist
                vx, vy = -uy, ux
                tip = p2
                left_w = (tip[0] - size * ux + size * 0.55 * vx, tip[1] - size * uy + size * 0.55 * vy)
                right_w = (tip[0] - size * ux - size * 0.55 * vx, tip[1] - size * uy - size * 0.55 * vy)
                
                # Solid dark backing outline for high visibility in dark mode
                b_tip = (tip[0] + 2.0 * ux, tip[1] + 2.0 * uy)
                b_left = (tip[0] - (size + 3) * ux + (size + 3) * 0.65 * vx, tip[1] - (size + 3) * uy + (size + 3) * 0.65 * vy)
                b_right = (tip[0] - (size + 3) * ux - (size + 3) * 0.65 * vx, tip[1] - (size + 3) * uy - (size + 3) * 0.65 * vy)
                draw.polygon([b_tip, b_left, b_right], fill=(0, 0, 0, 240))
                draw.polygon([tip, left_w, right_w], fill=color)

draw_arrows(nsr_px, NSR_COLOR, [0.08, 0.22, 0.48, 0.70, 0.88], size=15)
draw_arrows(suez_px, SUEZ_COLOR, [0.15, 0.45, 0.75], size=14)
draw_arrows(cape_px, CAPE_COLOR, [0.18, 0.42, 0.65, 0.85], size=14)

# 5. Route Ports and Markers
# Jakarta
xj, yj, _ = ortho_project(106.88, -6.10)
pxj, pyj = to_pixel(xj, yj)
draw.ellipse([pxj - 12, pyj - 12, pxj + 12, pyj + 12], fill=(255, 255, 255), outline=(10, 15, 20), width=3)
draw.ellipse([pxj - 6, pyj - 6, pxj + 6, pyj + 6], fill=NSR_COLOR, outline=SUEZ_COLOR, width=2)

# Cape of Good Hope waypoint
xcape, ycape, _ = ortho_project(18.5, -34.5)
pxcape, pycape = to_pixel(xcape, ycape)
draw.ellipse([pxcape - 8, pycape - 8, pxcape + 8, pycape + 8], fill=CAPE_COLOR, outline=(255, 255, 255), width=3)

# Teesport, UK
xuk, yuk, _ = ortho_project(-1.15, 54.60)
pxuk, pyuk = to_pixel(xuk, yuk)
draw.ellipse([pxuk - 11, pyuk - 11, pxuk + 11, pyuk + 11], fill=(255, 255, 255), outline=NSR_COLOR, width=4)
draw.ellipse([pxuk - 5, pyuk - 5, pxuk + 5, pyuk + 5], fill=(10, 15, 20))

# Helper for text with shadow
WHITE = (255, 255, 255, 255)
SHADOW = (0, 0, 0, 240)

def shadow_text(pos, text, font, fill=WHITE, shadow=SHADOW, offset=(1, 1)):
    draw.text((pos[0] + offset[0], pos[1] + offset[1]), text, font=font, fill=shadow)
    draw.text(pos, text, font=font, fill=fill)

# Helper to draw clean informational cards
def draw_info_card(pos, title, rows, badge_color, width=370, height=130):
    x, y = pos
    # Card background box
    draw.rounded_rectangle([x, y, x + width, y + height], radius=8,
                           fill=(15, 20, 28, 230), outline=(50, 65, 85, 240), width=2)
    # Color accent bar on left
    draw.rounded_rectangle([x, y, x + 8, y + height], radius=4, fill=badge_color)
    
    # Title with vector indicator circle
    draw.ellipse([x + 22, y + 15, x + 34, y + 27], fill=badge_color)
    draw.text((x + 42, y + 11), title, font=font_card_title, fill=badge_color)
    
    # Content rows
    curr_y = y + 42
    for label, val in rows:
        draw.text((x + 22, curr_y), label, font=font_card_body, fill=(190, 205, 220, 240))
        draw.text((x + 115, curr_y), val, font=font_card_bold, fill=(255, 255, 255, 255))
        curr_y += 24

# 6. Informational Cards for the 3 Routes (in English)
# Card 1: Northern Sea Route (Arctic)
draw_info_card(
    pos=(1480, 110),
    title="NORTHERN SEA ROUTE (NSR)",
    rows=[
        ("Duration:", "± 27 – 30 Days"),
        ("Distance:", "± 8,400 nm"),
        ("Season:", "July – Oct (Summer Window)")
    ],
    badge_color=NSR_COLOR,
    width=380, height=125
)

# Card 2: Suez Canal Route
draw_info_card(
    pos=(80, 680),
    title="SUEZ CANAL ROUTE",
    rows=[
        ("Duration:", "± 28 – 32 Days"),
        ("Distance:", "± 8,400 nm"),
        ("Operation:", "Year-Round Transit")
    ],
    badge_color=SUEZ_COLOR,
    width=370, height=125
)

# Card 3: Cape of Good Hope Route
draw_info_card(
    pos=(80, 1350),
    title="CAPE OF GOOD HOPE ROUTE",
    rows=[
        ("Duration:", "± 38 – 43 Days (+10–14 d)"),
        ("Distance:", "± 11,600 nm"),
        ("Status:", "Conflict Avoidance Route")
    ],
    badge_color=CAPE_COLOR,
    width=395, height=125
)

# Starting Point: Jakarta Callout
draw.line([(pxj, pyj), (pxj + 50, pyj + 30), (pxj + 100, pyj + 30)], fill=WHITE, width=2)
shadow_text((pxj + 110, pyj + 12), "STARTING POINT:\nJakarta, Indonesia\n(Port of Tanjung Priok)", font_bold_callout)

# Destination Point: UK Callout
draw.line([(pxuk, pyuk), (pxuk - 40, pyuk - 30), (pxuk - 90, pyuk - 30)], fill=WHITE, width=2)
shadow_text((pxuk - 270, pyuk - 75), "DESTINATION:\nTeesport, United Kingdom\n(Western Europe)", font_bold_callout)

# Cape of Good Hope label
shadow_text((pxcape - 170, pycape + 15), "Cape of Good Hope\n(South Africa)", font_water, fill=(235, 210, 140, 240))

# 7. Geographic Labels
countries = [
    ("RUSSIA", 90.0, 60.0, font_country_large),
    ("CHINA", 104.0, 34.0, font_country),
    ("INDIA", 79.0, 21.0, font_country),
    ("SAUDI\nARABIA", 44.0, 23.0, font_country),
    ("AFRICA", 22.0, 4.0, font_country_large),
    ("INDONESIA", 114.0, -1.0, font_country),
    ("JAPAN", 140.0, 36.5, font_country)
]

for name, lo, la, f in countries:
    x, y, vis = ortho_project(lo, la)
    if vis and x is not None:
        px, py = to_pixel(x, y)
        shadow_text((px - 35, py - 12), name, f, fill=(245, 245, 248, 240))

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
        shadow_text((px - 30, py - 8), name, font_water, fill=(185, 205, 225, 230))

final_img = Image.alpha_composite(base_img.convert("RGBA"), overlay)

out_file = os.path.join(out_dir, "arctic_shipping_route_globe.png")
final_img.save(out_file, "PNG", quality=95)

# Copy to artifact dir
artifact_img_path = os.path.join(artifact_dir, "arctic_shipping_route_globe.png")
shutil.copyfile(out_file, artifact_img_path)
print(f"3-Route map saved to {out_file} and copied to {artifact_img_path}!")
