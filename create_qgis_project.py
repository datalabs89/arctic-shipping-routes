import sys, os
from qgis.core import (
    QgsApplication, QgsProject, QgsCoordinateReferenceSystem,
    QgsVectorLayer, QgsLineSymbol, QgsSingleSymbolRenderer,
    QgsMarkerSymbol
)
from PyQt6.QtGui import QColor

qgs = QgsApplication([], False)
qgs.initQgis()

project = QgsProject.instance()
project.clear()

# 1. Coordinate Reference System: Azimuthal Orthographic centered on 30N, 55E
crs = QgsCoordinateReferenceSystem.fromProj("+proj=ortho +lat_0=30 +lon_0=55 +datum=WGS84 +units=m +no_defs")
project.setCrs(crs)

# 2. Add Natural Earth Countries
ne_path = r"C:\Users\User\GlobeBuilder\GlobeBuilder\resources\data\ne_50m_admin_0_countries.geojson"
lyr_countries = QgsVectorLayer(ne_path, "Countries (Natural Earth)", "ogr")
if lyr_countries.isValid():
    sym = lyr_countries.renderer().symbol()
    if sym:
        sym.setColor(QColor(42, 52, 45))
        sym.symbolLayer(0).setStrokeColor(QColor(60, 75, 65))
        sym.symbolLayer(0).setStrokeWidth(0.2)
    project.addMapLayer(lyr_countries)
    print("Added Countries layer")

# 3. Add Cape of Good Hope Route (Gold)
cape_path = r"C:\Users\User\ArcticShippingRoute\cape_route.geojson"
lyr_cape = QgsVectorLayer(cape_path, "Rute Tanjung Harapan (38-43 Hari, 11.600 nm)", "ogr")
if lyr_cape.isValid():
    sym = QgsLineSymbol.createSimple({"color": "#f5b923", "width": "1.0", "capstyle": "round"})
    lyr_cape.setRenderer(QgsSingleSymbolRenderer(sym))
    project.addMapLayer(lyr_cape)
    print("Added Cape Route layer")

# 4. Add Suez Route (Blue)
suez_path = r"C:\Users\User\ArcticShippingRoute\suez_route.geojson"
lyr_suez = QgsVectorLayer(suez_path, "Rute Terusan Suez (28-32 Hari, 8.400 nm)", "ogr")
if lyr_suez.isValid():
    sym = QgsLineSymbol.createSimple({"color": "#4b9be5", "width": "1.0", "capstyle": "round"})
    lyr_suez.setRenderer(QgsSingleSymbolRenderer(sym))
    project.addMapLayer(lyr_suez)
    print("Added Suez Route layer")

# 5. Add Northern Sea Route (Orange)
nsr_path = r"C:\Users\User\ArcticShippingRoute\northern_sea_route.geojson"
lyr_nsr = QgsVectorLayer(nsr_path, "Rute Arktik / NSR (27-30 Hari, 8.400 nm)", "ogr")
if lyr_nsr.isValid():
    sym = QgsLineSymbol.createSimple({"color": "#f58220", "width": "1.3", "capstyle": "round"})
    lyr_nsr.setRenderer(QgsSingleSymbolRenderer(sym))
    project.addMapLayer(lyr_nsr)
    print("Added Northern Sea Route layer")

# 6. Add Ports and Waypoints
ports_path = r"C:\Users\User\ArcticShippingRoute\ports_and_waypoints.geojson"
lyr_ports = QgsVectorLayer(ports_path, "Titik Awal (Jakarta) & Tujuan", "ogr")
if lyr_ports.isValid():
    sym = QgsMarkerSymbol.createSimple({
        "name": "circle",
        "color": "#ffffff",
        "size": "4.2",
        "outline_color": "#f58220",
        "outline_width": "1.0"
    })
    lyr_ports.setRenderer(QgsSingleSymbolRenderer(sym))
    project.addMapLayer(lyr_ports)
    print("Added Ports layer")

# 7. Save Project
proj_path = r"C:\Users\User\ArcticShippingRoute\arctic_shipping_route.qgs"
project.write(proj_path)
print("Updated QGIS Project file with 3 routes at:", proj_path)

qgs.exitQgis()
