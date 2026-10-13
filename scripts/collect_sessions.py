"""
scripts/collect_sessions.py

Collects real YouTube live chat streams, past broadcasts, or premieres using chat-downloader.
Adheres strictly to the privacy protocol:
  - Raw un-anonymized data is written only to data/raw_private/ (git-ignored).
  - Saved sessions in data/sessions/ are fully anonymized with salted-hashed author IDs.
  - Normalizes messages to standardized JSONL format.
"""

import os
import sys
import json
import yaml
import hashlib
import argparse
import secrets
from typing import Dict, Any, List

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SESSIONS_CONFIG = os.path.join(ROOT_DIR, "data", "sessions.yaml")
RAW_PRIVATE_DIR = os.path.join(ROOT_DIR, "data", "raw_private")
SESSIONS_OUT_DIR = os.path.join(ROOT_DIR, "data", "sessions")
SALT_FILE = os.path.join(ROOT_DIR, ".salt_secret")


def get_or_create_salt() -> str:
    """Retrieves or generates a persistent salt for hashing author identifiers."""
    if os.path.exists(SALT_FILE):
        with open(SALT_FILE, "r", encoding="utf-8") as f:
            salt = f.read().strip()
            if salt:
                return salt
    salt = secrets.token_hex(32)
    with open(SALT_FILE, "w", encoding="utf-8") as f:
        f.write(salt)
    return salt


def hash_author(author_str: str, salt: str) -> str:
    """Salted SHA-256 hash truncated to 16 hex characters."""
    if not author_str:
        return "anon_" + secrets.token_hex(4)
    return hashlib.sha256((salt + author_str).encode("utf-8")).hexdigest()[:16]


def extract_badges(chat_item: Dict[str, Any]) -> List[str]:
    """Extracts platform role badges: member, moderator, verified."""
    badges = []
    author_info = chat_item.get("author", {}) or {}
    badge_list = author_info.get("badges", []) or []

    for b in badge_list:
        title = (b.get("title") or b.get("label") or "").lower()
        if "member" in title:
            badges.append("member")
        elif "moderator" in title:
            badges.append("moderator")
        elif "verified" in title:
            badges.append("verified")

    # Author flags
    if author_info.get("is_moderator") and "moderator" not in badges:
        badges.append("moderator")
    if author_info.get("is_verified") and "verified" not in badges:
        badges.append("verified")

    return sorted(list(set(badges)))


def process_message_item(item: Dict[str, Any], session_id: str, salt: str) -> Dict[str, Any]:
    """Normalizes a raw chat item into the standardized JSONL schema."""
    msg_id = item.get("message_id") or item.get("id") or secrets.token_hex(8)
    
    # Timestamp conversion (milliseconds)
    ts = item.get("timestamp")
    if isinstance(ts, (int, float)):
        # If timestamp is in microseconds or seconds
        if ts > 1e14:
            ts_ms = int(ts // 1000)
        elif ts < 1e11:
            ts_ms = int(ts * 1000)
        else:
            ts_ms = int(ts)
    else:
        ts_ms = 0

    author_raw = (item.get("author", {}) or {}).get("name") or (item.get("author", {}) or {}).get("id") or "unknown"
    author_hash = hash_author(author_raw, salt)
    text = item.get("message") or ""
    badges = extract_badges(item)

    # Detect reply or mention
    is_reply = bool(item.get("reply_to") or ("@" in text and not text.startswith("http")))

    # Message type
    raw_type = item.get("message_type", "text_message")
    if "paid" in raw_type or "super_chat" in raw_type or "super_sticker" in raw_type:
        msg_type = "superchat"
    elif "membership" in raw_type or "sponsor" in raw_type:
        msg_type = "membership"
    else:
        msg_type = "text"

    return {
        "session_id": session_id,
        "msg_id": str(msg_id),
        "ts_ms": ts_ms,
        "author_hash": author_hash,
        "text": text.strip(),
        "badges": badges,
        "is_reply_or_mention": is_reply,
        "message_type": msg_type,
    }


def collect_session(session_id: str, url: str, group: str, max_messages: int = 1500, salt: str = None):
    """Collects messages from a single stream and saves normalized JSONL."""
    try:
        from chat_downloader import ChatDownloader
    except ImportError:
        print("Error: chat-downloader not installed. Run: pip install chat-downloader")
        sys.exit(1)

    os.makedirs(RAW_PRIVATE_DIR, exist_ok=True)
    os.makedirs(SESSIONS_OUT_DIR, exist_ok=True)

    salt = salt or get_or_create_salt()
    raw_private_file = os.path.join(RAW_PRIVATE_DIR, f"{session_id}_raw.jsonl")
    clean_out_file = os.path.join(SESSIONS_OUT_DIR, f"{session_id}.jsonl")

    print(f"[*] Starting collection for [{group}] {session_id} from {url}...")
    downloader = ChatDownloader()
    
    count = 0
    saved = 0

    try:
        chat = downloader.get_chat(url, max_messages=max_messages)
        with open(raw_private_file, "a", encoding="utf-8") as f_raw, \
             open(clean_out_file, "a", encoding="utf-8") as f_clean:
            for item in chat:
                count += 1
                # Save raw item to private git-ignored folder
                f_raw.write(json.dumps(item, ensure_ascii=False) + "\n")

                # Normalize and anonymize
                normalized = process_message_item(item, session_id, salt)

                # Flag or drop non-text messages (superchats/memberships)
                if normalized["message_type"] not in ("text",):
                    continue

                if not normalized["text"]:
                    continue

                f_clean.write(json.dumps(normalized, ensure_ascii=False) + "\n")
                saved += 1

                if saved >= max_messages:
                    print(f"[*] Reached message limit ({max_messages}) for {session_id}.")
                    break

                if count % 200 == 0:
                    print(f"    Collected {count} raw items, {saved} clean messages...")

        print(f"[+] Completed {session_id}: {saved} valid messages saved to {clean_out_file}")
    except Exception as e:
        print(f"[-] Error collecting {session_id}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Collect live chat sessions using chat-downloader")
    parser.add_argument("--config", type=str, default=SESSIONS_CONFIG, help="Path to sessions.yaml")
    parser.add_argument("--group", type=str, choices=["scam_waves", "organic_hype", "quiet", "all"], default="all")
    parser.add_argument("--session-id", type=str, help="Specific session ID to collect")
    parser.add_argument("--limit", type=int, default=1500, help="Max messages per session")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"Error: Config not found at {args.config}")
        sys.exit(1)

    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    salt = get_or_create_salt()

    groups_to_run = ["scam_waves", "organic_hype", "quiet"] if args.group == "all" else [args.group]

    for grp in groups_to_run:
        entries = config.get(grp, [])
        for entry in entries:
            sid = entry.get("id")
            url = entry.get("url")
            if args.session_id and sid != args.session_id:
                continue
            if "REPLACE_WITH" in url:
                print(f"[!] Skipping placeholder {sid}: {url}")
                continue
            collect_session(sid, url, grp, max_messages=args.limit, salt=salt)


if __name__ == "__main__":
    main()
