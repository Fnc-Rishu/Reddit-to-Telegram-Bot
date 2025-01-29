import json
import time
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
interval = int(config["Main"]["interval"])  # delay after each posting in seconds
total_messages = int(config["Main"]["total_messages"])  # Total messages to send before script exits.

desired_flairs = [flair.strip() for flair in config["Main"]["desired_flairs"].split(",")]

running = True
rep = 0

tg = TelegramHandler(chat_id=chat_id)
reddit = RedditHandler()
cache = Cache()

# -----------------------------------------------------
def reddit_int():
    """
    Function that uses the 'RedditHandler' to Fetch post and converts the fetched post into a telegram message and post using TelegramHandler.

    Returns:
        int: HTTP status code. (204 if no new content is available to fetch)
    """
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

            if post_flair not in desired_flairs:
                print(f"Post skipped due to flair '{post_flair}' not in desired flairs.")
                return 204  # Skip the post if it doesn't have the desired flair

            Cache.save_post_id(reddit.currrent_subreddit, reddit.post_id)

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
    rep = 0

    while rep < total_messages:  # If configured to run in a loop. exit after a total of 10 messages
        delay = interval

        post_status = reddit_int()
        if post_status == 429:  # If too many requests wait a while.
            delay = int(.2 * 60)  # Convert to seconds

        elif post_status == 404:  # Failed to fetch post or send message. Instantly get a new post.
            Cache.save_post_id(reddit.currrent_subreddit, reddit.post_id)
            delay = 0

        elif post_status == 204:  # No new Content Available.
            print("no new content")
            if is_single_run:
                break
        else:
            print("Message Sent.")
            if is_single_run:
                break
            else:
                rep += 1

        time.sleep(delay)


if __name__ == "__main__":
    main()
