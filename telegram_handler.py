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

class TelegramHandler:
    def __init__(self, chat_id):
        self.chat_id = chat_id

    def send_photo(self, photo, title):
        PHOTO_PARAMETER = {
            "chat_id": self.chat_id,
            "photo": photo,
            "caption": title,
            "disable_notification": ENABLE_NOTIFICATION,
            "parse_mode": parse_mode
        }
        
        for tries in range(MAX_RETRIES):
            try:
                action_response = requests.post(action_apiURL, {
                    "chat_id": self.chat_id, 
                    "action": "upload_photo"
                })
                photo_response = requests.post(photo_apiURL, PHOTO_PARAMETER)
                photo_response.raise_for_status()
            except:
                print("send_photo Failed, retrying once again...")
                time.sleep(4)
            else:
                print("send_photo Successful")
                return True
        return False

    def send_media_group(self, media_obj_list):
        """Send a group of media items with a single caption"""
        for tries in range(MAX_RETRIES):
            try:
                action_response = requests.post(action_apiURL, {
                    "chat_id": self.chat_id,
                    "action": "upload_photo"
                })
                
                # Make sure only the first media item has a caption
                if len(media_obj_list) > 1:
                    first_caption = media_obj_list[0].get('caption', '')
                    for item in media_obj_list[1:]:
                        item['caption'] = ''  # Remove caption from all but first item
                
                group_media_response = requests.post(
                    media_group_apiURL,
                    {
                        "chat_id": self.chat_id,
                        "media": media_obj_list,
                        "disable_notification": ENABLE_NOTIFICATION,
                    }
                )
                group_media_response.raise_for_status()
                return True
            except Exception as e:
                print(f"send_media_group Failed, retrying once again... Error: {e}")
                time.sleep(4)
        return False

    def send_animation(self, animation_url, title=None):
        # Convert .gifv to .mp4 if needed
        animation_url_ext = animation_url.rsplit(".", 1)[1]
        if animation_url_ext == "gifv":
            animation_url = animation_url.replace(animation_url_ext, "mp4")
        
        for tries in range(MAX_RETRIES):
            try:
                action_response = requests.post(action_apiURL, {
                    "chat_id": self.chat_id,
                    "action": "upload_document"
                })
                animation_response = requests.post(
                    animation_apiURL,
                    {
                        "chat_id": self.chat_id,
                        "animation": animation_url,
                        "caption": title,
                        "disable_notification": ENABLE_NOTIFICATION,
                        "parse_mode": parse_mode
                    }
                )
                animation_response.raise_for_status()
                return True
            except Exception as e:
                print("send_animation Failed, retrying once again...")
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
