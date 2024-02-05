import os, io, logging, json, time, re
from datetime import datetime
from threading import Condition

from flask import Flask, render_template, request, jsonify, Response, send_file, abort

from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput
from libcamera import Transform, controls

# Int Flask
app = Flask(__name__)

# Int Picamera2 and default settings
picam2 = Picamera2()
half_resolution = [dim // 2 for dim in picam2.sensor_resolution]
full_resolution = [picam2.sensor_resolution]

# Setting the stream to half resolution for the pi4 although I think it can handel full
main_stream = {"size": half_resolution}
video_config = picam2.create_video_configuration(main_stream)
print(picam2.camera_properties['Model'])

# Set the path where the images will be stored
UPLOAD_FOLDER = 'static/gallery'
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
    return render_template("camerasettings.html", title="Home", live_settings=live_settings, restart_settings=restart_settings, settings_from_camera=default_settings)

@app.route("/beta")
def beta():
    return render_template("beta.html", title="beta")


@app.route("/about")
def about():
    return render_template("about.html", title="About Picamera2 WebUI Lite")

@app.route('/video_feed')
def video_feed():
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

####################
# Setting Routes (routes that manipulate settings)
####################

# Route to update settings to the buffer
@app.route('/update_live_settings', methods=['POST'])
def update_settings():
    global live_settings, picam2, video_config
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
    except Exception as e:
        return jsonify(success=False, message=str(e))

# Route to update settings that requires a restart of the stream
@app.route('/update_restart_settings', methods=['POST'])
def update_restart_settings():
    global restart_settings, picam2, video_config
    try:
        data = request.get_json()
        stop_camera_stream()
        transform = Transform()
        # Update settings that require a restart
        for key, value in data.items():
            if key in restart_settings:
                if key in ('hflip', 'vflip'):
                    restart_settings[key] = data[key]
                    setattr(transform, key, value)
        video_config["transform"] = transform
        start_camera_stream()
        return jsonify(success=True, message="Restart settings updated successfully", settings=live_settings)
    except Exception as e:
        return jsonify(success=False, message=str(e))

@app.route('/reset_default_live_settings', methods=['GET'])
def reset_default_live_settings():
    global live_settings, restart_settings
    try:
        live_settings = load_settings("default-live-settings.json")
        live_settings = {key: value for key, value in live_settings.items() if key in default_settings}
        restart_settings = load_settings("default-restart-settings.json")
        configure_camera(live_settings)
        restart_configure_camera(restart_settings)
        return jsonify(data1=live_settings, data2=restart_settings)
    except Exception as e:
        return jsonify(error=str(e))

# Add a new route to save settings
@app.route('/save_settings', methods=['GET'])
def save_settings():
    global live_settings, restart_settings

    try:
        # Save current camera settings to the JSON file
        with open('live-settings.json', 'w') as file:
            json.dump(live_settings, file, indent=4)
        with open('restart-settings.json', 'w') as file:
            json.dump(restart_settings, file, indent=4)

        return jsonify(success=True, message="Settings saved successfully")
    except Exception as e:
        return jsonify(success=False, message=str(e))

####################
# Start/Stop Steam and Take photo
####################

def start_camera_stream():
    global picam2, output, video_config
    #video_config = picam2.create_video_configuration()
    # Flip Camera #################### Make configurable
    # video_config["transform"] = Transform(hflip=1, vflip=1)
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

def take_photo():
    global picam2
    try:
        timestamp = int(datetime.timestamp(datetime.now()))
        image_name = f'pimage_{timestamp}.jpg'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], image_name)
        request = picam2.capture_request()
        request.save("main", filepath)
        request.release()
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

@app.route('/image_gallery')
def image_gallery():
    try:
        image_files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith(('.jpg', '.jpeg', '.png', '.gif'))]
        
        if not image_files:
            # Handle the case where there are no files
            return render_template('no_files.html')
        
        # Create a list of dictionaries containing file name and timestamp
        files_and_timestamps = []
        for image_file in image_files:
            # Extracting Unix timestamp from the filename
            unix_timestamp = int(image_file.split('_')[-1].split('.')[0])
            timestamp = datetime.utcfromtimestamp(unix_timestamp).strftime('%Y-%m-%d %H:%M:%S')
            
            # Appending dictionary to the list
            files_and_timestamps.append({'filename': image_file, 'timestamp': timestamp})
        
        # Sorting the list based on Unix timestamp
        files_and_timestamps.sort(key=lambda x: x['timestamp'], reverse=True)

        return render_template('image_gallery.html', image_files=files_and_timestamps)
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
    live_settings = load_settings("live-settings.json")
    restart_settings = load_settings("restart-settings.json")
    default_settings = picam2.camera_controls
    live_settings = {key: value for key, value in live_settings.items() if key in default_settings}
    configure_camera(live_settings)

    # Start the Flask application
    app.run(debug=False, host='0.0.0.0', port=8080)
