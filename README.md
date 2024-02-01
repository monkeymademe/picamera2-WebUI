# Picamera2 WebUI Lite

## Overview

Picamera2 WebUI Lite is a lightweight web interface for the Raspberry Pi camera module, built on the Picamera2 library. This project provides a simple user interface to configure camera settings, capture photos, and manage images in a basic gallery.

## Features

- **Camera Settings:** Easily configure camera settings such as image rotation, exposure, white balance settings, and meny more.
- **Capture Photos:** Take photos with a single click and save them to the image gallery.
- **Image Gallery:** Veiw, delete, and download your images in a simple gallery interface.

## What Does 'Lite' Mean

This is part of a bigger project I am working on that would have some very advanced features like databases for settings and different gallery folders for example. But a lite version started to form during development so before I go down the rabbit hole of advanced features I branched this off so it nicely stands alone.

## Picamera2 Library

This project utilizes the Picamera2 library for Python. Picamera2 is the libcamera-based replacement for Picamera which was a Python interface to the Raspberry Pi's legacy camera stack. 
For more information about Picamera2, visit [Picamera2 GitHub Repository](https://github.com/raspberrypi/picamera2).

## Author

- **James Mitchell**

## Getting Started

Preinstalls

You will need to install the following:
- [flask](https://flask.palletsprojects.com/en/3.0.x/installation/#install-flask)
- [Picamera2](https://github.com/raspberrypi/picamera2)

Picamera2 may already be installed 

1. Update Raspberry Pi OS: 
```bash
sudo apt update && sudo apt upgrade
```

2. Clone the repository to your Raspberry Pi:
```bash
git clone https://github.com/your-username/picamera2-WebUI-Lite.git
```
3. Enter the directory: 
```bash
cd picamera2-WebUI-Lite
```
4. Run the application and access the web interface through your browser.
```bash
python app.py
```
5. From your broswer on connected to the same network goto the following address: 'http://**Your IP**:8080/'

## Compatibilty

- **Picamera2**

Please check [Picamera installation Requirements](https://github.com/raspberrypi/picamera2?tab=readme-ov-file#installation). Your operating system may not be compatible with Picamera2

- **Hardware**

Tested on Raspberry Pi Camera Module v3 which has focus settings. v1 is untested but if you see any bugs please post an issue. v2 and HQ has been tested settings like Auto focus that are unique to Camera Module v3 are filtered and removed when an older camera is used.

Raspberry Pi Compatibilty: 

- Pi 5 (8GB): Perfect
- Pi 4 (4GB): Perfect
- Pi 3B: Perfect
- Pi Zero v2: Slower lower frame rate on feed but very useable
- Pi Zero v1: Untested
- Older Pi's (Model A, 2B etc): Untested but expected not to work well.

## Future features

1. Set resoution
2. HDR settings
3. Noise Reduction settings
4. AfWindows (Target location iin frame to focus on)

## Known Bugs

1. When the user returns to the page the feed is square, its part of a refreash feature that reloads the feed when you leave the page and come back but due to the responsive layout it makes the feed square. If you reload the page its fine and also it does not always happen.
2. Old code tests and comments need to be flushed and sorted out. This is a hamer it in till it works project.
