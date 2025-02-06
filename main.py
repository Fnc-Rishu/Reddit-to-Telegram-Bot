import json
import time
import re
from configparser import ConfigParser
from telegram_handler import TelegramHandler
from reddit_handler import RedditHandler
from cache import Cache

# --------Loading the CONFIG files---------------------------
config = ConfigParser()
config.read("config.ini")

chat_id = config["Telegram"]["chat_id"]

def create_flair_pattern(flair_text):
    """Creates a pattern that matches flair text with or without emoji prefix"""
    escaped = re.escape(flair_text.strip())
    # Match optional emoji prefix and the flair text
    return re.compile(rf"(?::[a-z]+:\s*)?{escaped}", re.IGNORECASE)

# Convert desired flairs to regex patterns
desired_flairs = [create_flair_pattern(flair) 
                 for flair in config["Main"]["desired_flairs"].split(",")]

tg = TelegramHandler(chat_id=chat_id)
reddit = RedditHandler()
cache = Cache()

def matches_desired_flair(post_flair):
    """
    Check if the post flair matches any of the desired flairs using regex
    """
    if not post_flair:
        return False
    
    # Search for pattern anywhere in the flair text
    post_flair = post_flair.strip()
    matched_pattern = None
    for pattern in desired_flairs:
        if pattern.search(post_flair):
            print(f"Matched flair '{post_flair}' with pattern '{pattern.pattern}'")
            matched_pattern = pattern
            break
    
    if matched_pattern:
        return True
    else:
        print(f"Post skipped due to flair '{post_flair}' not matching any desired flairs.")
        return False

def process_submission(submission):
    """
    Process a single Reddit submission
    """
    try:
        # Skip if post is already in cache
        if Cache.is_a_repost(submission.subreddit.display_name, submission.id):
            return None

        # Get post flair
        post_flair = submission.link_flair_text.strip() if submission.link_flair_text else ""
        
        # Skip if flair doesn't match desired flairs
        if not matches_desired_flair(post_flair):
            return None

        # Convert submission to post data
        reddit_post = reddit.process_submission(submission)
        
        if not reddit_post:
            return None

        if isinstance(reddit_post, tuple):
            post_type = reddit_post[0]
            post_url = reddit_post[1]
            post_title = reddit_post[2]

            # Save to cache before processing
            Cache.save_post_id(submission.subreddit.display_name, submission.id)

            # Process different post types
            if post_type == "photo":
                photo_status = tg.send_photo(post_url, post_title)
                if photo_status:
                    print(f"Successfully forwarded photo post with flair '{post_flair}'")
                return photo_status

            elif post_type == "gallery":
                gallery_photo_posts = reddit_post[1]
                gallery_animation_posts = reddit_post[2]

                gallery_photo_post_len = len(gallery_photo_posts)
                gallery_animation_post_len = len(gallery_animation_posts)

                gallery_json_obj = json.dumps(gallery_photo_posts)
                gallery_status = False

                if gallery_photo_post_len == 0:  # If gallery has only GIFs
                    for animation_url in gallery_animation_posts:
                        if gallery_animation_posts.index(animation_url) == gallery_animation_post_len - 1:
                            gallery_status = tg.send_animation(animation_url=animation_url, title=post_title)
                        else:
                            gallery_status = tg.send_animation(animation_url=animation_url, title="")

                elif gallery_animation_post_len == 0:
                    gallery_status = tg.send_media_group(gallery_json_obj)

                else:  # Gallery has both GIFs and photos
                    for animation_url in gallery_animation_posts:
                        gallery_status = tg.send_animation(animation_url)
                    gallery_status = tg.send_media_group(gallery_json_obj)

                if gallery_status:
                    print(f"Successfully forwarded gallery post with flair '{post_flair}'")
                return gallery_status

            elif post_type == "animation":
                animation_status = tg.send_animation(animation_url=post_url, title=post_title)
                if animation_status:
                    print(f"Successfully forwarded animation post with flair '{post_flair}'")
                return animation_status

            elif post_type == "video":
                video_id = reddit_post[1]
                video_resolution = reddit_post[2]
                video_status = tg.send_video(video_id=video_id, video_resolution=video_resolution, title=post_title)
                if video_status:
                    print(f"Successfully forwarded video post with flair '{post_flair}'")
                return video_status

            elif post_type == "gfycat":
                gfycat_status = tg.send_gfycat(post_url, post_title)
                if gfycat_status:
                    print(f"Successfully forwarded gfycat post with flair '{post_flair}'")
                return gfycat_status

    except Exception as e:
        print(f"Error processing submission: {e}")
        return None

def stream_subreddits():
    """
    Stream new posts from configured subreddits
    """
    subreddits = [s.strip() for s in config["Reddit"]["subreddits"].split(",")]
    multi_subreddit = "+".join(subreddits)
    
    print(f"Starting to stream posts from: {multi_subreddit}")
    print(f"Watching for posts with these flairs: {[pattern.pattern for pattern in desired_flairs]}")
    
    while True:
        try:
            # Get the subreddit stream
            for submission in reddit.get_submission_stream():
                process_submission(submission)
        except Exception as e:
            print(f"Stream interrupted: {e}")
            print("Restarting stream in 30 seconds...")
            time.sleep(30)

def main():
    """Main function using streaming approach"""
    stream_subreddits()

if __name__ == "__main__":
    main()
