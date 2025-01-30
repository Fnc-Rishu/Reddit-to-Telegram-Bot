import json
import time
import re
from configparser import ConfigParser

from telegram_handler import TelegramHandler
from reddit_handler import RedditHandler
from cache import Cache

# ------Loading Data from the Config File----------

config = ConfigParser()  # Loading the config file
config.read("config.ini")

chat_id = config["Telegram"]["chat_id"]
#----------------------------------------------------
is_single_run = eval(config["Main"]["is_single_run"])
instant_send = eval(config["Main"]["instant_send"])

# Compile regex patterns for desired flairs
desired_flairs = [re.compile(flair.strip(), re.IGNORECASE) for flair in config["Main"]["desired_flairs"].split(",")]

tg = TelegramHandler(chat_id=chat_id)
reddit = RedditHandler()
cache = Cache()

# Track the latest post ID to avoid redundant checks
latest_post_id = None

# -----------------------------------------------------
def reddit_int():
    """
    Function that uses the 'RedditHandler' to fetch post and converts the fetched post into a telegram message and post using TelegramHandler.

    Returns:
        int: HTTP status code. (204 if no new content is available to fetch)
    """
    global latest_post_id

    reddit_post = reddit.get_reddit_json()  # Fetching the reddit post
    print(f"Fetched post: {reddit_post}")  # Debugging information

    if reddit_post:
        if isinstance(reddit_post, int):  # if an error code is returned.
            return reddit_post

        elif isinstance(reddit_post, tuple):  # tuple means a post has been fetched.
            post_type = reddit_post[0]
            post_url = reddit_post[1]
            post_title = reddit_post[2]
            post_flair = reddit_post[3].strip() if len(reddit_post) > 3 else ""  # Extract flair and strip whitespace
            post_id = reddit.post_id  # Get the post ID

            # Check if the post is the same as the latest post
            if post_id == latest_post_id:
                return 204  # No new post, skip further processing

            # Update the latest post ID
            latest_post_id = post_id

            # Check if post flair matches any of the desired flair patterns
            if not any(flair.match(post_flair) for flair in desired_flairs):
                print(f"Post skipped due to flair '{post_flair}' not in desired flairs.")
                return 204  # Skip the post if it doesn't have the desired flair

            # Check if post is already cached
            if Cache.is_a_repost(reddit.currrent_subreddit, post_id):
                print(f"Post '{post_title}' already cached. Skipping.")
                return 204  # Skip if post is already cached

            Cache.save_post_id(reddit.currrent_subreddit, post_id)

            if post_type == "photo":
                photo_status = tg.send_photo(post_url, post_title)
                if not photo_status:
                    return 404

            elif post_type == "gallery":
                gallery_photo_posts = reddit_post[1]
                gallery_animation_posts = reddit_post[2]

                gallery_photo_post_len = len(gallery_photo_posts)
                gallery_animation_post_len = len(gallery_animation_posts)

                gallery_json_obj = json.dumps(gallery_photo_posts)

                if gallery_photo_post_len == 0:  # If gallery has only GIFs
                    for animation_url in gallery_animation_posts:
                        if gallery_animation_posts.index(animation_url) == gallery_animation_post_len - 1:  # for only the last Gif to have caption.
                            gallery_status = tg.send_animation(animation_url=animation_url, title=post_title)
                        else:
                            gallery_status = tg.send_animation(animation_url=animation_url, title="")

                elif gallery_animation_post_len == 0:
                    gallery_status = tg.send_media_group(gallery_json_obj)

                else:  # Gallery has both Gif and photo, so Gifs first, followed by photos(with caption)
                    for animation_url in gallery_animation_posts:
                        gallery_status = tg.send_animation(animation_url)
                    gallery_status = tg.send_media_group(gallery_json_obj)

                if not gallery_status:
                    return 404

            elif post_type == "animation":
                animation_status = tg.send_animation(animation_url=post_url, title=post_title)
                if not animation_status:
                    return 404

            elif post_type == "video":
                video_id = reddit_post[1]
                video_resolution = reddit_post[2]
                video_status = tg.send_video(video_id=video_id, video_resolution=video_resolution, title=post_title)
                if not video_status:
                    return 404

            elif post_type == "gfycat":
                gfycat_status = tg.send_gfycat(post_url, post_title)
                if not gfycat_status:
                    return 404

            else:
                return 404

    else:  # just in case
        Cache.save_post_id(reddit.currrent_subreddit, reddit.post_id)
        return 404


def main():
    "main function"

    while True:  # Continuously run until manually stopped or a single run is configured
        post_status = reddit_int()
        if post_status == 429:  # If too many requests wait a while.
            print("Too many requests. Sleeping for 2 minutes.")
            time.sleep(120)  # Wait for 2 minutes before retrying

        elif post_status == 404:  # Failed to fetch post or send message. Instantly get a new post.
            Cache.save_post_id(reddit.currrent_subreddit, reddit.post_id)

        elif post_status == 204:  # No new Content Available.
            pass  # No new content, wait for next post
        else:
            print("Message Sent.")
            if is_single_run:
                break

        if not instant_send:
            time.sleep(1)  # Short sleep to avoid too frequent requests


if __name__ == "__main__":
    main()
