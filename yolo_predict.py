from datetime import datetime
from ultralytics import YOLO
from threading import Thread
from time import sleep
from pathlib import Path

def copy_and_rename_pathlib(src_path, dest_path, new_name):
	# Create Path objects
	src_path = Path(src_path)
	dest_path = Path(dest_path)
	# Copy and rename the file
	new_path = dest_path / new_name
	src_path.rename(new_path)
    
def prediction(img):
    model = YOLO('yolo11n.pt')
    img = img
    timestamp = f"{datetime.now().strftime('%d-%m-%Y-%H-%M-%S')}"
    timestamp_jpg = f"{timestamp}.jpg"
    save_location = "static/img/predictions"
    result = model.predict(img, save=True, imgsz=640, conf=0.4, iou=0.3, project=save_location, name=timestamp)
    
    r = result[0] # få det første resultat som liste med Result objekter
    summary = r.summary() # metoden summary returnerer en liste med dictionaries
    
    copy_and_rename_pathlib(f"{save_location}/{timestamp}/{img}", save_location, f"{timestamp}.jpg")
    path = Path(f"/static/img/predictions/{timestamp}").relative_to('/').rmdir()
    print(f"Successfully Created File, renamed and deleted dir {path}")
    return timestamp, timestamp_jpg, summary

