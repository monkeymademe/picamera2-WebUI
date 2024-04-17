# Picamera2 WebUI Lite

## Overview

Picamera2 WebUI Lite is a lightweight web interface for the Raspberry Pi camera module, built on the Picamera2 library. This project provides a simple user interface to configure camera settings, capture photos, and manage images in a basic gallery.

[![Watch the Demo here](https://img.youtube.com/vi/K_pSdu5fv1M/0.jpg)](https://www.youtube.com/watch?v=K_pSdu5fv1M)


## Features

- **Camera Settings:** Easily configure camera settings such as image rotation, exposure, white balance settings, and meny more.
- **Capture Photos:** Take photos with a single click and save them to the image gallery.
- **Image Gallery:** Veiw, delete, and download your images in a simple gallery interface.

## What Does 'Lite' Mean

This is part of a bigger project I am working on that would have some very advanced features like databases for settings and different gallery folders for example. But a lite version started to form during development so before I go down the rabbit hole of advanced features I branched this off so it nicely stands alone.

## Is this a finished project

I don't think there will be ever a point I could call this finished but at the moment there are features still in testing and missing so, no this is not a finished product.

## What is Picamera2 Library

This project utilizes the Picamera2 library for Python. Picamera2 is the libcamera-based replacement for Picamera which was a Python interface to the Raspberry Pi's legacy camera stack. 
For more information about Picamera2, visit [Picamera2 GitHub Repository](https://github.com/raspberrypi/picamera2).

## Author

- **James Mitchell**

## Getting Started

Preinstalls

You will need to install the following:
- [flask](https://flask.palletsprojects.com/en/3.0.x/installation/#install-flask)
- [Picamera2](https://github.com/raspberrypi/picamera2)

As of March the bookworm version of Raspberry Pi OS has come preinstalled with both flask and Picamera2 meaning all you need to do is install git and clone the repo

Picamera2 may already be installed 

1. Update Raspberry Pi OS: 
```bash
sudo apt update && sudo apt upgrade
```

2. Clone the repository to your Raspberry Pi:
```bash
git clone https://github.com/monkeymademe/picamera2-WebUI-Lite.git
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

## Running as a service 

- Run the following command and note down the location for python which python should look like "/usr/bin/python" `which python`
- Goto the following directory `cd /etc/systemd/system/`
- Create and edit the following file `sudo nano picamera2-webui-lite.service`
- Paste this into the file, in the line "ExecStart" the 1st part should be the result of your "which python" command we did at the start (if its the same then its all good) the 2nd path is the location of the cloned repo with the app.py
  
```bash
[Unit]
Description=Picamera2 WebUI Lite Server
After=network.target
[Service]
Type=simple
ExecStart=/usr/bin/python /home/pi/picamera2-WebUI-Lite/app.py
Restart=always
[Install]
WantedBy=multi-user.target
```
- Save the file
- Run 'sudo systemctl start picamera2-webui-lite.service' to start the service 
- Run the following to check the service is running 'sudo systemctl status picamera2-webui-lite.service'
- Run the following to enable the service to its running on reboot `sudo systemctl enable picamera2-webui-lite.service`
  
## Compatibilty

- **Picamera2**

Please check [Picamera installation Requirements](https://github.com/raspberrypi/picamera2?tab=readme-ov-file#installation). Your operating system may not be compatible with Picamera2. We have has reported issues with older versions (pre bookworm) not functioning due to libcamera not being updated in older versions. I recomend even on older pi's to use bookworm.

- **Hardware**

Tested on Raspberry Pi Camera Module v3 which has focus settings. v1 is untested but if you see any bugs please post an issue. v2 and HQ has been tested settings like Auto focus that are unique to Camera Module v3 are filtered and removed when an older camera is used.

Raspberry Pi Compatibilty: 

- Pi 5 (8GB): Perfect
- Pi 4 (4GB): Perfect
- Pi 3B: Perfect
- Pi Zero v2: Slower lower frame rate on feed but very useable
- Pi Zero v1: Untested
- Older Pi's (Model A, 2B etc): Untested but expected not to work well.

## Features currently in BETA

- Timelapse is an option with the current version but it can't be configured and is unstable

## Known issues 

- Resolution settings need a rework there is an issue between old and new cameras and saving settngs for both
- If the camera is not connected the system will not load
  
## Copyright and license
Code and documentation copyright 2024 the Picamera2 WebUI Lite Authors. Code released under the MIT License. Docs released under Creative Commons.
