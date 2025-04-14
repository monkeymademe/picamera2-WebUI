from picamera2 import Picamera2
import json

# Set debug level to Warning
Picamera2.set_logging(Picamera2.DEBUG)
# Ask picamera2 for what cameras are connected
global_cameras = Picamera2.global_camera_info()

def print_section(title):
    print(f"\n{'=' * 10} {title} {'=' * 10}")

def main(camera):
    picam2 = Picamera2(camera['Num'])

    print_section("Camera Info")
    print(f"Model: {picam2.camera_properties.get('Model')}")
    print(f"Camera Properties Output: {picam2.camera_properties}")

    print_section("Supported Sensor Modes")
    try:
        for i, mode in enumerate(picam2.sensor_modes):
            print(f"[{i}] {mode}")
    except Exception as e:
        print(f"⚠️ Could not get sensor modes: {e}")

    print_section("Camera Controls (Defaults)")
    try:
        controls = picam2.camera_controls
        for control, data in controls.items():
            print(f"{control}: {data}")
    except Exception as e:
        print(f"Error creating Camera Controls: {e}")

    print_section("Capture Configurations")
    try:
        preview_config = picam2.create_preview_configuration()
        still_config = picam2.create_still_configuration()
        video_config = picam2.create_video_configuration()
        print("Preview:", preview_config)
        print("Still:", still_config)
        print("Video:", video_config)
    except Exception as e:
        print(f"Error creating configs: {e}")

    print_section("Control Defaults Dump (JSON)")
    try:
        print(json.dumps(controls, indent=2))
    except Exception as e:
        print(f"Error printing controls as JSON: {e}")

if __name__ == "__main__":

    for connected_camera in global_cameras:   
        main(connected_camera)