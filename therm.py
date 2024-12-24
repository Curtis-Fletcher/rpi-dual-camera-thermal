import os
import sys
import pygame
from picamera2 import Picamera2
from libcamera import Transform
import time,datetime,board,busio,math
import numpy as np
import adafruit_mlx90640
import cv2
import pygame.freetype

np.set_printoptions(suppress=True,linewidth=sys.maxsize,threshold=sys.maxsize)

i2c = busio.I2C(board.SCL, board.SDA) # setup I2C
mlx = adafruit_mlx90640.MLX90640(i2c) # begin MLX90640 with I2C comm
mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_16_HZ # set refresh rate
mlx_shape = (32,24) # mlx90640 shape
mlx_op_shape = (530,350)
mlx_op_offset = (160,40)
lut = np.zeros((256, 1, 3), dtype=np.uint8)
r_func = lambda i: round(255*math.sqrt(i/255))
g_func = lambda i: round(255*pow(i/255,3))
#b_func = lambda i: round(255*((math.sin(2 * math.pi * i / 255)) if (math.sin(2 * math.pi * i / 255))>=0 else 0) + (i-247)*32 if i>247 else 0)
def b_func(i):
    op = 0
    if (math.sin(2 * math.pi * i / 255))>=0:
        op = 255 * (math.sin(2 * math.pi * i / 255))
    if i>247:
        op += (i-247)*32
    return round(op)
lut[:, 0, 0] = np.array([r_func(ct) for ct in reversed(range(256))], dtype=np.uint8)
lut[:, 0, 1] = np.array([g_func(ct) for ct in reversed(range(256))], dtype=np.uint8)
lut[:, 0, 2] = np.array([b_func(ct) for ct in reversed(range(256))], dtype=np.uint8)
os.putenv('SDL_FBDEV', '/dev/fb1')
os.environ["SDL_FBDEV"] = "/dev/fb1"
pygame.mixer.pre_init(buffer=4096)
pygame.init()
lcd = pygame.display.set_mode((800, 480))
lcd.fill((0,0,0))
picam2 = Picamera2()
camera_cap_shape = (1640,1232)
res = (800,480)
pygame.freetype.init()
ui_font = pygame.freetype.Font("/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf", 24)
config = picam2.create_preview_configuration(main = {"size": camera_cap_shape, "format": "XRGB8888"}, transform = Transform(hflip=0, vflip=1))
picam2.configure(config)
picam2.start()
cont = True
frame = np.zeros(mlx_shape[0]*mlx_shape[1]) # 768 pts
frame1 = np.zeros(mlx_shape[0]*mlx_shape[1])
frame2 = np.zeros(mlx_shape[0]*mlx_shape[1])
frame3 = np.zeros(mlx_shape[0]*mlx_shape[1])
therm_buffer = np.zeros(shape=mlx_shape, dtype=np.uint8)
max_temp = 10
min_temp = 20

legend_shape = (60,480)
frames_offset = (-60,0)
legend_buffer = np.zeros(shape=legend_shape, dtype=np.uint8)
for j in range(0, legend_shape[1]-1):
    legend_buffer[:,j] = [j*255//legend_shape[1]]*legend_shape[0]

legend_buffer = cv2.cvtColor(legend_buffer, cv2.COLOR_GRAY2BGR)
#legend_buffer = cv2.applyColorMap(legend_buffer, cv2.COLORMAP_TURBO);
legend_buffer = cv2.LUT(legend_buffer, lut)
legend_surface  = pygame.surfarray.make_surface(legend_buffer)
legend_offset = (740, 0);
timeings = []
startt = 0
center_temp = 0
first_frame = True

def mt(wipe = False):
    global timeings,startt
    if wipe:
        lastt = 0
        tinfo = ""
        for t in timeings:
            if lastt:
                tinfo += f" {t-lastt:0.5f}, "
            lastt = t
        print ("Timings:", tinfo)
        timeings=[]
        startt = datetime.datetime.now().timestamp()
    timeings.append(datetime.datetime.now().timestamp() - startt)
        
def shadow_text(txt, position, baseline):
    txt_surface, txt_rect = ui_font.render(txt, fgcolor=(255,255,255))
    if baseline == "bottom":
        position = np.subtract(position, (0,txt_rect[1]+2))
    if baseline == "mid":
        position = np.subtract(position, (0,(txt_rect[1]/2)+1))
    lcd.blit(txt_surface, np.add(position,(0,0)), special_flags=pygame.BLEND_RGB_SUB)
    lcd.blit(txt_surface, np.add(position,(2,2)), special_flags=pygame.BLEND_RGB_SUB)
    lcd.blit(txt_surface, np.add(position,(2,0)), special_flags=pygame.BLEND_RGB_SUB)
    lcd.blit(txt_surface, np.add(position,(0,2)), special_flags=pygame.BLEND_RGB_SUB)
    lcd.blit(txt_surface, np.add(position,(1,1)), special_flags=pygame.BLEND_RGB_ADD)

def false_colour(mlx_data):
    global max_temp, min_temp, frame1, frame2, frame3, first_frame
    mlx_data[382] =  mlx_data[381] # Bad Pixel
    # Temps are about 10C out at 100C so *1.1?
    mlx_data = np.multiply(mlx_data, 1.1)
    c_max_temp=mlx_data.max()
    c_min_temp=mlx_data.min()
    frame3, frame2 = frame2, frame3
    frame2, frame1 = frame1, frame2
    frame1[:] = mlx_data
    if first_frame:
        frame1[:] = mlx_data
        frame2[:] = mlx_data
        frame3[:] = mlx_data
    mlx_data = np.add(mlx_data,frame2)
    mlx_data = np.add(mlx_data,frame3)
    mlx_data = np.divide(mlx_data,3)

    deltat = 0.0;
    if math.fabs(c_min_temp - min_temp) >= 1:
        deltat = (c_min_temp - min_temp)/5
        if math.fabs(deltat) < 1:
            min_temp = math.floor(c_min_temp)
        else: 
            min_temp += math.floor(deltat)

    if math.fabs(c_max_temp - max_temp) >= 1:
        deltat = (c_max_temp - max_temp)/5
        if deltat < 70:
            if math.fabs(deltat) < 1:
                max_temp = math.ceil(c_max_temp)
            else:
                max_temp += math.ceil(deltat)

    if max_temp == min_temp:
        min_temp-=1
        max_temp+=1

    print (f"c_max_temp:{c_max_temp} max_temp:{max_temp} deltat:{deltat}")

    for j in range(0, len(mlx_data)):
        thermval =  255 - ((mlx_data[j]-min_temp)*255/(max_temp-min_temp))
        if thermval > 255:
            thermval = 255
        if thermval < 0:
            thermval = 0
        therm_buffer[j%mlx_shape[0],j//mlx_shape[0]] = thermval
    return therm_buffer

while cont:
    events=pygame.event.get()
    for e in events:
        if (e.type == pygame.KEYDOWN and e.key == pygame.K_x):
            cont = False
        if (e.type == pygame.KEYDOWN and e.key == pygame.K_UP):
            mlx_op_offset = (mlx_op_offset[0], mlx_op_offset[1]-10)
        if (e.type == pygame.KEYDOWN and e.key == pygame.K_DOWN):
            mlx_op_offset = (mlx_op_offset[0], mlx_op_offset[1]+10)
        if (e.type == pygame.KEYDOWN and e.key == pygame.K_LEFT):
            mlx_op_offset = (mlx_op_offset[0]-10, mlx_op_offset[1])
        if (e.type == pygame.KEYDOWN and e.key == pygame.K_RIGHT):
            mlx_op_offset = (mlx_op_offset[0]+10, mlx_op_offset[1])
        if (e.type == pygame.KEYDOWN and e.key == pygame.K_PAGEUP):
            mlx_op_shape = (mlx_op_shape[0]+10, mlx_op_shape[1]+10)
        if (e.type == pygame.KEYDOWN and e.key == pygame.K_PAGEDOWN):
            mlx_op_shape = (mlx_op_shape[0]-10, mlx_op_shape[1]-10)
        if (e.type == pygame.FINGERDOWN):
            pos=e.x
            print("Mouse:", e.x, ":", e.y)
        print("Shape:", mlx_op_shape, " Offset:", mlx_op_offset, " Type:", pygame.event.event_name(e.type))

    cam_array = picam2.capture_array()
    f = cv2.cvtColor(cam_array, cv2.COLOR_BGR2RGB)
    f = cv2.resize(f, res, interpolation = cv2.INTER_CUBIC)
    blur = cv2.GaussianBlur(f,(51,51),0)
    f = f - blur
    f = f + 127*np.ones(f.shape, np.uint8)
    f = np.rot90(f)
    f = pygame.surfarray.make_surface(f)
    lcd.blit(f, frames_offset)
    mlx_start = np.add(mlx_op_offset, frames_offset)
    mlx_mid = np.add(mlx_start, np.divide(mlx_op_shape,2))
    try:
        mlx.getFrame(frame)
        first_frame = False
        center_index = (len(frame)//2)+16
        center_temp = frame[center_index]
        mono_buffer = false_colour(frame)
        coloured_therm = cv2.cvtColor(mono_buffer, cv2.COLOR_GRAY2BGR)
        coloured_therm = cv2.flip(coloured_therm,0)
        coloured_therm = cv2.LUT(coloured_therm, lut)
        #coloured_therm = cv2.applyColorMap(coloured_therm, cv2.COLORMAP_TURBO);
        coloured_therm = cv2.resize(coloured_therm, (mlx_op_shape[1], mlx_op_shape[0]), interpolation = cv2.INTER_CUBIC)
        coloured_therm  = pygame.surfarray.make_surface(coloured_therm)#
        lcd.blit(coloured_therm, np.add(mlx_op_offset,frames_offset), special_flags=pygame.BLEND_RGB_MULT)
        mlx_ch = np.add(mlx_mid, (-8,8))
        pygame.draw.line(lcd, (255,255,255), np.add(mlx_ch, (2,0)), np.add(mlx_ch, (8,0)))
        pygame.draw.line(lcd, (255,255,255), np.add(mlx_ch, (-2,0)), np.add(mlx_ch, (-8,0)))
        pygame.draw.line(lcd, (255,255,255), np.add(mlx_ch, (0,2)), np.add(mlx_ch, (0,8)))
        pygame.draw.line(lcd, (255,255,255), np.add(mlx_ch, (0,-2)), np.add(mlx_ch, (0,-8)))
    except ValueError:
        pass
    except RuntimeError:
        time.sleep(2)
        pass
    except OSError:
        time.sleep(2)
        pass
    lcd.blit(legend_surface, legend_offset)
    shadow_text(f"{max_temp:.1f}", np.add(legend_offset,(1,0)), "top")
    shadow_text(f"{min_temp:.1f}", np.add(legend_offset, (1, legend_shape[1])), "bottom")
    mid_temp = (min_temp + max_temp)/2
    shadow_text(f"{mid_temp:.1f}",np.add(legend_offset, (1, legend_shape[1]/2)), "mid")
    shadow_text(f"{center_temp:.1f}", mlx_mid, "top")
    pygame.display.update()
