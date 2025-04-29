import pigpio
from time import sleep

pi = pigpio.pi()

while True:
    pi.write(13, 1)
    sleep(2)
    pi.write(13, 0)
    sleep(2)