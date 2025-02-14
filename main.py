import json
import time
import re
from configparser import ConfigParser
from telegram_handler import TelegramHandler
from reddit_handler import RedditHandler
from cache import Cache
from datetime import datetime, timezone

# ------Loading Data from the Config File----------
config = ConfigParser()
config.read("config.ini")

chat_id = config["Telegram"]["chat_id"]

def create_flair_pattern(flair_text):
    """Creates a pattern that matches flair text with or without emoji prefix"""
    escaped = re.escape(flair_text.strip())
    return re.compile(rf"(?::[a-z]+:\s*)?{escaped}$", re.IGNORECASE)

# Convert desired flairs to regex patterns
desired_flairs = [create_flair_pattern(flair) 
                 for flair in config["Main"]["desired_flairs"].split(",")]

tg = TelegramHandler(chat_id=chat_id)
reddit = RedditHandler()
cache = Cache()

def format_post_title(original_title, media_count=None, user_login=None):
    """Format the post title with metadata including timestamp and user info"""
    utc_now = datetime.now(timezone.utc)
    formatted_time = utc_now.strftime("%Y-%m-%d %H:%M:%S")
    
    title_parts = [original_title]
    
    if media_count and media_count > 1:
        title_parts.append(f"\n\n{media_count} images in this post")
    
    # Add timestamp and user info
    title_parts.append(f"\nCurrent Date and Time (UTC - YYYY-MM-DD HH:MM:SS formatted): {formatted_time}")
    if user_login:
        title_parts.append(f"Current User's Login: {user_login}")
    
    return "\n".join(title_parts)

def matches_desired_flair(post_flair):
    """Check if the post flair matches any of the desired flairs using regex"""
    if not post_flair:
        return False
    
    post_flair = post_flair.strip()
    flair_text = post_flair.split(":", 2)[-1].strip() if ":" in post_flair else post_flair
    
    print(f"Processing flair: '{post_flair}' (cleaned text: '{flair_text}')")
    
    for pattern in desired_flairs:
        if pattern.search(post_flair):
            desired_flair_texts = [f.strip() for f in config["Main"]["desired_flairs"].split(",")]
            if any(flair_text.lower() == desired.lower() for desired in desired_flair_texts):
                print(f"Matched flair '{post_flair}' with pattern '{pattern.pattern}'")
                return True
            else:
                print(f"Flair text '{flair_text}' not in desired flairs list despite pattern match")
                return False
    
    print(f"Post skipped due to flair '{post_flair}' not matching any desired flairs.")
    return False

def process_submission(submission):
    """Process a single Reddit submission with support for multiple media"""
    try:
        if Cache.is_a_repost(submission.subreddit.display_name, submission.id):
            return None

        post_flair = submission.link_flair_text.strip() if submission.link_flair_text else ""
        
        if not matches_desired_flair(post_flair):
            return None

        reddit_post = reddit.process_submission(submission)
        
        if not reddit_post:
            return None

        if isinstance(reddit_post, tuple):
            post_type = reddit_post[0]
            
            Cache.save_post_id(submission.subreddit.display_name, submission.id)
            
            max_retries = 3
            retry_delay = 5
            user_login = submission.author.name if submission.author else "Unknown"

            if post_type == "gallery":
                gallery_items = []
                
                if hasattr(submission, 'gallery_data') and hasattr(submission, 'media_metadata'):
                    for item_id in submission.gallery_data['items']:
                        metadata = submission.media_metadata[item_id['media_id']]
                        if metadata['status'] == 'valid':
                            if metadata['e'] == 'Image':
                                url = metadata['s']['u']
                                gallery_items.append(('photo', url))
                            elif metadata['e'] == 'AnimatedImage':
                                url = metadata['s']['gif']
                                gallery_items.append(('animation', url))

                if gallery_items:
                    first_item = gallery_items[0]
                    post_title = format_post_title(submission.title, len(gallery_items), user_login)
                    
                    if first_item[0] == 'photo':
                        success = tg.send_photo(first_item[1], post_title)
                    else:
                        success = tg.send_animation(first_item[1], post_title)

                    if not success:
                        print(f"Failed to send first item of gallery")
                        return False

                    for item_type, url in gallery_items[1:]:
                        for attempt in range(max_retries):
                            try:
                                if item_type == 'photo':
                                    success = tg.send_photo(url, "")
                                else:
                                    success = tg.send_animation(url, "")
                                
                                if success:
                                    break
                                else:
                                    raise Exception("Failed to send media")
                                
                            except Exception as e:
                                if attempt < max_retries - 1:
                                    print(f"Attempt {attempt + 1} failed: {e}")
                                    time.sleep(retry_delay)
                                    retry_delay *= 2
                                else:
                                    print(f"Failed to send gallery item after {max_retries} attempts")
                                    return False
                            
                            # Add small delay between sends to prevent rate limiting
                            time.sleep(1)

                    print(f"Successfully forwarded gallery post with {len(gallery_items)} items")
                    return True

            elif post_type == "photo":
                post_url = reddit_post[1]
                post_title = format_post_title(reddit_post[2], user_login=user_login)
                return tg.send_photo(post_url, post_title)

            elif post_type == "animation":
                post_url = reddit_post[1]
                post_title = format_post_title(reddit_post[2], user_login=user_login)
                return tg.send_animation(animation_url=post_url, title=post_title)

            elif post_type == "video":
                video_id = reddit_post[1]
                video_resolution = reddit_post[2]
                post_title = format_post_title(reddit_post[3], user_login=user_login)
                return tg.send_video(video_id=video_id, video_resolution=video_resolution, title=post_title)

            elif post_type == "gfycat":
                post_url = reddit_post[1]
                post_title = format_post_title(reddit_post[2], user_login=user_login)
                return tg.send_gfycat(post_url, post_title)

    except Exception as e:
        print(f"Error processing submission: {e}")
        return None

def stream_subreddits():
    """Stream new posts from configured subreddits"""
    subreddits = [s.strip() for s in config["Reddit"]["subreddits"].split(",")]
    multi_subreddit = "+".join(subreddits)
    
    print(f"Starting to stream posts from: {multi_subreddit}")
    print(f"Watching for posts with these flairs: {[pattern.pattern[1:-1] for pattern in desired_flairs]}")
    
    while True:
        try:
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
