import time
import requests
from configparser import ConfigParser

config = ConfigParser()
config.read("config.ini")

apiToken = config["Telegram"]["bot_api_key"]
ENABLE_NOTIFICATION = eval(config["Telegram"]["enable_notification"])

get_apiURL = f'https://api.telegram.org/bot{apiToken}/getUpdates'
text_apiURL = f'https://api.telegram.org/bot{apiToken}/sendMessage'
photo_apiURL = f'https://api.telegram.org/bot{apiToken}/sendPhoto'
animation_apiURL = f'https://api.telegram.org/bot{apiToken}/sendAnimation'
media_group_apiURL = f'https://api.telegram.org/bot{apiToken}/sendMediaGroup'
video_apiURL = f'https://api.telegram.org/bot{apiToken}/sendVideo'
action_apiURL = f'https://api.telegram.org/bot{apiToken}/sendChatAction'

# Parameters
parse_mode = "HTML"
MAX_RETRIES = 2
MEDIA_GROUP_LIMIT = 10  # Telegram's limit for media groups

class TelegramHandler:
    def __init__(self, chat_id):
        self.chat_id = chat_id

    def send_media_sequence(self, media_items, title):
        """
        Send multiple media items in sequence, respecting Telegram's rate limits
        
        Args:
            media_items: List of tuples (media_type, media_url)
            title: Caption for the first media item
        """
        if not media_items:
            return False

        success = True
        current_group = []
        
        for index, (media_type, media_url) in enumerate(media_items):
            # First item gets the full caption
            caption = title if index == 0 else ""
            
            media_obj = {
                "type": "photo" if media_type == "photo" else "video",
                "media": media_url,
                "caption": caption,
                "parse_mode": parse_mode
            }
            
            current_group.append(media_obj)
            
            # Send when we hit the group limit or it's the last item
            if len(current_group) == MEDIA_GROUP_LIMIT or index == len(media_items) - 1:
                if not self.send_media_group(current_group):
                    success = False
                current_group = []
                time.sleep(2)  # Add delay between groups to avoid rate limits
        
        return success

    def send_media_group(self, media_obj_list):
        """Send a group of media items as a single media group"""
        if not media_obj_list:
            return True
            
        for tries in range(MAX_RETRIES):
            try:
                action_response = requests.post(action_apiURL, {
                    "chat_id": self.chat_id,
                    "action": "upload_photo"
                })
                
                response = requests.post(
                    media_group_apiURL,
                    json={
                        "chat_id": self.chat_id,
                        "media": media_obj_list,
                        "disable_notification": ENABLE_NOTIFICATION,
                    }
                )
                response.raise_for_status()
                print(f"Successfully sent media group with {len(media_obj_list)} items")
                return True
            except Exception as e:
                print(f"send_media_group Failed, retrying... Error: {e}")
                time.sleep(4)
        return False


    def send_video(self, video_id, video_resolution, title):
        retries = 0
        posted = False
        while not posted:
            try:
                if retries >= 4:
                    break
                
                # Cap video resolution
                if video_resolution > 1080:
                    video_resolution = 1080
                elif video_resolution > 720 and video_resolution < 1000:
                    video_resolution = 720

                video_url = f"https://v.redd.it/{video_id}/DASH_{video_resolution}.mp4"
                action_response = requests.post(action_apiURL, {
                    "chat_id": self.chat_id,
                    "action": "upload_video"
                })

                video_response = requests.post(
                    video_apiURL,
                    allow_redirects=True,
                    params={
                        "chat_id": self.chat_id,
                        "video": video_url,
                        "caption": title,
                        "supports_streaming": "true",
                        "disable_notification": ENABLE_NOTIFICATION,
                        "parse_mode": parse_mode
                    }
                )
                video_response.raise_for_status()
                return True
            except requests.exceptions.HTTPError:
                video_resolution = (int(video_resolution/1.5))  # Reduce resolution
                retries += 1
        return False

    def send_gfycat(self, gfycat_id, title):
        gfycat_url = f"https://thumbs.gfycat.com/{gfycat_id}-mobile.mp4"
        
        for tries in range(MAX_RETRIES):
            try:
                action_response = requests.post(action_apiURL, {
                    "chat_id": self.chat_id,
                    "action": "upload_video"
                })
                gfycat_response = requests.post(
                    video_apiURL,
                    allow_redirects=True,
                    params={
                        "chat_id": self.chat_id,
                        "video": gfycat_url,
                        "caption": title,
                        "supports_streaming": "true",
                        "disable_notification": ENABLE_NOTIFICATION,
                        "parse_mode": parse_mode
                    }
                )
                gfycat_response.raise_for_status()
                return True
            except:
                print("send_gfycat Failed, retrying once again...")
                time.sleep(4)
        return False
