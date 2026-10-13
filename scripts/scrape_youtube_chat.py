import os
import sys
import time
import csv
import uuid
from playwright.sync_api import sync_playwright

def scrape_live_chat(video_id, duration_seconds=7200):
    url = f"https://www.youtube.com/live_chat?is_popout=1&v={video_id}"
    out_dir = os.path.join("data", "raw")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"scraped_chat_{video_id}.csv")
    
    file_exists = os.path.isfile(out_file)
    
    print(f"Connecting to live chat for {video_id}...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = context.new_page()
        page.goto(url)
        
        print("Waiting for chat to load...")
        try:
            page.wait_for_selector('yt-live-chat-text-message-renderer', timeout=15000)
            print("Chat loaded. Starting scrape...")
        except Exception as e:
            print("Could not find chat messages. Is the stream live and does it have chat enabled?")
            browser.close()
            return
            
        with open(out_file, 'a', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['comment_id', 'text', 'username', 'timestamp']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            if not file_exists:
                writer.writeheader()
                
            seen_ids = set()
            start_time = time.time()
            
            try:
                while time.time() - start_time < duration_seconds:
                    messages = page.locator('yt-live-chat-text-message-renderer').all()
                    
                    for msg in messages:
                        try:
                            # YouTube uses the element ID attribute for the chat ID
                            msg_id = msg.get_attribute('id')
                            if not msg_id or msg_id in seen_ids:
                                continue
                                
                            author = msg.locator('#author-name').inner_text().strip()
                            text = msg.locator('#message').inner_text().strip()
                            # If there is no text (e.g. only custom emoji), skip or store raw HTML
                            if not text:
                                continue
                                
                            # Convert current time to JS timestamp (unix ms) 
                            # YouTube's displayed timestamp doesn't include date, so current time is better for our realtime dataset
                            timestamp_ms = int(time.time() * 1000)
                            
                            writer.writerow({
                                'comment_id': msg_id,
                                'text': text,
                                'username': author,
                                'timestamp': timestamp_ms
                            })
                            seen_ids.add(msg_id)
                            csvfile.flush()
                            
                        except Exception as inner_e:
                            pass # Element might have been detached from DOM
                            
                    time.sleep(1) # Poll every second
                    
            except KeyboardInterrupt:
                print("Scraping manually interrupted.")
                
        print(f"Finished scraping. Saved to {out_file}")
        browser.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scrape_youtube_chat.py <youtube_video_id> [duration_seconds]")
        sys.exit(1)
        
    vid = sys.argv[1]
    dur = int(sys.argv[2]) if len(sys.argv) > 2 else 7200
    scrape_live_chat(vid, dur)
