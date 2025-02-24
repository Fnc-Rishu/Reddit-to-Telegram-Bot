import time
import requests
from configparser import ConfigParser
from typing import List, Tuple, Dict, Any

config = ConfigParser()
config.read("config.ini")

class TelegramHandler:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.api_token = config["Telegram"]["bot_api_key"]
        self.enable_notification = eval(config["Telegram"]["enable_notification"])
        
        # API URLs
        self.base_url = f'https://api.telegram.org/bot{self.api_token}'
        self.photo_url = f'{self.base_url}/sendPhoto'
        self.media_group_url = f'{self.base_url}/sendMediaGroup'
        self.action_url = f'{self.base_url}/sendChatAction'
        self.video_url = f'{self.base_url}/sendVideo'
        self.animation_url = f'{self.base_url}/sendAnimation'
        
        # Constants
        self.MAX_RETRIES = 2
        self.MEDIA_GROUP_LIMIT = 10
        self.parse_mode = "HTML"

    def _send_chat_action(self, action: str) -> None:
        """Send chat action to indicate bot is processing"""
        try:
            requests.post(self.action_url, {
                "chat_id": self.chat_id,
                "action": action
            })
        except Exception as e:
            print(f"Failed to send chat action: {e}")

    def send_photo(self, photo_url: str, caption: str = "") -> bool:
        """
        Send a single photo message
        
        Args:
            photo_url: URL of the photo
            caption: Optional caption for the photo
        Returns:
            bool: Success status
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                self._send_chat_action("upload_photo")
                
                response = requests.post(
                    self.photo_url,
                    params={
                        "chat_id": self.chat_id,
                        "photo": photo_url,
                        "caption": caption,
                        "parse_mode": self.parse_mode,
                        "disable_notification": not self.enable_notification
                    }
                )
                response.raise_for_status()
                return True
                
            except Exception as e:
                print(f"Photo send failed (attempt {attempt + 1}): {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(4)
        return False

    def send_media_group(self, media_items: List[Dict[str, Any]]) -> bool:
        """Send a group of media items as a single message"""
        if not media_items:
            return True
            
        for attempt in range(self.MAX_RETRIES):
            try:
                self._send_chat_action("upload_photo")
                
                response = requests.post(
                    self.media_group_url,
                    json={
                        "chat_id": self.chat_id,
                        "media": media_items,
                        "disable_notification": not self.enable_notification
                    }
                )
                response.raise_for_status()
                print(f"Successfully sent media group with {len(media_items)} items")
                return True
                
            except Exception as e:
                print(f"Media group send failed (attempt {attempt + 1}): {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(4)
        return False

    def send_media_sequence(self, media_items: List[Tuple[str, str]], title: str) -> bool:
        """Send multiple media items as grouped messages"""
        if not media_items:
            return False

        # If there's only one media item, use send_photo
        if len(media_items) == 1:
            media_type, media_url = media_items[0]
            if media_type == "photo":
                return self.send_photo(media_url, title)
            elif media_type == "video":
                return self.send_video(media_url, title)

        success = True
        current_group = []
        total_items = len(media_items)
        
        for index, (media_type, media_url) in enumerate(media_items):
            media_obj = {
                "type": "photo" if media_type == "photo" else "video",
                "media": media_url,
                "caption": title if index == 0 else "",
                "parse_mode": self.parse_mode
            }
            
            current_group.append(media_obj)
            
            if len(current_group) == self.MEDIA_GROUP_LIMIT or index == total_items - 1:
                if not self.send_media_group(current_group):
                    success = False
                    print(f"Failed to send media group {index//self.MEDIA_GROUP_LIMIT + 1}")
                else:
                    print(f"Successfully sent media group {index//self.MEDIA_GROUP_LIMIT + 1}")
                
                current_group = []
                if index < total_items - 1:
                    time.sleep(2)
        
        return success

    def send_video(self, video_url: str, title: str, resolution: int = 1080) -> bool:
        """Send a video message"""
        for attempt in range(self.MAX_RETRIES):
            try:
                self._send_chat_action("upload_video")
                
                if resolution > 1080:
                    resolution = 1080
                elif 720 < resolution < 1000:
                    resolution = 720
                
                response = requests.post(
                    self.video_url,
                    params={
                        "chat_id": self.chat_id,
                        "video": video_url,
                        "caption": title,
                        "supports_streaming": "true",
                        "disable_notification": not self.enable_notification,
                        "parse_mode": self.parse_mode
                    },
                    allow_redirects=True
                )
                response.raise_for_status()
                return True
                
            except Exception as e:
                print(f"Video send failed (attempt {attempt + 1}): {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(4)
                    resolution = int(resolution / 1.5)
        return False

    def send_animation(self, animation_url: str, title: str) -> bool:
        """Send an animation/GIF message"""
        for attempt in range(self.MAX_RETRIES):
            try:
                self._send_chat_action("upload_video")
                
                response = requests.post(
                    self.animation_url,
                    params={
                        "chat_id": self.chat_id,
                        "animation": animation_url,
                        "caption": title,
                        "parse_mode": self.parse_mode,
                        "disable_notification": not self.enable_notification
                    }
                )
                response.raise_for_status()
                return True
                
            except Exception as e:
                print(f"Animation send failed (attempt {attempt + 1}): {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(4)
        return False
