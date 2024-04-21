import os, io, logging, json, time, re
from datetime import datetime
from threading import Condition
import threading


from flask import Flask, render_template, request, jsonify, Response, send_file, abort

from PIL import Image

from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput
from libcamera import Transform, controls

# Int Flask
app = Flask(__name__)

# Int Picamera2 and default settings
picam2 = Picamera2()

# Int Picamera2 and default settings
timelapse_running = False
timelapse_thread = None

# Get the directory of the current script
current_dir = os.path.dirname(os.path.abspath(__file__))
# Define the path to the camera-config.json file
camera_config_path = os.path.join(current_dir, 'camera-config.json')
# Pull settings from from config file
with open(camera_config_path, "r") as file:
    camera_config = json.load(file)
# Print config for validation
print(f'\nCamera Config:\n{camera_config}\n')

# Split config for different uses
live_settings = camera_config.get('controls', {})
rotation_settings = camera_config.get('rotation', {})
sensor_mode = camera_config.get('sensor-mode', 1)
capture_settings = camera_config.get('capture-settings', {}) 

# Parse the selected capture resolution for later
selected_resolution = capture_settings["Resolution"]
resolution = capture_settings["available-resolutions"][selected_resolution]
print(f'\nCamera Settings:\n{capture_settings}\n')
print(f'\nCamera Set Resolution:\n{resolution}\n')

# Get the sensor modes and pick from the the camera_config
camera_modes = picam2.sensor_modes
mode = picam2.sensor_modes[sensor_mode]

# Create the video_config 
video_config = picam2.create_video_configuration(main={'size':resolution}, sensor={'output_size': mode['size'], 'bit_depth': mode['bit_depth']})
print(f'\nVideo Config:\n{video_config}\n')

# Pull default settings and filter live_settings for anything picamera2 wont use (because the not all cameras use all settings)
default_settings = picam2.camera_controls
live_settings = {key: value for key, value in live_settings.items() if key in default_settings}

# Define the path to the camera-module-info.json file
camera_module_info_path = os.path.join(current_dir, 'camera-module-info.json')
# Load camera modules data from the JSON file
with open(camera_module_info_path, "r") as file:
    camera_module_info = json.load(file)
camera_properties = picam2.camera_properties
print(f'\nPicamera2 Camera Properties:\n{camera_properties}\n')

# Set the path where the images will be stored
UPLOAD_FOLDER = os.path.join(current_dir, 'static/gallery')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create the upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

####################
# Streaming Class
####################

output = None
class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

def generate():
    global output
    while True:
        with output.condition:
            output.condition.wait()
            frame = output.frame
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

####################
# Load Config from file Function
####################

# Load camera settings from config file
def load_settings(settings_file):
    try:
        with open(settings_file, 'r') as file:
            settings = json.load(file)
            print(settings)
            return settings
    except FileNotFoundError:
        # Return default settings if the file is not found
        logging.error(f"Settings file {settings_file} not found")
        return None
    except Exception as e:
        logging.error(f"Error loading camera settings: {e}")
        return None

####################
# Site Routes (routes to actual pages)
####################
@app.route("/")
def home():
    return render_template("camerasettings.html", title="Picamera2 WebUI Lite", live_settings=live_settings, rotation_settings=rotation_settings, settings_from_camera=default_settings, capture_settings=capture_settings)

@app.route("/beta")
def beta():
    return render_template("beta.html", title="beta")

@app.route("/camera_info")
def camera_info():
    connected_camera = picam2.camera_properties['Model']
    connected_camera_data = next((module for module in camera_module_info["camera_modules"] if module["sensor_model"] == connected_camera), None)
    if connected_camera_data:
        return render_template("camera_info.html", title="Camera Info", connected_camera_data=connected_camera_data, camera_modes=camera_modes, sensor_mode=sensor_mode)
    else:
        return jsonify(error="Camera module data not found")

@app.route("/about")
def about():
    return render_template("about.html", title="About Picamera2 WebUI Lite")

@app.route('/video_feed')
def video_feed():
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/snapshot')
def snapshot():
    # Capture an image
    take_snapshot()
    # Wait for a few seconds to ensure the image is saved
    time.sleep(2)
    # Return the image file
    image_name = f'snapshot/pimage_snapshot.jpg'
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], image_name)
    return send_file(filepath, mimetype='image/jpg')

####################
# Setting Routes (routes that manipulate settings)
####################

# Route to update settings to the buffer
@app.route('/update_live_settings', methods=['POST'])
def update_settings():
    global live_settings, capture_settings, picam2, video_config, resolution, sensor_mode, mode
    try:
        # Parse JSON data from the request
        data = request.get_json()
        print(data)
        # Update only the keys that are present in the data
        for key in data:
            if key in live_settings:
                print(key)
                if key in ('AfMode', 'AeConstraintMode', 'AeExposureMode', 'AeFlickerMode', 'AeFlickerPeriod', 'AeMeteringMode', 'AfRange', 'AfSpeed', 'AwbMode', 'ExposureTime') :
                    live_settings[key] = int(data[key])
                elif key in ('Brightness', 'Contrast', 'Saturation', 'Sharpness', 'ExposureValue', 'LensPosition'):
                    live_settings[key] = float(data[key])
                elif key in ('AeEnable', 'AwbEnable', 'ScalerCrop'):
                    live_settings[key] = data[key]
                # Update the configuration of the video feed
                configure_camera(live_settings)
                return jsonify(success=True, message="Settings updated successfully", settings=live_settings)
            elif key in capture_settings:
                if key in ('Resolution'):
                    capture_settings['Resolution'] = int(data[key])
                    selected_resolution = int(data[key])
                    resolution = capture_settings["available-resolutions"][selected_resolution]
                    stop_camera_stream()
                    video_config = picam2.create_video_configuration(main={'size':resolution}, sensor={'output_size': mode['size'], 'bit_depth': mode['bit_depth']})
                    start_camera_stream()
                    return jsonify(success=True, message="Settings updated successfully", settings=capture_settings)
                elif key in ('makeRaw'):
                    capture_settings[key] = data[key]
                    return jsonify(success=True, message="Settings updated successfully", settings=capture_settings)
            elif key == ('sensor_mode'):
                sensor_mode = int(data[key])
                mode = picam2.sensor_modes[sensor_mode]
                stop_camera_stream()
                video_config = picam2.create_video_configuration(main={'size':resolution}, sensor={'output_size': mode['size'], 'bit_depth': mode['bit_depth']})
                start_camera_stream()
                save_sensor_mode(sensor_mode)
                return jsonify(success=True, message="Settings updated successfully", settings=sensor_mode)
    except Exception as e:
        return jsonify(success=False, message=str(e))

# Route to update settings that requires a restart of the stream
@app.route('/update_restart_settings', methods=['POST'])
def update_restart_settings():
    global rotation_settings, video_config
    try:
        data = request.get_json()
        stop_camera_stream()
        transform = Transform()
        # Update settings that require a restart
        for key, value in data.items():
            if key in rotation_settings:
                if key in ('hflip', 'vflip'):
                    rotation_settings[key] = data[key]
                    setattr(transform, key, value)
                video_config["transform"] = transform     
        start_camera_stream()
        return jsonify(success=True, message="Restart settings updated successfully", settings=live_settings)
    except Exception as e:
        return jsonify(success=False, message=str(e))

@app.route('/reset_default_live_settings', methods=['GET'])
def reset_default_live_settings():
    global live_settings, rotation_settings
    try:
        # Get the default settings from picam2.camera_controls
        default_settings = picam2.camera_controls

        # Apply only the default values to live_settings
        for key in default_settings:
            if key in live_settings:
                min_value, max_value, default_value = default_settings[key]
                live_settings[key] = default_value if default_value is not None else max_value
        configure_camera(live_settings)

        # Reset rotation settings and restart stream
        for key, value in rotation_settings.items():
            rotation_settings[key] = 0
        restart_configure_camera(rotation_settings)

        return jsonify(data1=live_settings, data2=rotation_settings)
    except Exception as e:
        return jsonify(error=str(e))

# Add a new route to save settings
@app.route('/save_settings', methods=['GET'])
def save_settings():
    global live_settings, rotation_settings, capture_settings, camera_config
    try:
        with open('camera-config.json', 'r') as file:
            camera_config = json.load(file)

        # Update controls in the configuration with live_settings
        for key, value in live_settings.items():
            if key in camera_config['controls']:
                camera_config['controls'][key] = value

        # Update controls in the configuration with rotation settings
        for key, value in rotation_settings.items():
            if key in camera_config['rotation']:
                camera_config['rotation'][key] = value

        # Update controls in the configuration with rotation settings
        for key, value in capture_settings.items():
            if key in camera_config['capture-settings']:
                camera_config['capture-settings'][key] = value
        
        # Save current camera settings to the JSON file
        with open('camera-config.json', 'w') as file:
            json.dump(camera_config, file, indent=4)

        return jsonify(success=True, message="Settings saved successfully")
    except Exception as e:
        logging.error(f"Error in saving data: {e}")
        return jsonify(success=False, message=str(e))
    
def save_sensor_mode(sensor_mode):
    try:
        with open('camera-config.json', 'r') as file:
            camera_config = json.load(file)

        # Update sensor mode
        camera_config['sensor-mode'] = sensor_mode
        
        # Save current camera settings to the JSON file
        with open('camera-config.json', 'w') as file:
            json.dump(camera_config, file, indent=4)

        return jsonify(success=True, message="Settings saved successfully")
    except Exception as e:
        logging.error(f"Error in saving data: {e}")
        return jsonify(success=False, message=str(e))

####################
# Start/Stop Steam and Take photo
####################

def start_camera_stream():
    global picam2, output, video_config
    picam2.configure(video_config)
    output = StreamingOutput()
    picam2.start_recording(JpegEncoder(), FileOutput(output))
    metadata = picam2.capture_metadata()
    time.sleep(1)

def stop_camera_stream():
    global picam2
    picam2.stop_recording()
    time.sleep(1)

# Define the route for capturing a photo
@app.route('/capture_photo', methods=['POST'])
def capture_photo():
    try:
        take_photo()  # Call your take_photo function
        time.sleep(1)
        return jsonify(success=True, message="Photo captured successfully")
    except Exception as e:
        return jsonify(success=False, message=str(e))

# Route to stop the timelapse
@app.route('/stop_timelapse', methods=['POST'])
def stop_timelapse():
    global timelapse_running, timelapse_thread
    print("Stop timelapse button pressed")
    # Check if the timelapse is running
    if timelapse_running:
        # Set the timelapse flag to False
        timelapse_running = False
        
        # Wait for the timelapse thread to finish
        if timelapse_thread:
            timelapse_thread.join()
        
        return jsonify(success=True, message="Timelapse stopped successfully")
    else:
        print("Timelapse is not running")
        return jsonify(success=True, message="Timelapse is not running")
 
 # Route to start the timelapse
@app.route('/start_timelapse', methods=['POST'])
def start_timelapse():
    global timelapse_running, timelapse_thread
    # Check if the timelapse is already running
    if not timelapse_running:
        # Specify the interval between images (in seconds)
        interval = 2
        
        # Set the timelapse flag to True
        timelapse_running = True
        
        # Create a new thread to run the timelapse function
        timelapse_thread = threading.Thread(target=take_lapse, args=(interval,))
        
        # Start the timelapse thread
        timelapse_thread.start()
        
        return jsonify(success=True, message="Timelapse started successfully")
    else:
        print("Timelapse is already running")
        return jsonify(success=True, message="Timelapse is already running")

# Function to take images for timelapse
def take_lapse(interval):
    global timelapse_running
    while timelapse_running:
        take_photo()
        time.sleep(interval)

def take_photo():
    global picam2, capture_settings
    try:
        timestamp = int(datetime.timestamp(datetime.now()))
        image_name = f'pimage_{timestamp}'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], image_name)
        request = picam2.capture_request()
        request.save("main", f'{filepath}.jpg')
        if capture_settings["makeRaw"]:
            request.save_dng(f'{filepath}.dng')
        request.release()
        #selected_resolution = capture_settings["Resolution"]
        #resolution = capture_settings["available-resolutions"][selected_resolution]
        #original_image = Image.open(filepath)
        #resized_image = original_image.resize(resolution)
        #resized_image.save(filepath)
        logging.info(f"Image captured successfully. Path: {filepath}")
    except Exception as e:
        logging.error(f"Error capturing image: {e}")

def take_snapshot():
    global picam2, capture_settings
    try:
        image_name = f'snapshot/pimage_snapshot'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], image_name)
        request = picam2.capture_request()
        request.save("main", f'{filepath}.jpg')
        logging.info(f"Image captured successfully. Path: {filepath}")
    except Exception as e:
        logging.error(f"Error capturing image: {e}")

####################
# Configure Camera
####################

def configure_camera(live_settings):
    picam2.set_controls(live_settings)
    time.sleep(0.5)

def restart_configure_camera(restart_settings):
        stop_camera_stream()
        transform = Transform()
        # Update settings that require a restart
        for key, value in restart_settings.items():
            if key in restart_settings:
                if key in ('hflip', 'vflip'):
                    setattr(transform, key, value)
        video_config["transform"] = transform
        start_camera_stream()

####################
# Image Gallery Functions
####################

from datetime import datetime
import os

@app.route('/image_gallery')
def image_gallery():
    try:
        image_files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith('.jpg')]
        print(image_files)

        if not image_files:
            # Handle the case where there are no files
            return render_template('no_files.html')

        # Create a list of dictionaries containing file name, timestamp, and dng presence
        files_and_timestamps = []
        for image_file in image_files:
            # Extracting Unix timestamp from the filename
            unix_timestamp = int(image_file.split('_')[-1].split('.')[0])
            timestamp = datetime.utcfromtimestamp(unix_timestamp).strftime('%Y-%m-%d %H:%M:%S')

            # Check if corresponding .dng file exists
            dng_file = os.path.splitext(image_file)[0] + '.dng'
            has_dng = os.path.exists(os.path.join(UPLOAD_FOLDER, dng_file))

            # Appending dictionary to the list
            files_and_timestamps.append({'filename': image_file, 'timestamp': timestamp, 'has_dng': has_dng, 'dng_file': dng_file})

        # Sorting the list based on Unix timestamp
        files_and_timestamps.sort(key=lambda x: x['timestamp'], reverse=True)

        # Pagination
        page = request.args.get('page', 1, type=int)
        items_per_page = 15
        total_pages = (len(files_and_timestamps) + items_per_page - 1) // items_per_page

        # Calculate the start and end page numbers for pagination
        start_page = max(1, page - 1)
        end_page = min(page + 3, total_pages)
        start_index = (page - 1) * items_per_page
        end_index = start_index + items_per_page
        files_and_timestamps_page = files_and_timestamps[start_index:end_index]

        return render_template('image_gallery.html', image_files=files_and_timestamps_page, page=page, start_page=start_page, end_page=end_page)
    except Exception as e:
        logging.error(f"Error loading image gallery: {e}")
        return render_template('error.html', error=str(e))


@app.route('/delete_image/<filename>', methods=['DELETE'])
def delete_image(filename):
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        os.remove(filepath)
        return jsonify(success=True, message="Image deleted successfully")
    except Exception as e:
        return jsonify(success=False, message=str(e))

@app.route('/view_image/<filename>', methods=['GET'])
def view_image(filename):
    # Pass the filename or any other necessary information to the template
    return render_template('view_image.html', filename=filename)

@app.route('/download_image/<filename>', methods=['GET'])
def download_image(filename):
    try:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        return send_file(image_path, as_attachment=True)
    except Exception as e:
        print(f"Error downloading image: {e}")
        abort(500)

####################
# Lets get the party started
####################

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)  # Change the level to DEBUG for more detailed logging

    # Start Camera stream
    start_camera_stream()

    # Load and set camera settings
    configure_camera(live_settings)

    # Start the Flask application
    app.run(debug=False, host='0.0.0.0', port=8080)
