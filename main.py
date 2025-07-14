from flask import Flask, request, jsonify
from sentinelhub import SHConfig, SentinelHubRequest, DataCollection, MimeType, bbox_to_dimensions, BBox, CRS
import numpy as np
from shapely.geometry import Polygon
import pyproj
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Set your Sentinel Hub credentials here
config = SHConfig()
config.sh_client_id = '3774c09d-1f9e-4a39-bd36-029aeda574e2'
config.sh_client_secret = 'N0sTP6nB2nuyLJwAkJzGDcP4q9CtDKXh'

# Evalscript for NDVI, NDWI, Red-edge NDVI
evalscript = """
//VERSION=3
function setup() {
    return {
        input: ["B04", "B05", "B08", "B11", "B12"],
        output: { bands: 3 }
    };
}
function evaluatePixel(sample) {
    let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
    let ndwi = (sample.B08 - sample.B11) / (sample.B08 + sample.B11);
    let redEdgeNdvi = (sample.B08 - sample.B05) / (sample.B08 + sample.B05);
    return [ndvi, ndwi, redEdgeNdvi];
}
"""

@app.route('/')
def index():
    return "Welcome to the Sentinel Hub NDVI/NDWI/Red-edge NDVI API!"

def calculate_area_hectares(coords):
    # Project polygon to UTM for accurate area calculation
    poly = Polygon(coords)
    lon, lat = poly.centroid.x, poly.centroid.y
    utm_zone = int((lon + 180) / 6) + 1
    proj_str = f"+proj=utm +zone={utm_zone} +datum=WGS84 +units=m +no_defs"
    project = pyproj.Transformer.from_crs("epsg:4326", proj_str, always_xy=True).transform
    poly_proj = Polygon([project(*c) for c in coords])
    area_m2 = poly_proj.area
    area_ha = area_m2 / 10000
    area_acres = area_m2 / 4046.85642
    return area_ha, area_acres

@app.route('/analyze', methods=['POST'])
def analyze():
    coords = request.json['coordinates']  # [[lon, lat], ...]
    print(f"Received coordinates: {coords}")
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    aoi_bbox = BBox(bbox=[min_lon, min_lat, max_lon, max_lat], crs=CRS.WGS84)
    bbox_size = bbox_to_dimensions(aoi_bbox, resolution=10)

    # Area calculation
    area_ha, area_acres = calculate_area_hectares(coords)

    request_sentinel = SentinelHubRequest(
        evalscript=evalscript,
        input_data=[SentinelHubRequest.input_data(DataCollection.SENTINEL2_L2A)],
        responses=[SentinelHubRequest.output_response('default', MimeType.TIFF)],
        bbox=aoi_bbox,
        size=bbox_size,
        config=config
    )
    print("Requesting data from Sentinel Hub...")
    data = request_sentinel.get_data()[0]
    print(f"Data received, processing...{data}")
    ndvi = float(np.nanmean(data[:, :, 0]))
    ndwi = float(np.nanmean(data[:, :, 1]))
    red_edge_ndvi = float(np.nanmean(data[:, :, 2]))

    # Generate a WMS URL for a true color image
    wms_url = (
        f"https://services.sentinel-hub.com/ogc/wms/{config.instance_id}"
        f"?SERVICE=WMS&REQUEST=GetMap&LAYERS=TRUE_COLOR&MAXCC=20"
        f"&BBOX={min_lon},{min_lat},{max_lon},{max_lat}"
        f"&WIDTH=512&HEIGHT=512&FORMAT=image/png&CRS=EPSG:4326"
    )

    print(f"NDVI: {ndvi}, NDWI: {ndwi}, Red-edge NDVI: {red_edge_ndvi}")
    print(f"Area: {area_ha} hectares, {area_acres} acres")
    print(f"True color WMS URL: {wms_url}")

    return jsonify({
        'ndvi': ndvi,
        'ndwi': ndwi,
        'red_edge_ndvi': red_edge_ndvi,
        'area_hectares': area_ha,
        'area_acres': area_acres,
        'true_color_url': wms_url
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)