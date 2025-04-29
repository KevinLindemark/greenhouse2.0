import pigpio
from time import sleep

pi = pigpio.pi()

while True:
    pi.write(17, 1)
    sleep(2)
    pi.write(17, 0)
    sleep(2)