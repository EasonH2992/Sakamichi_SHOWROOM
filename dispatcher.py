import os
import time
import json
from datetime import datetime
import pytz

# Third-party libraries
import requests
import yt_dlp

# Local modules
from discord_notifier import send_notification

# --- Constants ---

JST = pytz.timezone("Asia/Tokyo")
ROOM_BASE_URL = "https://public-api.showroom-cdn.com/room/"

# --- Initial Setup ---

try:
    with open("data.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    print("Loaded data.json configuration.")
except FileNotFoundError:
    print("ERROR: data.json not found. Exiting.")
    exit()

# List to store the status of monitored rooms
monitored_rooms_status = []

# --- Initial Status Check ---

for room_link in data["room_link_n"] + data["room_link_s"] + data["room_link_h"]:
    try:
        print(f"Checking initial status for room ID: {room_link}") 
        room_link = f"{ROOM_BASE_URL}{room_link}"

        result = requests.get(room_link, timeout=10).json()

        # Initialize status flags
        result["notification_dispatched"] = False
        result["is_currently_live"] = result.get("is_live", False) 
        
        # Custom filtering logic
        if "nekojita" in room_link and "乃木坂" not in result.get("name", ""):
            print(f"Skipping non-Nogizaka Neojita room: {result.get('name', 'Unknown')}")
            continue

        monitored_rooms_status.append(result)
        
    except requests.exceptions.RequestException as e:
        print(f"Request Error during initial check for room {room_link}: {e}")
    except Exception as e:
        print(f"Error during initial check for room {room_link}: {e}")

# --- Continuous Monitoring Loop ---

print("Start continuous monitoring loop.") 

while True:
    now = datetime.now(JST)
    
    for room in monitored_rooms_status:
        try:
            # Get the URL Key (string ID)
            room_url_key = room.get("url_key") or room.get("room_id") 
            if not room_url_key:
                #print(f"ERROR: Could not find valid URL Key for room ID {room.get('id', 'N/A')}. Skipping.")
                continue

            # Fetch the latest live status
            room_info_url = f"{ROOM_BASE_URL}{room_url_key}"
            
            response_status = requests.get(room_info_url, timeout=10)
            response_status.raise_for_status() 
            current_status = response_status.json()

            # Filter API errors
            if current_status.get("Code") == 404:
                print(f"ERROR: URL Key {room_url_key} is invalid or closed (API Code 404 JSON). Skipping this check.")
                continue
                
            is_live = current_status.get("is_live", False)
            member_name = current_status.get("name", "Unknown Member")
            is_notified = room["notification_dispatched"]
            
            # --- Core Logic: Detect Live and Dispatch Notification ---
            if is_live and not is_notified:
                current_time = datetime.now(JST)
                timestamp = current_time.strftime("[%Y/%m/%d %H:%M:%S]")

                print(f"[{timestamp}] {member_name} is LIVE! Attempting to send Discord notification.") 
                
                # Fallback URL if yt-dlp fails
                m3u8_url = "M3U8 URL Fetch Failed. (Reason: yt-dlp Error)" 
                
                try:
                    full_url = f"https://www.showroom-live.com/{room_url_key}" 
                    
                    ydl_opts = {
                        'format': 'best',
                        'quiet': True,
                        'no_warnings': True,
                        'simulate': True,
                    }
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        # Extract info without downloading
                        info = ydl.extract_info(full_url, download=False)
                        m3u8_url = info.get('url', "M3U8 URL Not Available")
                        
                        if m3u8_url == "M3U8 URL Not Available":
                             raise ValueError("yt-dlp ran successfully but no stream URL was found.")
                             
                    print(f"DEBUG: M3U8 URL successfully retrieved via yt-dlp.")
                    
                except Exception as e:
                    print(f"WARNING: Failed to fetch M3U8 URL for {member_name}: {e}")
                
                # Call Discord notification function (sends two separate messages)
                send_notification(member_name, room_url_key, m3u8_url)
                
                # Update status flags
                room["notification_dispatched"] = True
                room["is_currently_live"] = True
            
            # Reset status when stream ends
            elif not is_live and is_notified:
                room["notification_dispatched"] = False
                room["is_currently_live"] = False

                current_time = datetime.now(JST)
                timestamp = current_time.strftime("[%Y/%m/%d %H:%M:%S]")
                print(f"[{timestamp}] {member_name} stream ends.")
                
        except requests.exceptions.RequestException as req_e:
            print(f"Request Error for room {room_url_key}: {req_e}")
        except Exception as e:
            print(f"An unexpected error occurred for room {room_url_key}: {e}")

    # Sleep for 10 seconds before the next loop iteration
    time.sleep(15)