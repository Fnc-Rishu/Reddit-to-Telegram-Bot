# reddit_handler.py

from configparser import ConfigParser
import praw
import requests
import random
from cache import Cache
from input_object import InputObject

HEADER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9",
}

# --------Loading the CONFIG files---------------------------
config = ConfigParser()
config.read("config.ini")

SUBREDDIT_LIST = [s.strip() for s in config["Reddit"]["subreddits"].split(",")]
SEARCH_LIMIT = config["Reddit"]["search_limit"]
SORT = config["Reddit"]["sort_posts"]
FETCH_LATEST = eval(config["Reddit"]["fetch_latest_post"])

CHANNEL_NAME = config["Telegram"]["channel_name"]
CHANNEL_LINK = config["Telegram"]["channel_link"]
INCLUDE_TITLE = eval(config["Telegram"]["include_title"])
LINK_TO_POST = eval(config["Telegram"]["link_to_post"])
SIGN_MESSAGES = eval(config["Telegram"]["sign_messages"])
ONLY_IMAGES = eval(config["Telegram"]["only_images"])

PHOTO_FILE_TYPES = ["jpg", "jpeg", "png", "webp"]
ANIMATION_FILE_TYPES = ["gif", "gifv", "mp4"]

REDDIT_URL = "https://www.reddit.com/r/"
REDDIT_PARAMETER = {"limit": SEARCH_LIMIT}

class RedditHandler:
    """
    Class that handles extracting and filtering of media from Reddit submissions.
    """
    def __init__(self):
        self.retries = 0
        self.current_index = 0
        self.post_json = None
        self.gallery_url_list = None
        
        # Initialize PRAW for streaming
        self.reddit = praw.Reddit(
            client_id=config["Reddit"]["client_id"],
            client_secret=config["Reddit"]["client_secret"],
            user_agent="script:RedditToTelegramBot:v1.0 (by /u/YourUsername)"
        )

    def get_submission_stream(self):
        """
        Get a stream of new submissions from all configured subreddits
        """
        subreddits = "+".join(SUBREDDIT_LIST)
        return self.reddit.subreddit(subreddits).stream.submissions(skip_existing=True)

    def process_submission(self, submission):
        """
        Process a submission from the stream
        """
        try:
            # Skip removed or stickied posts
            if hasattr(submission, 'removed_by_category') and submission.removed_by_category:
                return None
            if submission.stickied:
                return None

            # Set current subreddit and post ID
            self.currrent_subreddit = submission.subreddit.display_name
            self.post_id = submission.id

            # Check for reposts
            if Cache.is_a_repost(self.currrent_subreddit, self.post_id):
                return None

            # Create post_json from submission for compatibility with existing methods
            self.post_json = {
                "id": submission.id,
                "removed_by_category": getattr(submission, 'removed_by_category', None),
                "stickied": submission.stickied,
                "permalink": submission.permalink,
                "title": submission.title,
                "subreddit": submission.subreddit.display_name,
                "link_flair_text": submission.link_flair_text,
                "url_overridden_by_dest": submission.url,
                "is_gallery": hasattr(submission, 'gallery_data'),
                "is_video": submission.is_video,
                "media": submission.media,
                "post_hint": getattr(submission, 'post_hint', None),
                "preview": getattr(submission, 'preview', {})
            }

            if hasattr(submission, 'media_metadata'):
                self.post_json["media_metadata"] = submission.media_metadata

            # Format post title
            post_title = ""
            current_reddit_url = f'www.reddit.com{submission.permalink}'

            if INCLUDE_TITLE:
                post_title += submission.title + "\n"
            if LINK_TO_POST:
                post_title += f'<a href="{current_reddit_url}">r/{submission.subreddit.display_name}</a>\n\n'
            if SIGN_MESSAGES:
                post_title += f'<a href="{CHANNEL_LINK}">-{CHANNEL_NAME}</a>'

            # Check post types
            if not ONLY_IMAGES:
                if self.is_photo_post():
                    return ("photo", submission.url, post_title, submission.link_flair_text)

                elif self.is_gallery_post():
                    gallery_data = self.process_gallery(submission)
                    if gallery_data:
                        return ("gallery", gallery_data[0], gallery_data[1], post_title, submission.link_flair_text)

                elif self.is_animation_post():
                    return ("animation", submission.url, post_title, submission.link_flair_text)

                elif self.is_video_post():
                    if submission.media and 'reddit_video' in submission.media:
                        video_url = submission.media['reddit_video']['fallback_url']
                        video_id = video_url.rsplit("/", 1)[1]
                        video_height = submission.media['reddit_video']['height']
                        return ("video", video_id, video_height, post_title, submission.link_flair_text)

                elif self.is_gfycat_post():
                    if submission.media and 'oembed' in submission.media:
                        preview_url = submission.media['oembed']['thumbnail_url']
                        gfycat_id = preview_url.split("/")[-1].split("-")[-2]
                        return ("gfycat", gfycat_id, post_title, submission.link_flair_text)

            else:  # Photo posts only
                if self.is_photo_post():
                    return ("photo", submission.url, post_title, submission.link_flair_text)

            return None

        except Exception as e:
            print(f"Error processing submission: {e}")
            return None

    def process_gallery(self, submission):
        """Process gallery submissions"""
        try:
            if not hasattr(submission, 'gallery_data') or not hasattr(submission, 'media_metadata'):
                return None

            gallery_photo_list = []
            animation_list = []
            first_run = True

            for item in submission.media_metadata.values():
                if item["status"] == "valid":
                    if item["e"] == "Image":
                        url = item["s"]["u"].replace("amp;", "")
                        media_obj = InputObject(
                            media=url,
                            type="photo",
                            caption=submission.title if first_run else "",
                            subreddit=submission.subreddit.display_name,
                            reddit_url=f'www.reddit.com{submission.permalink}'
                        )
                        gallery_photo_list.append(media_obj.__dict__)
                        first_run = False
                    elif item["e"] == "AnimatedImage":
                        url = item["s"]["gif"]
                        animation_list.append(url)

            return (gallery_photo_list, animation_list)

        except Exception as e:
            print(f"Error processing gallery: {e}")
            return None

    def is_photo_post(self):
        """
        Checks if the extracted post json block represents a photo post.

        Returns:
            bool:
        """
        try:
            override_url = self.post_json["url_overridden_by_dest"]
            return any(override_url.lower().endswith(ext) for ext in PHOTO_FILE_TYPES)
        except:
            return False

    def is_gallery_post(self):
        """
        Checks if the extracted json block represents a gallery post.

        Returns:
            bool:
        """
        try:
            return self.post_json["is_gallery"] and self.post_json["media_metadata"] is not None
        except:
            return False

    def is_animation_post(self):
        """
        Checks if the extracted post json block represents an animation(gif) post.

        Returns:
            bool:
        """
        try:
            override_url = self.post_json["url_overridden_by_dest"]
            return any(override_url.lower().endswith(ext) for ext in ANIMATION_FILE_TYPES)
        except:
            return False

    def is_video_post(self):
        """
        Checks if the extracted json block represents an internal video post.

        Returns:
            bool:
        """
        try:
            return self.post_json["post_hint"] == "hosted:video" and self.post_json["is_video"]
        except:
            return False

    def is_gfycat_post(self):
        """
        Checks if the extracted json block represents an embedded gyfcat post.

        Returns:
            bool:
        """
        try:
            return self.post_json["post_hint"] == "rich:video" and self.post_json["media"]["type"] == "gfycat.com"
        except:
            return False

    def get_reddit_json(self, retry: bool = False):
        """
        Retrieves the entire json containing a list of posts.

        Args:
            retry(bool): True if the method is being called after failing to fetch a post. Default False.

        Returns:
            int: HTTP response code.204 on no new Content Available.
            tuple: A tuple containing the post type, media url or media object, caption, and flair.
        """
        if self.retries > 10:
            return 204

        if retry:
            self.retries += 1
        else:
            self.retries = 0

        # Gets a subreddit from a list of subreddits
        self.currrent_subreddit = random.choice(SUBREDDIT_LIST)

        request_url = REDDIT_URL + self.currrent_subreddit + f"/{SORT}/" + ".json"

        try:
            reddit_response = requests.get(request_url, params=REDDIT_PARAMETER, headers=HEADER)
            reddit_response.raise_for_status()
        except:
            print("too many requests")
            return 429  # Too many requests
        else:
            reddit_response_json = reddit_response.json()

        try:
            self.reddit_json = reddit_response_json["data"]["children"]
            self.reddit_json_length = len(self.reddit_json)
        except:
            if len(SUBREDDIT_LIST) == 1:
                return 204
            else:
                return self.get_reddit_json(retry=True)
        else:
            return self.get_post_json()  # Return the post json

    def get_post_json(self, retry: bool = False):
        """
        Extracts a json element containing the post data from the main json.

        Args:
            retry(bool): True if the method is being called after failing to fetch a post. Default False.

        Returns:
            bool|tuple: A tuple containing the post type, media url or media object, caption, and flair. False on fail
        """
        if FETCH_LATEST:  # Only look for the most recent post in the specified time.
            if not retry:
                self.index = 0
            else:
                self.index += 1
        else:  # Look for a random post from the search limit
            self.index = random.randint(0, self.reddit_json_length - 1)

        while self.current_index == self.index and not FETCH_LATEST:
            self.index = random.randint(0, self.reddit_json_length - 1)
        self.current_index = self.index

        try:
            self.post_json = self.reddit_json[self.index]["data"]
        except IndexError:
            if len(SUBREDDIT_LIST) == 1:  # If single subreddit return
                return 204
            else:
                return self.get_reddit_json(retry=True)

        self.post_id = self.post_json["id"]

        # ----CHECK IF POSTS ARE BEING REPEATED-------------------------------
        if Cache.is_a_repost(subreddit=self.currrent_subreddit, post_id=self.post_id):  # True means posted before.
            if FETCH_LATEST:
                return self.get_post_json(retry=True)
            else:
                return self.get_post_json()
        else:  # PostId has not been posted before
            try:
                is_removed = self.post_json["removed_by_category"]
            except:
                pass
            else:
                if is_removed:  # post has been removed by someone. Filtering out spam.
                    Cache.save_post_id(self.currrent_subreddit, self.post_id)
                    return 404

            try:  # Check if the post is a pinned post
                is_stickied = self.post_json["stickied"]
            except:
                pass
            else:
                if is_stickied:
                    Cache.save_post_id(self.currrent_subreddit, self.post_id)
                    return 404

            current_permalink = self.post_json["permalink"]
            current_reddit_url = f'www.reddit.com{current_permalink}'

            current_title = self.post_json["title"]
            current_subreddit = self.post_json["subreddit"]
            post_flair = self.post_json.get("link_flair_text", "")

            post_title = ""

            # ----------Post Caption and Signature-------------------------------
            if INCLUDE_TITLE:
                post_title = post_title + current_title + "\n"

            if LINK_TO_POST:
                hyperlink = f'<a href="{current_reddit_url}">r/{current_subreddit}</a>\n\n'
                post_title = post_title + hyperlink

            if SIGN_MESSAGES:
                post_signature = f'<a href="{CHANNEL_LINK}">-{CHANNEL_NAME}</a>'
                post_title = post_title + post_signature

            # ------------Checking the type of post fetched--------------------

            if not ONLY_IMAGES:
                # ---------------------Photo Post----------------------
                if self.is_photo_post():
                    current_url = self.post_json["url_overridden_by_dest"]
                    return ("photo", current_url, post_title, post_flair)

                # ------------------------Gallery Post------------------------------
                elif self.is_gallery_post():
                    gallery_photo_list = []
                    animation_list = []
                    first_run = True
                    for link in self.gallery_url_list["photo"]:
                        current_url = link
                        current_type = "photo"

                        reddit_media_group_object = InputObject(media=current_url,
                                                                type=current_type,
                                                                caption=post_title,
                                                                subreddit=current_subreddit,
                                                                reddit_url=current_reddit_url)

                        dict_obj = reddit_media_group_object.__dict__  # Object to dictionary

                        if not first_run:  # Delete caption of all other photos and keep only one.
                            del dict_obj["caption"]
                        first_run = False
                        gallery_photo_list.append(dict_obj)  # save dict to list

                    for link in self.gallery_url_list["animation"]:
                        animation_list.append(link)

                    photo_list = gallery_photo_list  # json this later in the main.py
                    return ("gallery", photo_list, animation_list, post_title, post_flair)

                # ------------------------Animation Post------------------------------
                elif self.is_animation_post():
                    current_type = "animation"
                    current_url = self.post_json["url_overridden_by_dest"]
                    return ("animation", current_url, post_title, post_flair)

                # ------------------------Video Post------------------------------
                elif self.is_video_post():
                    video_url = self.post_json["url_overridden_by_dest"]
                    video_id = video_url.rsplit("/", 1)[1]  # Extracting the id from the url v.reddit.it/video_id
                    video_height = self.post_json["preview"]["images"][0]["source"]["height"]  # height is to be used in the url.
                    return ("video", video_id, video_height, post_title, post_flair)

                # ------------------------Gfycat Post------------------------------
                elif self.is_gfycat_post():
                    preview_url = self.post_json["secure_media"]["oembed"]["thumbnail_url"]
                    after_slash = preview_url.split("/")[-1]
                    after_dash = after_slash.split("-")[-2]
                    gfycat_id = after_dash  # extracting the id
                    return ("gfycat", gfycat_id, post_title, post_flair)

                # ------------------------Unsupported Post------------------------------
                else:
                    return 404

            else:  # Post photo only
                # ---------------------Photo Post----------------------
                if self.is_photo_post():
                    current_url = self.post_json["url_overridden_by_dest"]
                    return ("photo", current_url, post_title, post_flair)
                else:
                    return False
