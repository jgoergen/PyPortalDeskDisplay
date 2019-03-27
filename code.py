import os
import time
import gc
import board
import busio
from digitalio import DigitalInOut
import pulseio
import adafruit_touchscreen
import neopixel
from adafruit_esp32spi import adafruit_esp32spi
import adafruit_esp32spi.adafruit_esp32spi_requests as requests
from adafruit_display_text.Label import Label
from adafruit_bitmap_font import bitmap_font
import storage
import adafruit_sdcard
import displayio
import audioio

from secrets import secrets

# Support functions !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

def set_backlight(val):

    global backlight

    """Adjust the TFT backlight.

    :param val: The backlight brightness. Use a value between ``0`` and ``1``, where ``0`` is
                off, and ``1`` is 100% brightness.

    """

    val = max(0, min(1.0, val))

    if backlight:
        backlight.duty_cycle = int(val * 65535)
    else:
        board.DISPLAY.auto_brightness = False
        board.DISPLAY.brightness = val

def play_file(file_name, wait_to_finish=True):
    
    global _speaker_enable
    global audio
    
    """Play a wav file.

    :param str file_name: The name of the wav file to play on the speaker.

    """
    board.DISPLAY.wait_for_frame()
    wavfile = open(file_name, "rb")
    wavedata = audioio.WaveFile(wavfile)
    _speaker_enable.value = True
    audio.play(wavedata)
    if not wait_to_finish:
        return
    while audio.playing:
        pass
    wavfile.close()
    _speaker_enable.value = False

def setBackground(file_or_color, position=None):

    global bg_file
    global bg_sprite
    global bg_group
    global primaryDisplayGroup
    global displayio

    if not position:
        position = (0, 0)  # default in top corner

    if bg_file:
        bg_file.close()

    # clear previous background
    while bg_group:
        bg_group.pop()
        
    if isinstance(file_or_color, str): # its a filenme:
        bg_file = open(file_or_color, "rb")
        background = displayio.OnDiskBitmap(bg_file)
        
        try:
            bg_sprite = displayio.TileGrid(background,
                                           pixel_shader=displayio.ColorConverter(),
                                           position=position)
        except TypeError:
            bg_sprite = displayio.TileGrid(background,
                                           pixel_shader=displayio.ColorConverter(),
                                           x=position[0], y=position[1])

    elif isinstance(file_or_color, int):
        # Make a background color fill
        color_bitmap = displayio.Bitmap(320, 240, 1)
        color_palette = displayio.Palette(1)
        color_palette[0] = file_or_color
        try:
            bg_sprite = displayio.TileGrid(color_bitmap,
                                                    pixel_shader=color_palette,
                                                    position=(0, 0))
        except TypeError:
            bg_sprite = displayio.TileGrid(color_bitmap,
                                                    pixel_shader=color_palette,
                                                    x=position[0], y=position[1])
    else:
        raise RuntimeError("Unknown type of background")

    bg_group.append(bg_sprite)
    board.DISPLAY.refresh_soon()
    gc.collect()
    board.DISPLAY.wait_for_frame()

def connectToWifi():

    global esp
    global statusNeopixel
    global secrets

    statusNeopixel.fill((0, 0, 100))
    
    while not esp.is_connected:
        # secrets dictionary must contain 'ssid' and 'password' at a minimum
        print("Connecting to AP", secrets['ssid'])
        statusNeopixel.fill((100, 0, 0)) # red = not connected
        try:
            esp.connect(secrets)
            statusNeopixel.fill((0,100,0))
        except RuntimeError as error:
            print("Cound not connect to internet", error)
            print("Retrying in 3 seconds...")
            time.sleep(3)

def loadBitmapFromUrl(url, imagePosition):
    
    global sdCard
    global wget
    global setBackground

    try:
        if sdCard:
            filename = "/sd/tempImage.bmp"
            chunk_size = 512  # current bug in big SD writes -> stick to 1 block
            
            try:
                wget(image_url, filename, chunk_size=chunk_size)

            except OSError as error:
                print(error)
                raise OSError("""\n\nNo writable filesystem found for saving datastream. Insert an SD card or set internal filesystem to be unsafe by setting 'disable_concurrent_write_protection' in the mount options in boot.py""") # pylint: disable=line-too-long
            
            setBackground(filename, imagePosition)
    finally:
        gc.collect()

def wget(url, filename, *, chunk_size=512):
    
    global statusNeopixel
    
    """Download a url and save to filename location, like the command wget.

    :param url: The URL from which to obtain the data.
    :param filename: The name of the file to save the data to.
    :param chunk_size: how much data to read/write at a time.

    """
    statusNeopixel.fill((100, 100, 0))
    r = requests.get(url, stream=True)

    content_length = int(r.headers['content-length'])
    remaining = content_length
    file = open(filename, "wb")

    for i in r.iter_content(min(remaining, chunk_size)):  # huge chunks!
        statusNeopixel.fill((0, 100, 100))
        remaining -= len(i)
        file.write(i)

        if not remaining:
            break

        statusNeopixel.fill((100, 100, 0))

    file.close()
    r.close()
    statusNeopixel.fill((0, 0, 0))

def jsonTraverse(json, path):
    value = json
    for x in path:
        value = value[x]
        gc.collect()
    return value
    
# Init !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

# Global settings
rootDirectory = ("/"+__file__).rsplit('/', 1)[0]

collegiateFont = bitmap_font.load_font(rootDirectory + "/fonts/Collegiate-50.bdf")
arialFont = bitmap_font.load_font(rootDirectory + "/fonts/Arial.bdf")

# Turn on backlight
try:
    backlight = pulseio.PWMOut(board.TFT_BACKLIGHT)  # pylint: disable=no-member
except ValueError:
    backlight = None
    
set_backlight(1.0)

# Create 'group' for drawing to display
primaryDisplayGroup = displayio.Group(max_size=15)
board.DISPLAY.show(primaryDisplayGroup)

# Create 'group' for drawing backgrounds to display
bg_file = None
bg_sprite = None
bg_group = displayio.Group(max_size=5)
primaryDisplayGroup.append(bg_group)

# Set black background
setBackground(0x000000)

progressLabel = Label(arialFont, text = str("Setting up Neopixel"))
progressLabel.x = 30
progressLabel.y = 30
progressLabel.color = 0xFFFFFF
primaryDisplayGroup.append(progressLabel)
board.DISPLAY.refresh_soon()
board.DISPLAY.wait_for_frame()

# Setup neopixel on back of unit
statusNeopixel = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.2)

progressLabel._update_text(str("Setting up Audio"))  # pylint: disable=protected-access
board.DISPLAY.refresh_soon()
board.DISPLAY.wait_for_frame()

# Enable audio and built in speaker
_speaker_enable = DigitalInOut(board.SPEAKER_ENABLE)
_speaker_enable.switch_to_output(False)
audio = audioio.AudioOut(board.AUDIO_OUT)

progressLabel._update_text(str("Setting up WIFI"))  # pylint: disable=protected-access
board.DISPLAY.refresh_soon()
board.DISPLAY.wait_for_frame()

# Enable connection to esp32
esp32_ready = DigitalInOut(board.ESP_BUSY)
esp32_gpio0 = DigitalInOut(board.ESP_GPIO0)
esp32_reset = DigitalInOut(board.ESP_RESET)
esp32_cs = DigitalInOut(board.ESP_CS)
spi = busio.SPI(board.SCK, board.MOSI, board.MISO)

esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready,
                                                esp32_reset, esp32_gpio0)
for _ in range(3): # retries
    try:
        print("ESP firmware:", esp.firmware_version)
        break
    except RuntimeError:
        print("Retrying ESP32 connection")
        time.sleep(1)
        esp.reset()
else:
    raise RuntimeError("Was not able to find ESP32")

requests.set_interface(esp)

progressLabel._update_text(str("Connecting to WIFI"))  # pylint: disable=protected-access
board.DISPLAY.refresh_soon()
board.DISPLAY.wait_for_frame()

connectToWifi()

progressLabel._update_text(str("Setting up SD Card"))  # pylint: disable=protected-access
board.DISPLAY.refresh_soon()
board.DISPLAY.wait_for_frame()
gc.collect()

# Init SD Card
sd_cs = DigitalInOut(board.SD_CS)
sdCard = None
try:
    sdCard = adafruit_sdcard.SDCard(spi, sd_cs)
    vfs = storage.VfsFat(sdCard)
    storage.mount(vfs, "/sd")
except OSError as error:
    print("No SD card found:", error)

progressLabel._update_text(str("Setting up Touch"))  # pylint: disable=protected-access
board.DISPLAY.refresh_soon()
board.DISPLAY.wait_for_frame()

# Init Touch Screen
# pylint: disable=no-member
touchscreen = adafruit_touchscreen.Touchscreen(board.TOUCH_XL, board.TOUCH_XR,
                                               board.TOUCH_YD, board.TOUCH_YU,
                                               calibration=((5200, 59000),
                                                           (5800, 57000)),
                                               size=(320, 240))
# pylint: enable=no-member

while progressLabel:
    progressLabel.pop()

gc.collect()
board.DISPLAY.refresh_soon()
board.DISPLAY.wait_for_frame()

# Display features !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

def showGithubStats(repo):

    global rootDirectory
    global statusNeopixel
    global setBackground
    global jsonTraverse
    global board
    global collegiateFont
    global primaryDisplayGroup

    repoUrl = "https://api.github.com/repos" + repo + "?access_token="+secrets['github_token']
    starCountJsonPropPath = ["stargazers_count"]

    # get data from url
    statusNeopixel.fill((100, 100, 0))   # yellow = fetching data
    gc.collect()
    r = requests.get(repoUrl)
    gc.collect()
    statusNeopixel.fill((0, 0, 100))   # green = got data
    jsonData = r.json()
    r.close()
    gc.collect()

    starCount = jsonTraverse(jsonData, starCountJsonPropPath)

    # display data
    starCount = Label(collegiateFont, text = str(starCount))
    starCount.x = 200
    starCount.y = 100
    starCount.color = 0xFFFFFF
    primaryDisplayGroup.append(starCount)

    # load github stat background
    setBackground(rootDirectory + "/githubstar.bmp")

    # wait 
    time.sleep(60)

    # cleanup!
    while starCount:
        starCount.pop()

# Main loop !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

while True:
    
    # board.DISPLAY.show(self.splash)
    # for i in range(100, -1, -1):  # dim down
    #     self.set_backlight(i/100)
    #     time.sleep(0.005)
    # self.setBackground(bootscreen)
    # board.DISPLAY.wait_for_frame()
    # for i in range(100):  # dim up
    #     self.set_backlight(i/100)
    #     time.sleep(0.005)
    # time.sleep(2)

    # create label
    # newCaption = Label(self._caption_font, text=str(caption_text))
    # newCaption.x = caption_position[0]
    # newCaption.y = caption_position[1]
    # newCaption.color = caption_color
    # self.splash.append(newCaption)

    # update label text
    # self._caption._update_text(str(caption_text))  # pylint: disable=protected-access
    # board.DISPLAY.refresh_soon()
    # board.DISPLAY.wait_for_frame()

    # get data from url
    # self.statusNeopixel.fill((100, 100, 0))   # yellow = fetching data
    # gc.collect()
    # r = requests.get(self._url)
    # gc.collect()
    # self.statusNeopixel.fill((0, 0, 100))   # green = got data

    # if it's json data
    # jsonData = r.json()
    # gc.collect()

    # dispose of your request!
    # r.close()

    showGithubStats("/jgoergen/CamBot");

    time.sleep(60)