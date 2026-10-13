"""
ml/session_state.py

Defines the SessionState dataclass that encapsulates all per-WebSocket-connection
state for the Scam Shield engine.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time


@dataclass
class UserProfile:
    """
    Tracks in-session behavioral data for a single username/author hash.
    Built incrementally as messages arrive.
    """
    username: str
    message_timestamps: List[int] = field(default_factory=list)  # unix ms
    message_texts: List[str] = field(default_factory=list)
    total_messages: int = 0
    flagged_count: int = 0
    first_message_ts: Optional[int] = None

    def record_message(self, text: str, timestamp: int):
        self.message_timestamps.append(timestamp)
        self.message_texts.append(text)
        self.total_messages += 1
        if self.first_message_ts is None:
            self.first_message_ts = timestamp

    def get_velocity(self, window_seconds: int = 60) -> int:
        """Returns number of messages sent in the last `window_seconds`."""
        cutoff = (int(time.time() * 1000)) - (window_seconds * 1000)
        return sum(1 for ts in self.message_timestamps if ts >= cutoff)

    def get_type_token_ratio(self) -> float:
        """
        Type-Token Ratio (TTR): unique_words / total_words.
        Low TTR across a user's messages indicates template recycling.
        """
        if len(self.message_texts) < 3:
            return 1.0
        all_tokens = []
        for text in self.message_texts:
            tokens = text.lower().split()
            all_tokens.extend(tokens)
        if not all_tokens:
            return 1.0
        return len(set(all_tokens)) / len(all_tokens)

    def is_first_message(self) -> bool:
        return self.total_messages == 1


@dataclass
class SessionState:
    """
    Complete state for one WebSocket connection (one live stream session).
    """
    # Rolling time-window of recent comments
    rolling_window: List[dict] = field(default_factory=list)

    # Per-username behavioral profiles
    user_profiles: Dict[str, UserProfile] = field(default_factory=dict)

    # Session-level counters for dashboard
    total_scanned: int = 0
    total_flagged: int = 0
    total_scam: int = 0

    # Session start time (unix ms)
    started_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def get_or_create_profile(self, username: str) -> UserProfile:
        if username not in self.user_profiles:
            self.user_profiles[username] = UserProfile(username=username)
        return self.user_profiles[username]
