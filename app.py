import os, io, logging, json, time, re
from datetime import datetime
from threading import Condition
import threading


from flask import Flask, render_template, request, jsonify, Response, send_file, abort

from PIL import Image

from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.encoders import MJPEGEncoder
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput
from libcamera import Transform, controls

# Init Flask
app = Flask(__name__)

Picamera2.set_logging(Picamera2.DEBUG)

# Get global camera information
global_cameras = Picamera2.global_camera_info()
# global_cameras = [global_cameras[0]]


# Get the directory of the current script
current_dir = os.path.dirname(os.path.abspath(__file__))
# Define the path to the camera-config.json file
camera_config_path = os.path.join(current_dir, 'camera-config.json')

# Load the camera-module-info.json file
with open(os.path.join(current_dir, 'camera-module-info.json'), 'r') as file:
    camera_module_info = json.load(file)

# Load the JSON configuration file
with open(os.path.join(current_dir, 'camera-last-config.json'), 'r') as file:
    camera_last_config = json.load(file)

# Set the path where the images will be stored
CAMERA_CONFIG_FOLDER = os.path.join(current_dir, 'static/camera_config')
app.config['CAMERA_CONFIG_FOLDER'] = CAMERA_CONFIG_FOLDER
print(CAMERA_CONFIG_FOLDER)
# Create the upload folder if it doesn't exist
os.makedirs(app.config['CAMERA_CONFIG_FOLDER'], exist_ok=True)

# Set the path where the images will be stored
UPLOAD_FOLDER = os.path.join(current_dir, 'static/gallery')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

# Define a function to generate the stream for a specific camera
def generate_stream(camera):
    while True:
        with camera.output.condition:
            camera.output.condition.wait()
            frame = camera.output.frame
        yield (b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

# CameraObject that will store the itteration of 1 or more cameras
class CameraObject:
    def __init__(self, camera_num, camera_info):
        # Init camera to picamera2 using the camera number
        self.camera = Picamera2(camera_num)
        # Basic Camera Info (Sensor type etc)
        self.camera_info = camera_info
        # Default controls for the Camera
        self.settings = self.camera.camera_controls
        # Lists all sensor modes
        self.sensor_modes = self.camera.sensor_modes
        # Using the output from sensor_modes generate a list of available resolutions
        self.output_resolutions = self.available_resolutions()
        


        self.output = None
        # need an if statment for checking if there is config or load a default template for now this is ok cause config is assumed        
        #self.saved_config = self.load_settings_from_file(camera_info['Config_Location'])
        self.init_camera()
        print(f'\nSaved Config:\n{self.saved_config}\n')
        self.live_config = {}
        self.live_config = self.saved_config
        print(f'\nLive Config:\n{self.live_config}\n')
        print(f"\nSensor Mode:\n{self.live_config['sensor-mode']}\n")

    def build_default_config(self):
        default_config = {}
        for control, values in self.settings.items():
            if control in ['ScalerCrop', 'AfPause', 'FrameDurationLimits', 'NoiseReductionMode', 'AfMetering', 'ColourGains', 'StatsOutputEnable', 'AnalogueGain', 'AfWindows', 'AeFlickerPeriod', 'HdrMode', 'AfTrigger']:
                continue  # Skip ScalerCrop for debugging purposes
            
            if isinstance(values, tuple) and len(values) == 3:
                min_value, max_value, default_value = values
                
                # Handle default_value being None
                if default_value is None:
                    default_value = min_value  # Assign minimum value if default is None
                
                # Handle array or span types (example with ScalerCrop)
                if isinstance(min_value, (list, tuple)):
                    default_value = list(min_value)  # Convert to list if needed
                
                default_config[control] = default_value
                
        return default_config

    def available_resolutions(self):
        # Use a set to collect unique resolutions
        resolutions_set = set()
        for mode in self.sensor_modes:
            size = mode.get('size')
            if size:
                resolutions_set.add(size)
        # Convert the set back to a list
        unique_resolutions = list(resolutions_set)
        # Sort the resolutions from smallest to largest
        sorted_resolutions = sorted(unique_resolutions, key=lambda x: (x[0] * x[1], x))
        return sorted_resolutions

    def take_photo(self):
        try:
            timestamp = int(datetime.timestamp(datetime.now()))
            image_name = f'pimage_{timestamp}'
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], image_name)
            request = self.camera.capture_request()
            request.save("main", f'{filepath}.jpg')
            if self.self.live_config['controls']['capture-settings']["makeRaw"]:
                request.save_dng(f'{filepath}.dng')
            request.release()
            logging.info(f"Image captured successfully. Path: {filepath}")
        except Exception as e:
            logging.error(f"Error capturing image: {e}")

    def start_streaming(self):
        self.output = StreamingOutput()
        self.camera.start_recording(MJPEGEncoder(), output=FileOutput(self.output))
        time.sleep(1)

    def stop_streaming(self):
        self.camera.stop_recording()

    def load_settings_from_file(self, config_location):
        with open(os.path.join(CAMERA_CONFIG_FOLDER ,config_location), 'r') as file:
            return json.load(file)

    def update_settings(self, new_settings):
        self.settings.update(new_settings)

    def save_settings_to_file(self):
        with open(self.camera_info['Config_Location'], 'w') as file:
            json.dump(self.settings, file)

    def configure_camera(self):
        try:
            # Attempt to set the controls
            self.camera.set_controls(self.live_config['controls'])
            print('Controls set successfully.')
            
            # Adding a small sleep to ensure operations are completed
            time.sleep(0.5)
        except Exception as e:
            # Log the exception
            logging.error("An error occurred while configuring the camera: %s", str(e))
            print(f"An error occurred: {str(e)}")

    def init_camera(self):
        self.capture_settings = {
            "Resize": False,
            "makeRaw": False,
            "Resolution": 0
        }
        self.rotation = {
        "hflip": 0,
        "vflip": 0
        }
        self.sensor_mode = 1
        # If no config file use default generated from controls
        self.live_settings = self.build_default_config()
        # Parse the selected capture resolution for later
        selected_resolution = self.capture_settings["Resolution"]
        resolution = self.output_resolutions[selected_resolution]
        print(f'\nCamera Settings:\n{self.capture_settings}\n')
        print(f'\nCamera Set Resolution:\n{resolution}\n')

        # Get the sensor modes and pick from the the camera_config
        mode = self.camera.sensor_modes[self.sensor_mode]
        print(f'MODE Config:\n{mode}\n')
        self.video_config = self.camera.create_video_configuration(main={'size':resolution})

        # self.video_config = self.camera.create_video_configuration(main={'size':resolution}, sensor={'output_size': mode['size'], 'bit_depth': mode['bit_depth']})
        print(f'\nVideo Config:\n{self.video_config}\n')
        self.camera.configure(self.video_config)
        # Pull default settings and filter live_settings for anything picamera2 wont use (because the not all cameras use all settings)
        self.live_settings = {key: value for key, value in self.live_settings.items() if key in self.settings}
        self.camera.set_controls(self.live_settings)
        self.rotation_settings = self.rotation
        self.saved_config = {'controls':self.live_settings, 'rotation':self.rotation, 'sensor-mode':int(self.sensor_mode), 'capture-settings':self.capture_settings}

    def update_live_config(self, data):
         # Update only the keys that are present in the data
        print(data)
        for key in data:
            if key in self.live_config['controls']:
                try:
                    if key in ('AfMode', 'AeConstraintMode', 'AeExposureMode', 'AeFlickerMode', 'AeFlickerPeriod', 'AeMeteringMode', 'AfRange', 'AfSpeed', 'AwbMode', 'ExposureTime') :
                        self.live_config['controls'][key] = int(data[key])
                    elif key in ('Brightness', 'Contrast', 'Saturation', 'Sharpness', 'ExposureValue', 'LensPosition'):
                        self.live_config['controls'][key] = float(data[key])
                    elif key in ('AeEnable', 'AwbEnable', 'ScalerCrop'):
                        self.live_config['controls'][key] = data[key]
                    # Update the configuration of the video feed
                    self.configure_camera()
                    success = True
                    settings = self.live_config['controls']
                    print(settings)
                    return success, settings
                except Exception as e:
                    logging.error(f"Error capturing image: {e}")
            elif key in self.live_config['capture-settings']:
                if key == 'Resolution':
                    self.live_config['capture-settings']['Resolution'] = int(data[key])
                    selected_resolution = int(data[key])
                    resolution = self.output_resolutions[selected_resolution]
                    mode = self.camera.sensor_modes[self.sensor_mode]
                    self.stop_streaming()
                    self.video_config = self.camera.create_video_configuration(main={'size':resolution}, sensor={'output_size': mode['size'], 'bit_depth': mode['bit_depth']})
                    self.camera.configure(self.video_config)
                    self.start_streaming()
                    success = True
                    settings = self.live_config['capture-settings']
                    return success, settings
                elif key == 'makeRaw':
                    self.live_config['capture-settings'][key] = data[key]
                    success = True
                    settings = self.live_config['capture-settings']
                    return success, settings
            elif key == 'sensor-mode':
                self.sensor_mode = sensor_mode = int(data[key])
                mode = self.camera.sensor_modes[self.sensor_mode]
                print("MODE")
                print(mode)
                self.live_config['sensor-mode'] = int(data[key])
                resolution = mode['size']
                self.stop_streaming()
                try:
                    self.video_config = self.camera.create_video_configuration(main={'size': resolution})
                except Exception as e:
                    # Log the exception
                    logging.error("An error occurred while configuring the camera: %s", str(e))
                    print(f"An error occurred: {str(e)}")
                print(resolution)
                self.camera.configure(self.video_config)
                print(f'\nVideo Config:\n{self.video_config}\n')
                print(self.camera_info)
                print(self.settings)
                self.start_streaming()
                success = True
                settings = self.live_config['sensor-mode']
                return success, settings

    def apply_rotation(self,data):
        self.stop_streaming()
        transform = Transform()
        # Update settings that require a restart
        for key, value in data.items():
            if key in self.live_config['rotation']:
                if key in ('hflip', 'vflip'):
                    self.live_config['rotation'][key] = data[key]
                    setattr(transform, key, value) 
            self.video_config['transform'] = transform 
            self.camera.configure(self.video_config)
            time.sleep(0.5)
        self.start_streaming()
        success = True
        settings = self.live_config['rotation']
        return success, settings

    def take_snapshot(self,camera_num):
        try:
            image_name = f'snapshot/pimage_snapshot_{camera_num}'
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], image_name)
            request = self.camera.capture_request()
            request.save("main", f'{filepath}.jpg')
            logging.info(f"Image captured successfully. Path: {filepath}")
            return f'{filepath}.jpg'
        except Exception as e:
            logging.error(f"Error capturing image: {e}")
        
    def take_preview(self,camera_num):
        try:
            image_name = f'snapshot/pimage_preview_{camera_num}'
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], image_name)
            request = self.camera.capture_request()
            request.save("main", f'{filepath}.jpg')
            logging.info(f"Image captured successfully. Path: {filepath}")
            return f'{filepath}.jpg'
        except Exception as e:
            logging.error(f"Error capturing image: {e}")

# Init dictionary to store camera instances
cameras = {}
camera_new_config = {'cameras': []}
print(f'\nDetected Cameras:\n{global_cameras}\n')
# Iterate over each camera in the global_cameras list
for camera_info in global_cameras:
    # Flag to check if a matching camera is found in the last config
    matching_camera_found = False
    print(f'\nCamera Info:\n{camera_info}\n')
    # Get the number of the camera in the global_cameras list
    camera_num = camera_info['Num']
    # Iterate over each camera in the last config
    for camera_info_last in camera_last_config['cameras']:
        # Check if the camera number and model match
        print(camera_info_last)
        print(f"{camera_info['Num']} {camera_info_last['Num']} and {camera_info['Model']}  {camera_info_last['Model']}")
        if (camera_info['Num'] == camera_info_last['Num'] and camera_info['Model'] == camera_info_last['Model']):
            print(f"Detected camera {camera_info['Num']}: {camera_info['Model']} matched last used in config.")
            # Add the matching camera to the new config
            camera_new_config['cameras'].append(camera_info_last)
            # Set the flag to True
            matching_camera_found = True
            # Merge some data before creating object 
            camera_info['Config_Location'] = camera_new_config['cameras'][camera_num]['Config_Location']
            camera_info['Has_Config'] = camera_new_config['cameras'][camera_num]['Has_Config']
            # Create an instance of the custom CameraObject class
            camera_obj = CameraObject(camera_num, camera_info)
            # Start the camera
            camera_obj.start_streaming()
            # Add the camera instance to the dictionary
            cameras[camera_num] = camera_obj
        
    # If camera is not matching the last config, check its a pi camera if not a supported pi camera module its skipped
    if not matching_camera_found:
        is_pi_cam = False
        # Iterate over the supported Camera Modules and look for a match
        for camera_modules in camera_module_info['camera_modules']:
            if (camera_info['Model'] == camera_modules['sensor_model']):
                is_pi_cam = True
                print("Camera config has changed since last boot - Adding new Camera")
                add_camera_config = {'Num':camera_info['Num'], 'Model':camera_info['Model'], 'Is_Pi_Cam': is_pi_cam, 'Has_Config': False, 'Config_Location': f"default_{camera_info['Model']}.json"}
                camera_new_config['cameras'].append(add_camera_config)
                # Merge some data before creating object
                camera_info['Config_Location'] = camera_new_config['cameras'][camera_num]['Config_Location']
                camera_info['Has_Config'] = camera_new_config['cameras'][camera_num]['Has_Config']
                # Create an instance of the custom CameraObject class
                camera_obj = CameraObject(camera_num, camera_info)
                # Start the camera
                camera_obj.start_streaming()
                # Add the camera instance to the dictionary
                cameras[camera_num] = camera_obj 

# Print the new config for debug
print(f'\nCurrent detected compatible Cameras:\n{camera_new_config}\n')
# Write config to last config file for next reboot
with open(os.path.join(current_dir, 'camera-last-config.json'), 'w') as file:
    json.dump(camera_new_config, file, indent=4)

def get_camera_info(camera_model, camera_module_info):
    return next(
        (module for module in camera_module_info["camera_modules"] if module["sensor_model"] == camera_model),
        next(module for module in camera_module_info["camera_modules"] if module["sensor_model"] == "Unknown")
    )

####################
# Site Routes (routes to actual pages)
####################

# Define your 'home' route
@app.route('/')
def home():
    # Assuming cameras is a dictionary containing your CameraObjects
    cameras_data = [(camera_num, camera) for camera_num, camera in cameras.items()]
    camera_list = [(camera_num, camera, camera.camera_info['Model'], get_camera_info(camera.camera_info['Model'], camera_module_info)) for camera_num, camera in cameras.items()]
    # Pass cameras_data as a context variable to your template
    return render_template('home.html', title="Picamera2 WebUI", cameras_data=cameras_data, camera_list=camera_list, active_page='home')

@app.route('/control_camera_<int:camera_num>')
def control_camera(camera_num):
    cameras_data = [(camera_num, camera) for camera_num, camera in cameras.items()]
    camera = cameras.get(camera_num)
    resolutions = camera.available_resolutions()
    print(camera.live_config.get('capture-settings'))
    if camera:
        return render_template("camerasettings.html", title="Picamera2 WebUI - Camera <int:camera_num>", cameras_data=cameras_data, camera_num=camera_num, live_settings=camera.live_config.get('controls'), rotation_settings=camera.live_config.get('rotation'), settings_from_camera=camera.settings, capture_settings=camera.live_config.get('capture-settings'), resolutions=resolutions, enumerate=enumerate, active_page='control_camera')
    else:
        abort(404)

@app.route("/beta")
def beta():
    return render_template("beta.html", title="beta")

@app.route("/camera_info_<int:camera_num>")
def camera_info(camera_num):
    cameras_data = [(camera_num, camera) for camera_num, camera in cameras.items()]
    camera = cameras.get(camera_num)
    connected_camera = camera.camera_info['Model']
    connected_camera_data = next((module for module in camera_module_info["camera_modules"] if module["sensor_model"] == connected_camera), None)
    # If connected camera is not found, select the "Unknown" camera
    if connected_camera_data is None:
        connected_camera_data = next(module for module in camera_module_info["camera_modules"] if module["sensor_model"] == "Unknown")
    print(cameras_data)
    if connected_camera_data:
        return render_template("camera_info.html", title="Camera Info", cameras_data=cameras_data, camera_num=camera_num, connected_camera_data=connected_camera_data, camera_modes=camera.sensor_modes, sensor_mode=camera.live_config.get('sensor-mode'), active_page='camera_info')
    else:
        return jsonify(error="Camera module data not found")

@app.route('/capture_photo_<int:camera_num>', methods=['POST'])
def capture_photo(camera_num):
    try:
        cameras_data = [(camera_num, camera) for camera_num, camera in cameras.items()]
        camera = cameras.get(camera_num)
        camera.take_photo()  # Call your take_photo function
        time.sleep(1)
        return jsonify(success=True, message="Photo captured successfully")
    except Exception as e:
        return jsonify(success=False, message=str(e))

@app.route("/about")
def about():
    return render_template("about.html", title="About Picamera2 WebUI", active_page='about')

@app.route('/video_feed_<int:camera_num>')
def video_feed(camera_num):
    camera = cameras.get(camera_num)
    if camera:
        return Response(generate_stream(camera), mimetype='multipart/x-mixed-replace; boundary=frame')
    else:
        abort(404)


@app.route('/snapshot_<int:camera_num>')
def snapshot(camera_num):
    camera = cameras.get(camera_num)
    if camera:
        # Capture an image
        filepath = camera.take_snapshot(camera_num)
        # Wait for a few seconds to ensure the image is saved
        time.sleep(1)
        return send_file(filepath, as_attachment=False, download_name="snapshot.jpg",  mimetype='image/jpeg')
    else:
        abort(404)

@app.route('/preview_<int:camera_num>', methods=['POST'])
def preview(camera_num):
    try:
        camera = cameras.get(camera_num)
        if camera:
            # Capture an image
            filepath = camera.take_preview(camera_num)
            # Wait for a few seconds to ensure the image is saved
            time.sleep(1)
            return jsonify(success=True, message="Photo captured successfully")
    except Exception as e:
        return jsonify(success=False, message=str(e))

####################
# POST routes for saving data
####################

# Route to update settings to the buffer
@app.route('/update_live_settings_<int:camera_num>', methods=['POST'])
def update_settings(camera_num):
    cameras_data = [(camera_num, camera) for camera_num, camera in cameras.items()]
    camera = cameras.get(camera_num)
    try:
        # Parse JSON data from the request
        data = request.get_json()
        print(data)

        success, settings = camera.update_live_config(data)
        print(settings)
        return jsonify(success=success, message="Settings updated successfully", settings=settings)
    except Exception as e:
        return jsonify(success=False, message=str(e))

@app.route('/update_restart_settings_<int:camera_num>', methods=['POST'])
def update_restart_settings(camera_num):
    cameras_data = [(camera_num, camera) for camera_num, camera in cameras.items()]
    camera = cameras.get(camera_num)
    try:
        data = request.get_json()
        print(data)
        success, settings = camera.apply_rotation(data)
        return jsonify(success=True, message="Restart settings updated successfully", settings=settings)
    except Exception as e:
        return jsonify(success=False, message=str(e))



####################
# Image Gallery Functions
####################

@app.route('/image_gallery')
def image_gallery():
    # Assuming cameras is a dictionary containing your CameraObjects
    cameras_data = [(camera_num, camera) for camera_num, camera in cameras.items()]
    print(f'Camera Data {cameras_data}')
    camera_list = [(camera_num, camera, camera.camera_info['Model']) for camera_num, camera in cameras.items()]
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

        return render_template('image_gallery.html', image_files=files_and_timestamps_page, page=page, start_page=start_page, end_page=end_page, cameras_data=cameras_data, camera_list=camera_list, active_page='image_gallery')
    except Exception as e:
        logging.error(f"Error loading image gallery: {e}")
        return render_template('error.html', error=str(e), cameras_data=cameras_data, camera_list=camera_list)


if __name__ == "__main__":

    # Start the Flask application
    app.run(debug=False, host='0.0.0.0', port=8080)