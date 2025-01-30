import os
import exifread
from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
from google.cloud import vision
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB limit
app.secret_key = os.getenv('SECRET_KEY')

# Configure Google Cloud credentials
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def convert_to_decimal(coord, ref):
    try:
        degrees = coord.values[0].num / coord.values[0].den
        minutes = coord.values[1].num / coord.values[1].den
        seconds = coord.values[2].num / coord.values[2].den
        decimal = degrees + (minutes / 60) + (seconds / 3600)
        return -decimal if ref in ['S', 'W'] else decimal
    except:
        return None

def get_exif_coordinates(image_path):
    try:
        with open(image_path, 'rb') as f:
            tags = exifread.process_file(f)
            lat_ref = tags.get('GPS GPSLatitudeRef')
            lat = tags.get('GPS GPSLatitude')
            lon_ref = tags.get('GPS GPSLongitudeRef')
            lon = tags.get('GPS GPSLongitude')

            if lat and lon and lat_ref and lon_ref:
                lat = convert_to_decimal(lat, lat_ref)
                lon = convert_to_decimal(lon, lon_ref)
                return lat, lon
        return None
    except:
        return None

def detect_landmark(image_path):
    try:
        client = vision.ImageAnnotatorClient()
        with open(image_path, 'rb') as f:
            content = f.read()
        image = vision.Image(content=content)
        response = client.landmark_detection(image=image)
        landmarks = response.landmark_annotations
        return landmarks[0].description if landmarks else None
    except:
        return None

def geocode_location(landmark):
    try:
        API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')
        url = f'https://maps.googleapis.com/maps/api/geocode/json?address={landmark}&key={API_KEY}'
        response = requests.get(url).json()
        if response['results']:
            location = response['results'][0]['geometry']['location']
            return location['lat'], location['lng']
        return None
    except:
        return None

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
            
        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)
            
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Try EXIF data first
            coords = get_exif_coordinates(filepath)
            source = 'EXIF Data'
            
            # Fallback to landmark detection
            if not coords:
                landmark = detect_landmark(filepath)
                if landmark:
                    coords = geocode_location(landmark)
                    source = f'Landmark Detection: {landmark}'
            
            # Clean up uploaded file
            try:
                os.remove(filepath)
            except:
                pass
            
            if coords:
                return render_template('result.html', 
                                    lat=coords[0], 
                                    lng=coords[1],
                                    source=source,
                                    maps_api_key=os.getenv('GOOGLE_MAPS_API_KEY'))
            
            return render_template('result.html', error='Location not found')
    
    return render_template('index.html')

if __name__ == '__main__':
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
    app.run(host='0.0.0.0', port=9000, debug=True)