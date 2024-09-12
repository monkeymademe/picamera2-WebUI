# Picamera2 WebUI

## Overview

Picamera2 WebUI is a lightweight web interface for the Raspberry Pi camera module, built on the Picamera2 Python library and using Flask. This project provides a user interface to configure camera settings, capture photos, and manage images in a basic gallery.

### Demo

[![Watch the Demo here](https://img.youtube.com/vi/K_pSdu5fv1M/0.jpg)](https://www.youtube.com/watch?v=K_pSdu5fv1M)

## Features

- **Camera Control:** Easily configure camera settings such as image rotation, exposure, white balance settings, and many more.
- **Capture Photos:** Take photos with a single click and save them to the image gallery.
- **Image Gallery:** View, delete, and download your images in a simple gallery interface.

## Is this a finished project

I don't think there will be ever a point I could call this finished but at the moment there are features still in testing and missing so, no this is not a finished product.

## What is Picamera2 Library

This project utilizes the Picamera2 Python library. Picamera2 is the libcamera-based replacement for Picamera which was a Python interface to the Raspberry Pi's legacy camera stack. 
For more information about Picamera2, visit [Picamera2 GitHub Repository](https://github.com/raspberrypi/picamera2).

## Author

- **James Mitchell**

## Getting Started

Note: Please also see [Compatibility](#compatibilty) below

### Preinstalls / Dependencies

As of September 2024 the Bookworm version of Raspberry Pi OS (Desktop) has the required dependencies preinstalled, so you can skip to **Installation** below. If you are using the Lite version you will need to install the following:
- [flask](https://flask.palletsprojects.com/en/3.0.x/installation/#install-flask)
- [Picamera2](https://github.com/raspberrypi/picamera2)

### Installation

1. Update Raspberry Pi OS: 
```bash
sudo apt update && sudo apt upgrade -y
```
2. Clone the repository to your Raspberry Pi:
```bash
git clone https://github.com/monkeymademe/picamera2-WebUI.git
```
3. Enter the directory: 
```bash
cd picamera2-WebUI
```
4. Run the application and access the web interface through your browser.
```bash
python app.py
```
5. From your broswer, on a device connected to the same network, goto the following address: 'http://**Your IP**:8080/'

## Running as a service 

- Run the following command and note down the location for python which python should look like "/usr/bin/python" `which python`
- Goto the following directory `cd /etc/systemd/system/`
- Create and edit the following file `sudo nano picamera2-webui.service`
- Paste this into the file, in the line "ExecStart" the 1st part should be the result of your "which python" command we did at the start (if its the same then its all good) the 2nd path is the location of the cloned repo with the app.py
  
```bash
[Unit]
Description=Picamera2 WebUI Server
After=network.target
[Service]
Type=simple
ExecStart=/usr/bin/python /home/pi/picamera2-WebUI/app.py
Restart=always
[Install]
WantedBy=multi-user.target
```
- Save the file
- Run `sudo systemctl start picamera2-webui.service` to start the service 
- Run the following to check the service is running `sudo systemctl status picamera2-webui.service`
- Run the following to enable the service to its running on reboot `sudo systemctl enable picamera2-webui.service`
  
## Compatibilty

- **Raspberry Pi OS / Debian**

Please be aware that due to dependencies on newer versions of Picamera2 (see below) and Libcamera this project only works on Raspberry Pi OS Bookworm (or newer). Issues have been reported with older versions (e.g. Bullseye) not functioning due to libcamera no longer being updated on older versions of the Raspberry Pi OS. The recommendation, even on older Pi's, is to use Bookworm (or newer).

- **Picamera2**

Please check [Picamera installation Requirements](https://github.com/raspberrypi/picamera2?tab=readme-ov-file#installation). Your operating system may not be compatible with Picamera2.

There has been some reported issues with the PiCamera2 on older Raspberry Pi's: ```OSError: [Errno 12] Cannot allocate memory``` https://github.com/raspberrypi/picamera2/issues/972#issuecomment-1980573868

- **Hardware**

Tested on Raspberry Pi Camera Module v3 which has focus settings. v1 is untested but if you see any bugs please post an issue. v2 and HQ has been tested settings like Auto focus that are unique to Camera Module v3 are filtered and removed when an older camera is used.

Raspberry Pi Compatibilty: 

- Pi 5 (8GB): Perfect
- Pi 5 (4GB): Perfect
- Pi 4 (4GB): Perfect
- Pi 3B: Perfect
- Pi Zero v2: Slower lower frame rate on feed but very useable
- Pi Zero v1: Untested
- Older Pi's (Model A, 2B etc): Untested but expected not to work well.

## Features currently in BETA

- Timelapse is an option with the current version but it can't be configured and is unstable
- MultiCamera Support
- Basic GPIO Config

## Known issues 

- ScalerCrop is not working correctly
- Saving config is currently optimal and will be reworked for the next release
  
## Copyright and license

Code and documentation copyright 2024 the Picamera2 WebUI Authors. Code released under the MIT License. Docs released under Creative Commons.
