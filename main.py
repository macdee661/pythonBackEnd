from flask import Flask, request, jsonify
from sentinelhub import SHConfig, SentinelHubRequest, DataCollection, MimeType, bbox_to_dimensions, BBox, CRS
import numpy as np

app = Flask(__name__)

# Set your Sentinel Hub credentials here
config = SHConfig()
config.sh_client_id = 'YOUR_CLIENT_ID'
config.sh_client_secret = 'YOUR_CLIENT_SECRET'

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

@app.route('/analyze', methods=['POST'])
def analyze():
    coords = request.json['coordinates']  # [[lon, lat], ...]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    aoi_bbox = BBox(bbox=[min_lon, min_lat, max_lon, max_lat], crs=CRS.WGS84)
    bbox_size = bbox_to_dimensions(aoi_bbox, resolution=10)

    request_sentinel = SentinelHubRequest(
        evalscript=evalscript,
        input_data=[SentinelHubRequest.input_data(DataCollection.SENTINEL2_L2A)],
        responses=[SentinelHubRequest.output_response('default', MimeType.TIFF)],
        bbox=aoi_bbox,
        size=bbox_size,
        config=config
    )
    data = request_sentinel.get_data()[0]
    ndvi = float(np.nanmean(data[:, :, 0]))
    ndwi = float(np.nanmean(data[:, :, 1]))
    red_edge_ndvi = float(np.nanmean(data[:, :, 2]))
    return jsonify({
        'ndvi': ndvi,
        'ndwi': ndwi,
        'red_edge_ndvi': red_edge_ndvi
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
