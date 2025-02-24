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

# Initialize global handlers
chat_id = config["Telegram"]["chat_id"]
tg = TelegramHandler(chat_id=chat_id)
reddit = RedditHandler()  # Added this line
cache = Cache()

def create_flair_pattern(flair_text):
    """Creates a pattern that matches flair text with or without emoji prefix"""
    # Remove any existing emoji prefix if present
    cleaned_text = flair_text.split(":", 2)[-1].strip() if ":" in flair_text else flair_text.strip()
    # Escape special characters but preserve spaces
    escaped = " ".join(re.escape(part) for part in cleaned_text.split())
    return re.compile(rf"(?::[a-z]+:\s*)?{escaped}$", re.IGNORECASE)

# Convert desired flairs to regex patterns
desired_flairs = [create_flair_pattern(flair.strip()) 
                 for flair in config["Main"]["desired_flairs"].split(",")]

def matches_desired_flair(post_flair):
    """Check if the post flair matches any of the desired flairs"""
    if not post_flair:
        return False
    
    # Clean the post flair text
    cleaned_flair = post_flair.split(":", 2)[-1].strip() if ":" in post_flair else post_flair.strip()
    print(f"Processing flair: '{post_flair}' (cleaned text: '{cleaned_flair}')")
    
    # Check against each pattern
    for pattern in desired_flairs:
        if pattern.search(post_flair):
            print(f"Matched flair '{post_flair}' with pattern '{pattern.pattern}'")
            # Verify the cleaned text matches exactly (case-insensitive)
            desired_flair_texts = [f.strip().split(":", 2)[-1].strip() 
                                 for f in config["Main"]["desired_flairs"].split(",")]
            if any(cleaned_flair.lower() == desired.lower() for desired in desired_flair_texts):
                return True
    
    print(f"Post skipped due to flair '{post_flair}' not matching any desired flairs.")
    return False

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

def collect_media_items(submission):
    """Collect all media items from a submission"""
    media_items = []
    
    try:
        if hasattr(submission, 'gallery_data') and hasattr(submission, 'media_metadata'):
            for item in submission.gallery_data['items']:
                media_id = item['media_id']
                if media_id in submission.media_metadata:
                    metadata = submission.media_metadata[media_id]
                    if metadata['status'] == 'valid':
                        if metadata['e'] == 'Image':
                            url = metadata['s']['u'].replace("amp;", "")
                            media_items.append(('photo', url))
                        elif metadata['e'] == 'AnimatedImage':
                            url = metadata['s']['gif'].replace("amp;", "")
                            media_items.append(('animation', url))
        elif submission.url.lower().split('.')[-1] in ['jpg', 'jpeg', 'png', 'webp']:
            media_items.append(('photo', submission.url))
        elif submission.url.lower().split('.')[-1] in ['gif', 'gifv', 'mp4']:
            media_items.append(('animation', submission.url))
        elif hasattr(submission, 'is_video') and submission.is_video:
            if submission.media and 'reddit_video' in submission.media:
                url = submission.media['reddit_video']['fallback_url']
                media_items.append(('video', url))
    except Exception as e:
        print(f"Error collecting media items: {e}")
    
    return media_items

def process_submission(submission):
    """Process a single Reddit submission with support for multiple media"""
    try:
        if Cache.is_a_repost(submission.subreddit.display_name, submission.id):
            return None

        post_flair = submission.link_flair_text.strip() if submission.link_flair_text else ""
        
        if not matches_desired_flair(post_flair):
            return None

        # Collect all media items first
        media_items = collect_media_items(submission)
        if not media_items:
            return None

        Cache.save_post_id(submission.subreddit.display_name, submission.id)
        
        # Just use the plain title without any additional formatting
        caption = submission.title
        
        # Only add subreddit link and channel signature if configured
        if config.getboolean("Telegram", "link_to_post", fallback=True):
            caption += f'\n<a href="https://www.reddit.com{submission.permalink}">r/{submission.subreddit.display_name}</a>'
        if config.getboolean("Telegram", "sign_messages", fallback=True):
            caption += f'\n<a href="{config["Telegram"]["channel_link"]}">-{config["Telegram"]["channel_name"]}</a>'

        # Send all media items
        success = send_media_items(media_items, caption)
        
        if success:
            print(f"Successfully forwarded post with {len(media_items)} media items")
            return True
        else:
            print("Failed to forward post")
            return False

    except Exception as e:
        print(f"Error processing submission: {e}")
        return None

def send_media_items(media_items, caption):
    """Send all media items with proper error handling"""
    try:
        # Send first item with just the title as caption
        first_item = media_items[0]
        success = False
        
        if first_item[0] == 'photo':
            success = tg.send_photo(first_item[1], caption)
        elif first_item[0] == 'animation':
            success = tg.send_animation(first_item[1], caption)
        elif first_item[0] == 'video':
            success = tg.send_video(first_item[1], caption)
            
        if not success:
            return False

        # Send remaining items without any caption
        for media_type, url in media_items[1:]:
            max_retries = 3
            retry_delay = 5
            
            for attempt in range(max_retries):
                try:
                    success = False
                    if media_type == 'photo':
                        success = tg.send_photo(url, "")
                    elif media_type == 'animation':
                        success = tg.send_animation(url, "")
                    elif media_type == 'video':
                        success = tg.send_video(url, "")
                        
                    if success:
                        break
                        
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(f"Attempt {attempt + 1} failed: {e}")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        print(f"Failed to send media item after {max_retries} attempts")
                        return False
                
                time.sleep(1)  # Rate limiting delay
                
        return True
        
    except Exception as e:
        print(f"Error sending media items: {e}")
        return False

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
