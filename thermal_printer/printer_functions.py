import argparse
import logging
import platform
import struct
import os
import sys
import time
import inspect

import usb.core
import usb.util
from PIL import Image, ImageDraw, ImageEnhance

MAX_PRINTER_DOTS_PER_LINE = 384
LOGGER = logging.getLogger('image_print.py')

# USB specific constant definitions
PIPSTA_USB_VENDOR_ID = 0x0483
PIPSTA_USB_PRODUCT_ID = 0xA19D
AP1400_USB_PRODUCT_ID = 0xA053
AP1400V_USB_PRODUCT_ID = 0xA19C

valid_usb_ids = {PIPSTA_USB_PRODUCT_ID, AP1400_USB_PRODUCT_ID, AP1400V_USB_PRODUCT_ID}

class printer_finder(object):
    def __call__(self, device):
        if device.idVendor != PIPSTA_USB_VENDOR_ID:
            return False
        return True if device.idProduct in valid_usb_ids else False

# Printer commands
SET_FONT_MODE_3 = b'\x1b!\x03'
SET_LED_MODE = b'\x1bX\x2d'
FEED_PAST_CUTTER = b'\n' * 5
SELECT_SDL_GRAPHICS = b'\x1b*\x08'

DOTS_PER_LINE = 384
BYTES_PER_DOT_LINE = DOTS_PER_LINE // 8
USB_BUSY = 66

def setup_usb():
    '''Connects to the 1st Pipsta found on the USB bus'''
    dev = usb.core.find(custom_match=printer_finder())
    if dev is None:
        raise IOError('Printer not found')

    try:
        dev.reset()
        dev.set_configuration()
    except usb.core.USBError as err:
        raise IOError('Failed to configure the printer', err)

    cfg = dev.get_active_configuration()
    interface_number = cfg[(0, 0)].bInterfaceNumber
    usb.util.claim_interface(dev, interface_number)
    alternate_setting = usb.control.get_interface(dev, interface_number)
    intf = usb.util.find_descriptor(
        cfg, bInterfaceNumber=interface_number,
        bAlternateSetting=alternate_setting)

    ep_out = usb.util.find_descriptor(
        intf,
        custom_match=lambda e:
        usb.util.endpoint_direction(e.bEndpointAddress) ==
        usb.util.ENDPOINT_OUT
    )

    if ep_out is None:
        raise IOError('Could not find an endpoint to print to')
    
    return ep_out, dev

def convert_image(image):
    '''Takes the bitmap and converts it to PIPSTA 24-bit image format'''
    image = image.convert('1')
    pixels = image.load()
    
    width, height = image.size
    imagebits = bytearray()

    for y in range(height):
        byte = 0
        for x in range(width):
            pixel = pixels[x, y]
            bit = 1 if pixel == 0 else 0
            byte = (byte << 1) | bit
            if (x + 1) % 8 == 0:
                imagebits.append(byte)
                byte = 0

        if width % 8 != 0:
            imagebits.append(byte << (8 - (width % 8)))

    LOGGER.info("Done converting image to binary format!")
    return bytes(imagebits)

def print_text(text):
    '''Prints a line of text with optional formatting.'''
    ep_out, device = setup_usb()
    
    try:
        # Set text formatting
        commands = bytearray()

        # Add text
        commands.extend(text.encode('utf-8'))
        
        # Reset formatting
        commands.extend(b'\x1b\x45\x00')  # Disable bold text
        commands.extend(b'\x1b\x2d\x00')  # Disable underline text
        
        
        # Print a line feed after the text
        ep_out.write(b'\n' * 2)
        # Send the command to print the text
        ep_out.write(commands)
        
    except usb.core.USBError as e:
        print(f"Failed to print text: {e}")
    finally:
        usb.util.dispose_resources(device)

def print_image(device, ep_out, data):
    '''Reads the data and sends it a dot line at once to the printer'''
    LOGGER.debug('Start print')
    try:
        ep_out.write(SET_FONT_MODE_3)

        dots_per_line_int = int(DOTS_PER_LINE)
        bytes_per_line = dots_per_line_int // 8

        cmd = struct.pack('3s2B', SELECT_SDL_GRAPHICS,
                          bytes_per_line & 0xFF,
                          bytes_per_line // 256)

        lines = len(data) // BYTES_PER_DOT_LINE
        lines = int(lines)

        start = 0
        for line in range(lines):
            start = line * BYTES_PER_DOT_LINE
            end = start + BYTES_PER_DOT_LINE
            
            start = int(start)
            end = int(end)
            
            ep_out.write(cmd + data[start:end])
            time.sleep(0.01)  # Small delay to prevent buffer overflow

            res = device.ctrl_transfer(0xC0, 0x0E, 0x020E, 0, 2)
            while res[0] == USB_BUSY:
                time.sleep(0.01)
                res = device.ctrl_transfer(0xC0, 0x0E, 0x020E, 0, 2)
        
        LOGGER.debug('End print')
    except Exception as e:
        LOGGER.error(f'Error during printing: {e}')
    finally:
        pass

def check_printer_ready(device):
    '''Check if the printer is ready before sending the next job.'''
    while True:
        try:
            # Check the status of the printer
            res = device.ctrl_transfer(0xC0, 0x0E, 0x020E, 0, 2)
            if res[0] != USB_BUSY:
                break  # Printer is ready
        except usb.core.USBError as e:
            LOGGER.warning(f"USB Error while checking printer status: {e}")
        time.sleep(0.1)  # Wait a bit before checking again

def print_single_image(filename):
    usb_out, device = setup_usb()
    usb_out.write(SET_LED_MODE + b'\x01')

    try:
        im = Image.open(filename)
        im = adjust_contrast(im, 1.5)  # Increase contrast by a factor of 1.5

        wpercent = (DOTS_PER_LINE / float(im.size[0]))
        hsize = int((float(im.size[1]) * float(wpercent)))
        im = im.resize((DOTS_PER_LINE, hsize), Image.LANCZOS)
        im.save("temp.png")
        
        im = load_image("temp.png")
        
        print_data = convert_image(im)
        usb_out.write(SET_LED_MODE + b'\x00')
        print_image(device, usb_out, print_data)
        
        # Check if the printer is ready for the next job
        check_printer_ready(device)
    finally:
        usb.util.dispose_resources(device)  # Properly release the USB resources
        usb_out.write(SET_LED_MODE + b'\x00')

def parse_arguments():
    '''Parse the filename argument passed to the script. If no argument is supplied, a default filename is provided.'''
    default_file = "image.png"
    parser = argparse.ArgumentParser()
    parser.add_argument('filename', help='the image file to print', nargs='?', default=default_file)
    return parser.parse_args()

def load_image(filename):
    '''Loads an image from the named png file. Note that the extension must be omitted from the parameter.'''
    if not os.path.isfile(filename):
        root_dir = os.path.dirname(os.path.abspath(inspect.stack()[-1][1]))
        filename = os.path.join(root_dir, filename)
        
    return Image.open(filename).convert('1')

def adjust_contrast(image, factor):
    '''Adjusts the contrast of the image. Factor > 1 increases contrast, 0 < factor < 1 decreases contrast.'''
    enhancer = ImageEnhance.Contrast(image)
    return enhancer.enhance(factor)

def feed_paper():
    '''Feeds the paper by a specific number of lines.'''
    ep_out, device = setup_usb()
    feed_lines = 6  # Number of lines to feed; adjust as needed
    feed_command = b'\n' * feed_lines
    
    try:
        ep_out.write(feed_command)
    except usb.core.USBError as e:
        print(f"Failed to feed paper: {e}")
    finally:
        usb.util.dispose_resources(device)

def main():
    args = parse_arguments()
    usb_out, device = setup_usb()
    usb_out.write(SET_LED_MODE + b'\x01')

    try:
        im = Image.open(args.filename)
        im = adjust_contrast(im, 4)  # Increase contrast by a factor of 1.5

        wpercent = (DOTS_PER_LINE / float(im.size[0]))
        hsize = int((float(im.size[1]) * float(wpercent)))
        im = im.resize((DOTS_PER_LINE, hsize), Image.LANCZOS)
        im.save("temp.png")
        
        im = load_image("temp.png")
        
        print_data = convert_image(im)
        usb_out.write(SET_LED_MODE + b'\x00')
        print_image(device, usb_out, print_data)
    finally:
        usb_out.write(SET_LED_MODE + b'\x00')
        
if __name__ == '__main__':
    main()