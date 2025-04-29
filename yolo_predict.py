from datetime import datetime
from ultralytics import YOLO
from pathlib import Path
from sqlite3 import Connection

def copy_and_rename_pathlib(src_path, dest_path, new_name):
	# Create Path objects
	src_path = Path(src_path)
	dest_path = Path(dest_path)
	# Copy and rename the file
	new_path = dest_path / new_name
	src_path.rename(new_path)
    
def prediction(img):
    model = YOLO('yolo11n.pt')
    timestamp_jpg = img
    timestamp = img[:-4]
    img = f"static/img/{img}"
    save_location = "static/img/predictions" # mappe hvor billede skal gemmes
    result = model.predict(img, save=True, imgsz=640, conf=0.4, iou=0.3, project=save_location, name=timestamp)
    
    r = result[0] # få det første resultat som liste med Result objekter
    summary = r.summary() # metoden summary returnerer en liste med dictionaries
    
    copy_and_rename_pathlib(f"{save_location}/{timestamp}/{timestamp_jpg}", save_location, timestamp_jpg)
    path = Path(f"/static/img/predictions/{timestamp}").relative_to('/').rmdir()
    print(f"Successfully Created File, renamed and deleted dir {path}")
    return timestamp, timestamp_jpg, summary