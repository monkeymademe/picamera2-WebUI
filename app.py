import os, io, logging, json, time, re
from datetime import datetime
from threading import Condition
import threading
import argparse


from flask import Flask, render_template, request, jsonify, Response, send_file, abort, session

import secrets

from PIL import Image

from gpiozero import Button, LED

from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.encoders import MJPEGEncoder
#from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput
from libcamera import Transform, controls

# Init Flask
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # Generates a random 32-character hexadecimal string
Picamera2.set_logging(Picamera2.DEBUG)

# Get global camera information
global_cameras = Picamera2.global_camera_info()
# global_cameras = [global_cameras[0]]

# Get the directory of the current script
current_dir = os.path.dirname(os.path.abspath(__file__))
# Define the path to the camera-config.json file
camera_config_path = os.path.join(current_dir, 'camera-config.json')
last_config_file_path = os.path.join(current_dir, 'camera-last-config.json')


# Load the camera-module-info.json file
with open(os.path.join(current_dir, 'camera-module-info.json'), 'r') as file:
    camera_module_info = json.load(file)

# Define the minimum required configuration
minimum_last_config = {
    "cameras": []
}

gpio_template = [
    {'pin': 1, 'label': '3v3 Power', 'status': 'disabled', 'color': 'warning'},
    {'pin': 2, 'label': '5v Power', 'status': 'disabled', 'color': 'danger'},
    {'pin': 3, 'label': 'GPIO 2', 'status': '', 'color': 'primary'},
    {'pin': 4, 'label': '5v Power', 'status': 'disabled', 'color': 'danger'},
    {'pin': 5, 'label': 'GPIO 3', 'status': '', 'color': 'primary'},
    {'pin': 6, 'label': 'Ground', 'status': 'disabled', 'color': 'dark'},
    {'pin': 7, 'label': 'GPIO 4', 'status': '', 'color': 'success'},
    {'pin': 8, 'label': 'GPIO 14', 'status': '', 'color': 'purple'},
    {'pin': 9, 'label': 'Ground', 'status': 'disabled', 'color': 'dark'},
    {'pin': 10, 'label': 'GPIO 10', 'status': '', 'color': 'purple'},
    {'pin': 11, 'label': 'GPIO 17', 'status': '', 'color': 'success'},
    {'pin': 12, 'label': 'GPIO 18', 'status': '', 'color': 'info'},
    {'pin': 13, 'label': 'GPIO 27', 'status': '', 'color': 'success'},
    {'pin': 14, 'label': 'Ground', 'status': 'disabled', 'color': 'dark'},
    {'pin': 15, 'label': 'GPIO 22', 'status': '', 'color': 'success'},
    {'pin': 16, 'label': 'GPIO 23', 'status': '', 'color': 'success'},
    {'pin': 17, 'label': '3v3 Power', 'status': 'disabled', 'color': 'warning'},
    {'pin': 18, 'label': 'GPIO 24', 'status': '', 'color': 'success'},
    {'pin': 19, 'label': 'GPIO 10', 'status': '', 'color': 'pink'},
    {'pin': 20, 'label': 'Ground', 'status': 'disabled', 'color': 'dark'},
    {'pin': 21, 'label': 'GPIO 9', 'status': '', 'color': 'pink'},
    {'pin': 22, 'label': 'GPIO 25', 'status': '', 'color': 'success'},
    {'pin': 23, 'label': 'GPIO 11', 'status': '', 'color': 'pink'},
    {'pin': 24, 'label': 'GPIO 8', 'status': '', 'color': 'pink'},
    {'pin': 25, 'label': 'Ground', 'status': 'disabled', 'color': 'dark'},
    {'pin': 26, 'label': 'GPIO 7', 'status': '', 'color': 'pink'},
    {'pin': 27, 'label': 'GPIO 0', 'status': '', 'color': 'primary'},
    {'pin': 28, 'label': 'GPIO 1', 'status': '', 'color': 'primary'},
    {'pin': 29, 'label': 'GPIO 5', 'status': '', 'color': 'success'},
    {'pin': 30, 'label': 'Ground', 'status': 'disabled', 'color': 'dark'},
    {'pin': 31, 'label': 'GPIO 6', 'status': '', 'color': 'success'},
    {'pin': 32, 'label': 'GPIO 12', 'status': '', 'color': 'success'},
    {'pin': 33, 'label': 'GPIO 13', 'status': '', 'color': 'success'},
    {'pin': 34, 'label': 'Ground', 'status': 'disabled', 'color': 'dark'},
    {'pin': 35, 'label': 'GPIO 19', 'status': '', 'color': 'info'},
    {'pin': 36, 'label': 'GPIO 16', 'status': '', 'color': 'success'},
    {'pin': 37, 'label': 'GPIO 27', 'status': '', 'color': 'success'},
    {'pin': 38, 'label': 'GPIO 20', 'status': '', 'color': 'info'},
    {'pin': 39, 'label': 'Ground', 'status': 'disabled', 'color': 'dark'},
    {'pin': 40, 'label': 'GPIO 21', 'status': '', 'color': 'info'}  
]

# Function to load or initialize configuration
def load_or_initialize_config(file_path, default_config):
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            try:
                config = json.load(file)
                if not config:  # Check if the file is empty
                    raise ValueError("Empty configuration file")
            except (json.JSONDecodeError, ValueError):
                # If file is empty or invalid, create new config
                with open(file_path, 'w') as file:
                    json.dump(default_config, file, indent=4)
                config = default_config
    else:
        # Create the file with minimum configuration if it doesn't exist
        with open(file_path, 'w') as file:
            json.dump(default_config, file, indent=4)
        config = default_config
    return config

# Load or initialize the configuration
camera_last_config = load_or_initialize_config(last_config_file_path, minimum_last_config)


# Set the path where the images will be stored
CAMERA_CONFIG_FOLDER = os.path.join(current_dir, 'static/camera_config')
app.config['CAMERA_CONFIG_FOLDER'] = CAMERA_CONFIG_FOLDER
# Create the upload folder if it doesn't exist
os.makedirs(app.config['CAMERA_CONFIG_FOLDER'], exist_ok=True)

# Set the path where the images will be stored
UPLOAD_FOLDER = os.path.join(current_dir, 'static/gallery')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.buffer = io.BytesIO()
        self.condition = Condition()

    def write(self, buf):
        # Clear the buffer before writing the new frame
        self.buffer.seek(0)
        self.buffer.truncate()
        self.buffer.write(buf)
        with self.condition:
            self.condition.notify_all()

    def read_frame(self):
        self.buffer.seek(0)
        return self.buffer.read()

# Define a function to generate the stream for a specific camera
def generate_stream(camera):
    while True:
        with camera.output.condition:
            camera.output.condition.wait()  # Wait for the new frame to be available
            frame = camera.output.read_frame()
        if frame:
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
        self.live_config = {}
        self.init_camera()
        print(f'\nLive Config:\n{self.live_config}\n')
        print(f"\nSensor Mode:\n{self.live_config['sensor-mode']}\n")

    def build_default_config(self):
        default_config = {}
        for control, values in self.settings.items():
            if control in ['ScalerCrop', 'ScalerCrops', 'AfPause', 'FrameDurationLimits', 'NoiseReductionMode', 'AfMetering', 'ColourGains', 'StatsOutputEnable', 'AfWindows', 'AeFlickerPeriod', 'HdrMode', 'AfTrigger']:
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
    
    def setbutton(self):
        if self.live_config['GPIO']['enableGPIO']:
            if self.live_config['GPIO']['button'] >= 1:
                self.button = Button(f'BOARD{self.live_config["GPIO"]["button"]}', bounce_time = 0.1)
                self.button.when_pressed = self.take_photo
                self.current_button = self.live_config["GPIO"]["button"]
                
    def setled(self):
        if self.live_config['GPIO']['enableGPIO']:
            if self.live_config['GPIO']['led'] >= 1:
                self.led = LED(f'BOARD{self.live_config["GPIO"]["led"]}')
                self.led.on()

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
            image_name = f'pimage_cam_{self.camera_info["Num"]}_{timestamp}'
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], image_name)
            request = self.camera.capture_request()
            request.save("main", f'{filepath}.jpg')
            if self.live_config['capture-settings']["makeRaw"]:
                request.save_dng(f'{filepath}.dng')
            request.release()
            logging.info(f"Image captured successfully. Path: {filepath}")
        except Exception as e:
            logging.error(f"Error capturing image: {e}")

    def start_streaming(self):
        self.output = StreamingOutput()
        encoder = self.live_config['capture-settings'].get("Encoder", "MJPEGEncoder")
        if encoder == "MJPEGEncoder":
            self.camera.start_recording(MJPEGEncoder(), output=FileOutput(self.output))
            time.sleep(1)
        elif encoder == "JpegEncoder":
            self.camera.start_recording(JpegEncoder(), output=FileOutput(self.output))
            time.sleep(1)
        print(f'\nStarted Stream with encoder: {encoder} \n')

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
            print('\nControls set successfully.\n')
            
            # Adding a small sleep to ensure operations are completed
            time.sleep(0.5)
        except Exception as e:
            # Log the exception
            logging.error("An error occurred while configuring the camera: %s", str(e))
            print(f"\nAn error occurred: {str(e)}\n")
    
    def file_exists(self, file_name, file_path):
        file = os.path.join(file_path ,file_name)
        return os.path.exists(file)

    def init_camera(self):
        if self.camera_info['Has_Config']:
            file_name = self.camera_info['Config_Location']
            if self.file_exists(file_name, CAMERA_CONFIG_FOLDER):
                self.config_from_file(file_name)
            else:
                self.default_camera_settings()
        else:
            self.default_camera_settings()


    def default_camera_settings(self):
        self.capture_settings = {
            "Resize": False,
            "makeRaw": False,
            "Resolution": 0,
            "Encoder": "MJPEGEncoder"
        }
        self.rotation = {
            "hflip": 0,
            "vflip": 0
        }
        self.gpio = {
            "enableGPIO": False,
            "button": 0,
            "led": 0
        }
        self.sensor_mode = 0
        # If no config file use default generated from controls
        self.live_settings = self.build_default_config()
        # Parse the selected capture resolution for later
        selected_resolution = self.capture_settings["Resolution"]
        resolution = self.output_resolutions[selected_resolution]
        print(f'\nCamera Settings:\n{self.capture_settings}\n')
        print(f'\nCamera Set Resolution:\n{resolution}\n')
        self.stop_streaming()
        # Get the sensor modes and pick from the the camera_config
        mode = self.camera.sensor_modes[self.sensor_mode]
        print(f'\nSensor Mode Config:\n{mode}\n')
        self.video_config = self.camera.create_video_configuration(main={'size':resolution}, sensor={'output_size': mode['size'], 'bit_depth': mode['bit_depth']})
        print(f'\nVideo Config:\n{self.video_config}\n')
        self.camera.configure(self.video_config)
        # Pull default settings and filter live_settings for anything picamera2 wont use (because the not all cameras use all settings)
        self.live_settings = {key: value for key, value in self.live_settings.items() if key in self.settings}
        self.camera.set_controls(self.live_settings)
        self.rotation_settings = self.rotation
        self.live_config = {'controls':self.live_settings, 'rotation':self.rotation, 'sensor-mode':int(self.sensor_mode), 'capture-settings':self.capture_settings, 'GPIO':self.gpio}
        self.start_streaming()
        self.configure_camera()
        self.camera_info['Has_Config'] = False
        self.camera_info['Config_Location'] = 'default.json'
        self.setbutton()
        self.setled()
        self.update_camera_last_config()

    def config_from_file(self, file):
        newconfig = self.load_settings_from_file(file)
        print(f"\Setting New Config:\n {newconfig}\n")
        self.live_config = newconfig
        self.stop_streaming()
        self.live_config['capture-settings']['Encoder'] = self.live_config['capture-settings'].get("Encoder", "MJPEGEncoder")
        selected_resolution = self.live_config['capture-settings']['Resolution']
        resolution = self.output_resolutions[selected_resolution]
        mode = self.camera.sensor_modes[self.live_config['sensor-mode']]
        print(f'\nSensor Mode Config:\n{mode}\n')
        self.video_config = self.camera.create_video_configuration(main={'size':resolution}, sensor={'output_size': mode['size'], 'bit_depth': mode['bit_depth']})
        self.apply_rotation(self.live_config['rotation'])
        self.camera_info['Has_Config'] = True
        self.camera_info['Config_Location'] = file
        self.update_camera_last_config()
        self.setbutton()
        self.setled()
        self.start_streaming()
        self.configure_camera()

    def update_camera_last_config(self):
        global camera_last_config
        for cam in camera_last_config["cameras"]:
            if cam["Num"] == self.camera_info['Num']:
                cam["Has_Config"] = self.camera_info['Has_Config']
                cam["Config_Location"] = self.camera_info['Config_Location']
        with open(os.path.join(current_dir, 'camera-last-config.json'), 'w') as file:
            json.dump(camera_last_config, file, indent=4)

    def save_live_config(self, file):
        print(f'\Saving Live Config:\n{file}\n')
        self.live_config['Model'] = self.camera_info['Model']
        self.camera_info['Has_Config'] = True
        
        if not file.endswith(".json"):
            file += ".json"
        
        self.camera_info['Config_Location'] = file
        
        try:
            with open(os.path.join(CAMERA_CONFIG_FOLDER, file), 'w') as f:
                json.dump(self.live_config, f, indent=4)
            self.update_camera_last_config()
            return file  # Return the filename on success
        except Exception as e:
            print(f'\nAn error occurred:\n{e}\n')
            return None  # Return None or raise an exception on failure

    def update_live_config(self, data):
         # Update only the keys that are present in the data
        for key in data:
            if key in self.live_config['controls']:
                try:
                    if key in ('AfMode', 'AeConstraintMode', 'AeExposureMode', 'AeFlickerMode', 'AeFlickerPeriod', 'AeMeteringMode', 'AfRange', 'AfSpeed', 'AwbMode', 'ExposureTime') :
                        self.live_config['controls'][key] = int(data[key])
                    elif key in ('Brightness', 'Contrast', 'Saturation', 'Sharpness', 'ExposureValue', 'LensPosition', 'AnalogueGain'):
                        self.live_config['controls'][key] = float(data[key])
                    elif key in ('AeEnable', 'AwbEnable', 'ScalerCrop'):
                        self.live_config['controls'][key] = data[key]
                    # Update the configuration of the video feed
                    
                    success = True
                    settings = self.live_config['controls']
                    print(f'\nUpdated live setting:\n{settings}\n')
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
                    self.apply_rotation(self.live_config['rotation'])
                    self.start_streaming()
                    success = True
                    settings = self.live_config['capture-settings']
                    return success, settings
                elif key == 'makeRaw':
                    self.live_config['capture-settings'][key] = data[key]
                    success = True
                    settings = self.live_config['capture-settings']
                    return success, settings
                elif key == 'Encoder':
                    self.live_config['capture-settings'][key] = data[key]
                    settings = self.live_config['capture-settings']
                    self.stop_streaming()
                    time.sleep(1)
                    self.start_streaming()
                    success = True
                    return success, settings
            elif key in self.live_config['GPIO']:
                if key in ('button'):
                    self.live_config['GPIO'][key] = int(data[key])
                    success = True
                    settings = self.live_config['GPIO']
                    self.setbutton()
                    return success, settings
                elif key == 'led':
                    self.live_config['GPIO'][key] = int(data[key])
                    success = True
                    settings = self.live_config['GPIO']
                    self.setled()
                elif key == 'enableGPIO':
                    self.live_config['GPIO'][key] = data[key]
                    success = True
                    settings = self.live_config['GPIO']
                    return success, settings
            elif key == 'sensor-mode':
                self.sensor_mode = sensor_mode = int(data[key])
                selected_resolution = self.live_config['capture-settings']['Resolution']
                resolution = self.output_resolutions[selected_resolution]
                mode = self.camera.sensor_modes[self.sensor_mode]
                self.live_config['sensor-mode'] = int(data[key])
                self.stop_streaming()
                try:
                    self.video_config = self.camera.create_video_configuration(main={'size':resolution}, sensor={'output_size': mode['size'], 'bit_depth': mode['bit_depth']})
                    self.apply_rotation(self.live_config['rotation'])

                except Exception as e:
                    # Log the exception
                    logging.error("An error occurred while configuring the camera: %s", str(e))
                    print(f"\nAn error occurred:\n{str(e)}\n")
                self.camera.configure(self.video_config)
                print(f'\nVideo Config:\n{self.video_config}\n')
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

    # Check against last known config
    for camera_info_last in camera_last_config['cameras']:
        if (camera_info['Num'] == camera_info_last['Num'] and camera_info['Model'] == camera_info_last['Model']):
            print(f"\nDetected camera:\n{camera_info['Num']}: {camera_info['Model']} matched last used in config.\n")
            camera_new_config['cameras'].append(camera_info_last)
            matching_camera_found = True
            camera_info['Config_Location'] = camera_new_config['cameras'][camera_num]['Config_Location']
            camera_info['Has_Config'] = camera_new_config['cameras'][camera_num]['Has_Config']
            camera_obj = CameraObject(camera_num, camera_info)
            camera_obj.start_streaming()
            cameras[camera_num] = camera_obj
            break
    
    # If no matching camera found, check if it's a known Pi camera module
    if not matching_camera_found:
        is_pi_cam = False
        for camera_modules in camera_module_info['camera_modules']:
            if (camera_info['Model'] == camera_modules['sensor_model']):
                is_pi_cam = True
                print("\nCamera config has changed since last boot - Adding new Camera\n")
                add_camera_config = {'Num':camera_info['Num'], 'Model':camera_info['Model'], 'Is_Pi_Cam': is_pi_cam, 'Has_Config': False, 'Config_Location': f"default_{camera_info['Model']}.json"}
                camera_new_config['cameras'].append(add_camera_config)
                camera_info['Config_Location'] = camera_new_config['cameras'][camera_num]['Config_Location']
                camera_info['Has_Config'] = camera_new_config['cameras'][camera_num]['Has_Config']
                camera_obj = CameraObject(camera_num, camera_info)
                camera_obj.start_streaming()
                cameras[camera_num] = camera_obj
                break
        
        # If it's not a Pi camera or in the last config, add it anyway
        if not is_pi_cam:
            print("\nAdding a new unknown camera to the configuration\n")
            add_camera_config = {'Num':camera_info['Num'], 'Model':camera_info['Model'], 'Is_Pi_Cam': False, 'Has_Config': False, 'Config_Location': f"default_{camera_info['Model']}.json"}
            camera_new_config['cameras'].append(add_camera_config)
            camera_info['Config_Location'] = add_camera_config['Config_Location']
            camera_info['Has_Config'] = add_camera_config['Has_Config']
            camera_obj = CameraObject(camera_num, camera_info)
            camera_obj.start_streaming()
            cameras[camera_num] = camera_obj

# Print the new config for debug
print(f'\nCurrent detected compatible Cameras:\n{camera_new_config}\n')
# Write config to last config file for next reboot
camera_last_config = camera_new_config
with open(os.path.join(current_dir, 'camera-last-config.json'), 'w') as file:
    json.dump(camera_last_config, file, indent=4)



def get_camera_info(camera_model, camera_module_info):
    return next(
        (module for module in camera_module_info["camera_modules"] if module["sensor_model"] == camera_model),
        next(module for module in camera_module_info["camera_modules"] if module["sensor_model"] == "Unknown")
    )

####################
# Site Routes (routes to actual pages)
####################

@app.context_processor
def inject_theme():
    theme = session.get('theme', 'light')  # Default to 'light'
    version = "1.0.5"
    return dict(version=version, theme=theme)

@app.route('/set_theme/<theme>')
def set_theme(theme):
    session['theme'] = theme
    return 

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
    config_files = [f for f in os.listdir(CAMERA_CONFIG_FOLDER) if os.path.isfile(os.path.join(CAMERA_CONFIG_FOLDER, f))]
    config_data = []
    for file in config_files:
        with open(os.path.join(CAMERA_CONFIG_FOLDER, file), 'r') as f:
            config = json.load(f)
            camera_model = config.get('Model', 'Unknown')
            is_selected = False
            if camera.camera_info['Has_Config']:
                if camera.camera_info['Config_Location'] == file:
                    is_selected = True
            config_data.append({
                'filename': file,
                'model': camera_model,
                'is_selected': is_selected
            })
    if camera:
        return render_template("camerasettings.html", title="Picamera2 WebUI - Camera <int:camera_num>", cameras_data=cameras_data, camera_num=camera_num, live_settings=camera.live_config.get('controls'), rotation_settings=camera.live_config.get('rotation'), settings_from_camera=camera.settings, capture_settings=camera.live_config.get('capture-settings'), resolutions=resolutions, enumerate=enumerate, camera_info=camera.camera_info, config_data=config_data, active_page='control_camera')
    else:
        abort(404)

@app.route("/beta")
def beta():
    return render_template("beta.html", title="beta")

@app.route("/camera_info_<int:camera_num>")
def camera_info(camera_num):
    full_url = request.url_root.rstrip('/')
    cameras_data = [(camera_num, camera) for camera_num, camera in cameras.items()]
    camera = cameras.get(camera_num)
    connected_camera = camera.camera_info['Model']
    connected_camera_data = next((module for module in camera_module_info["camera_modules"] if module["sensor_model"] == connected_camera), None)
    # If connected camera is not found, select the "Unknown" camera
    if connected_camera_data is None:
        connected_camera_data = next(module for module in camera_module_info["camera_modules"] if module["sensor_model"] == "Unknown")
    if connected_camera_data:
        return render_template("camera_info.html", title="Camera Info", cameras_data=cameras_data, camera_num=camera_num, connected_camera_data=connected_camera_data, camera_modes=camera.sensor_modes, sensor_mode=camera.live_config.get('sensor-mode'), capture_settings=camera.live_config.get('capture-settings'), active_page='camera_info', full_url=full_url, gpio_template=gpio_template, gpio_settings=camera.live_config.get('GPIO'))
    else:
        return jsonify(error="Camera module data not found")

@app.route('/reset_default_settings_camera_<int:camera_num>', methods=['GET'])
def reset_default_settings_camera(camera_num):
    cameras_data = [(camera_num, camera) for camera_num, camera in cameras.items()]
    camera = cameras.get(camera_num)
    try:
        camera.default_camera_settings()
        resolutions = camera.available_resolutions()
        response_data = {
        'live_settings': camera.live_config.get('controls'),
        'rotation_settings': camera.live_config.get('rotation')
        }
        return jsonify(response_data)
    except Exception as e:
        return jsonify(error=str(e))

@app.route('/get_file_settings_camera_<int:camera_num>', methods=['POST'])
def get_file_settings_camera(camera_num):
    try:
        # Parse JSON data from the request
        filename = request.get_json().get('filename')
        camera = cameras.get(camera_num)
        if not camera:
            return jsonify(success=False, error="Camera not found.")
        
        camera.config_from_file(filename)
        resolutions = camera.available_resolutions()
        response_data = {
            'live_settings': camera.live_config.get('controls'),
            'rotation_settings': camera.live_config.get('rotation'),
            'capture_settings': camera.live_config.get('capture-settings'), 
            'resolutions': camera.available_resolutions(),
            'success': True
        }
        return jsonify(response_data)
    except Exception as e:
        return jsonify(success=False, error=str(e))

@app.route('/save_config_file_camera_<int:camera_num>', methods=['POST'])
def save_config_file(camera_num):
    try:
        # Fetch the filename from the request
        filename = request.get_json().get('filename')
        print(f'\nReceived filename:\n{filename}\n')
        
        # Fetch the camera object from the global 'cameras' dictionary
        camera = cameras.get(camera_num)
        if not camera:
            raise ValueError(f'\nCamera with number {camera_num} not found\n')
        
        # Call the save_live_config method on the camera object
        response_data = camera.save_live_config(filename)
        if response_data is not None:
            print(f'\nSaved config data:\n{response_data}\n')
            # Return the success response with the filename and model
            return jsonify(success=True, filename=response_data, model=camera.camera_info['Model'])
        else:
            return jsonify(success=False, error="Failed to save config file")
    except Exception as e:
        # Log the error and return an error response
        print(f'\nERROR:\n{e}\n')
        return jsonify(success=False, error=str(e))

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
    cameras_data = [(camera_num, camera) for camera_num, camera in cameras.items()]
    camera_list = [(camera_num, camera, camera.camera_info['Model'], get_camera_info(camera.camera_info['Model'], camera_module_info)) for camera_num, camera in cameras.items()]
    # Pass cameras_data as a context variable to your template
    return render_template("about.html", title="About Picamera2 WebUI", cameras_data=cameras_data, camera_list=camera_list, active_page='about')

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
        success, settings = camera.update_live_config(data)
        if success:
            camera.configure_camera()
        return jsonify(success=success, message="Settings updated successfully", settings=settings)
    except Exception as e:
        return jsonify(success=False, message=str(e))

@app.route('/update_restart_settings_<int:camera_num>', methods=['POST'])
def update_restart_settings(camera_num):
    cameras_data = [(camera_num, camera) for camera_num, camera in cameras.items()]
    camera = cameras.get(camera_num)
    try:
        data = request.get_json()
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
    camera_list = [(camera_num, camera, camera.camera_info['Model']) for camera_num, camera in cameras.items()]
    try:
        image_files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith('.jpg')]
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

            # Get the image resolution
            img = Image.open(os.path.join(UPLOAD_FOLDER, image_file))
            width, height = img.size
            img.close()

            # Appending dictionary to the list
            files_and_timestamps.append({'filename': image_file, 'timestamp': timestamp, 'has_dng': has_dng, 'dng_file': dng_file, 'width': width, 'height': height})

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
        print(f"\nError downloading image:\n{e}\n")
        abort(500)

if __name__ == "__main__":
    # Parse any argument passed from command line
    parser = argparse.ArgumentParser(description='PiCamera2 WebUI')
    parser.add_argument('--port', type=int, default=8080, help='Port number to run the web server on')
    parser.add_argument('--ip', type=str, default='0.0.0.0', help='IP to which the web server is bound to')
    args = parser.parse_args()
    
    app.run(host=args.ip, port=args.port)
