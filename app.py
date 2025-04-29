from flask import Flask, render_template, redirect, url_for
from flask_socketio import SocketIO, emit
import pigpio
import libcamera
from picamera2 import Picamera2
from datetime import datetime, date
from sqlite3 import Connection
import smbus
from time import sleep
import threading
from matplotlib.figure import Figure
import base64
from io import BytesIO
from yolo_predict import copy_and_rename_pathlib, prediction

LED_GPIO_RED = 12
LED_GPIO_BLUE = 13
PUMP_GPIO = 17

pi = pigpio.pi()
pi.set_PWM_frequency(LED_GPIO_RED, 10000)
pi.set_PWM_range(LED_GPIO_RED, 100) 
pi.set_PWM_frequency(LED_GPIO_BLUE, 10000)
pi.set_PWM_range(LED_GPIO_BLUE, 100) 
pi.set_PWM_dutycycle(LED_GPIO_BLUE, 0)
pi.set_PWM_dutycycle(LED_GPIO_RED, 0)
pi.set_mode(LED_GPIO_RED, pigpio.OUTPUT)
pi.set_mode(LED_GPIO_BLUE, pigpio.OUTPUT)
if pi.get_PWM_dutycycle(LED_GPIO_RED) > 40 or pi.get_PWM_dutycycle(LED_GPIO_BLUE) > 30:
    pi.set_PWM_dutycycle(LED_GPIO_RED, 30)
    pi.set_PWM_dutycycle(LED_GPIO_BLUE, 40)
    
app = Flask(__name__)
socketio = SocketIO(app)

class WaterPump:
    def __init__(self, PUMP_GPIO_PIN=17):
        self.PUMP_GPIO_PIN = PUMP_GPIO_PIN # der står 38 på adapter
        self.pump_running = False
    
    def water_plants(self, duration_seconds):
        self.pump_running = True
        pi.write(self.PUMP_GPIO_PIN, 1)
        sleep(duration_seconds)
        pi.write(self.PUMP_GPIO_PIN, 0)
        self.pump_running = False

class ADC:
    def __init__(self, i2c_addr=0x4b):
            self.i2c_addr = i2c_addr
            self.bus = smbus.SMBus(1)
    
    def raw_adc(self):
        # Reads word (2 bytes) as int - 0 is comm byte​
        rd = self.bus.read_word_data(self.i2c_addr, 0)
        # Exchanges high and low bytes​
        data = ((rd & 0xFF) << 8) | ((rd & 0xFF00) >> 8)
        # Ignores two least significiant bits​
        data = data >> 2
        #print(data)
        return data

class LDR:
    def __init__(self):
        self.light_value = None 
        self.adc = ADC(0x48) # Composition
    
    def continous_measure(self):
        while True:
            self.light_value = self.adc.raw_adc()
            sleep(0.2)

    def start_continous_measure(self):
        soil_thread = threading.Thread(target=self.continous_measure)
        soil_thread.start()

ldr = LDR()
ldr.start_continous_measure()

class SoilMoist:
    def __init__(self, dry=682, wet=300):
        self.dry = dry
        self.wet = wet
        self.soil_moisture_percent = None 
        self.water_pump = WaterPump() # Composition
        self.adc = ADC() # Composition
        
    def soil_percent(self):
        data = self.adc.raw_adc()
        if data < self.wet:
            data = 100

        else:
            # tør måling - ADC måling * 100.0 / tør måling - våd måling. ​
            percentage = (self.dry - data) * 100.0 / (self.dry - self.wet) 
            data = round(percentage, 2)
            if percentage < 0:
                data = 0
        if data < 10:
            ...
            #print(f"Soil is dry and at {data}% moisture!")
        return data

    def insert_soilmoisture(self):
        date_time = datetime.now()
        timestamp = f"{date_time.strftime('%d-%m-%Y-%H-%M-%S')}"
        con = Connection('greenhouse.db')
        cur = con.cursor()
        moisture_percentage = self.soil_percent()
        params = (timestamp, moisture_percentage)
        sql = """INSERT INTO SoilMoisture (timestamp, moisture_percentage) VALUES(?, ?)"""  
        cur.execute(sql, params)
        con.commit()
        con.close()

    def select_soil_percentage(self, amount):
        if isinstance(amount, int) and amount > 0:
            con = Connection('greenhouse.db')
            cur = con.cursor()
            sql = f"""SELECT moisture_percentage, timestamp FROM SoilMoisture ORDER BY rowid DESC LIMIT {amount}"""
            cur.execute(sql)
            img_rows = cur.fetchall()
            print(img_rows)
            con.close()
            return img_rows

    def continous_measure(self):
        while True:
            self.soil_moisture_percent = self.soil_percent()
            sleep(0.2)
    
    def start_continous_measure(self):
        soil_thread = threading.Thread(target=self.continous_measure)
        soil_thread.start()

soil_measure = SoilMoist()
soil_measure.start_continous_measure()

@socketio.on('skru_roed')
def skru_roed(data):
    lysstyrke_roed = int(data['lysstyrke_roed'])

    if lysstyrke_roed < 0:
        lysstyrke_roed = 0

    if lysstyrke_roed > 60:
        lysstyrke_roed = 60
    print(f"rød: {lysstyrke_roed}")
    pi.set_PWM_dutycycle(LED_GPIO_RED, lysstyrke_roed)

@socketio.on('skru_blaa')
def skru_blaa(data):
    lysstyrke_blaa = int(data['lysstyrke_blaa'])

    if lysstyrke_blaa < 0:
        lysstyrke_blaa = 0

    if lysstyrke_blaa > 60:
        lysstyrke_blaa = 60
    print(f"blå: {lysstyrke_blaa}")
    pi.set_PWM_dutycycle(LED_GPIO_BLUE, lysstyrke_blaa)


def select_images(amount, table="Images"):
    if isinstance(amount, int) and amount > 0:
        if table == "Images" or table == "ImagePredictions":
            con = Connection('greenhouse.db')
            cur = con.cursor()
            sql = f"""SELECT timestamp_jpg FROM Images ORDER BY rowid DESC LIMIT {amount}"""
            cur.execute(sql)
            img_rows = cur.fetchall()
            print(img_rows)
            con.close()
            return img_rows

def insert_img(timestamp, timestamp_jpg):
    con = Connection('greenhouse.db')
    cur = con.cursor()
    params = (timestamp, timestamp_jpg)
    sql = """INSERT INTO Images (timestamp, timestamp_jpg) VALUES(?, ?)"""  
    cur.execute(sql, params)
    con.commit()
    con.close()

def take_picture():
    timestamp = datetime.now().strftime('%d-%m-%Y-%H:%M:%S')
    timestamp_jpg = f"{timestamp}.jpg"
    picam = Picamera2()
    config = picam.create_preview_configuration(main={"size": (640, 480)})
    config["transform"] = libcamera.Transform(hflip=1, vflip=1)
    picam.configure(config)    
    picam.start()
    picam.capture_file(f"static/img/{timestamp_jpg}")
    picam.close()
    insert_img(timestamp, timestamp_jpg)

def insert_prediction(timestamp, timestamp_jpg, summary):
    con = Connection('greenhouse.db')
    cur = con.cursor()
    params = (timestamp, timestamp_jpg, summary)
    sql = """INSERT INTO Images (timestamp, timestamp_jpg, summary) VALUES(?, ?, ?)"""  
    cur.execute(sql, params)
    con.commit()
    con.close()

@app.route("/take_photo/")
def take_photo():
    # tager et nyt billede
    take_picture()
    # laver et redirect tilbage til home når billedet er taget
    return redirect(url_for("home"))

@app.route("/predict_last_photo/")
def predict_last_photo():
    # hent sidste billede
    last_photo = select_images(1)[0][0]
    # prediction på sidste billede
    prediction(last_photo)
    # laver et redirect tilbage til home når billedet er taget
    return redirect(url_for("home", predicted = True)) # argument bruges til at vise predicted billede

@app.route("/")
def home():
    # tager den returnerede liste med tuples fra cur.fetchall()
    # for at få det seneste billede tages de første tuple i listen
    # derefter tages den første item i tuplen 
    return render_template("home.html", image = select_images(1)[0][0])

@app.route("/gallery/")
def gallery():
    image_rows = select_images(10)
    return render_template("gallery.html", image_rows = image_rows)

@app.route("/soil_history/")
def soil_history():
    soil_data = soil_measure.select_soil_percentage(10)
    # Generate the figure **without using pyplot**.
    fig = Figure()
    ax = fig.subplots()
    x = []
    y = []
    ax.tick_params(axis='x', which='both', rotation=30)
    fig.subplots_adjust(bottom=0.3)
    ax.set_xlabel("Timestamps")
    ax.set_ylabel("Soilmoisture %")
    for row in soil_data:
        x.append(row[1]) # timestamp
        y.append(row[0]) # moisture percentage
    ax.plot(x, y)
    # Save it to a temporary buffer.
    buf = BytesIO()
    fig.savefig(buf, format="png")
    # Embed the result in the html output.
    data = base64.b64encode(buf.getbuffer()).decode("ascii")
    return render_template("soil_history.html", soil_data = data)

@app.route("/manual_light/")
def manual_light():
    return render_template("manual_light.html", methods=['GET'])

@socketio.on('hent_soil')
def hent_soil():
    print(soil_measure.soil_moisture_percent)
    sleep(0.5)
    data = {"moist_percentage":soil_measure.soil_moisture_percent,
            "pump_state": soil_measure.water_pump.pump_running
            }
    socketio.emit('soil', data)
    
@app.route("/soil_live/")
def soil_live():
    return render_template("soil_live.html", methods=['GET'])

@socketio.on('hent_ldr')
def hent_soil():
    #print(ldr.light_value)
    sleep(0.5)
    data = {"ldr":ldr.light_value,
            }
    socketio.emit('ldr', data)
    
@app.route("/ldr_live/")
def ldr_live():
    return render_template("ldr_live.html", methods=['GET'])

if __name__ == ('__main__'):
    app.run(host="0.0.0.0", debug=True)
