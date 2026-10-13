import random
import uuid

# Common realistic-looking username components
FIRST_NAMES = ["Alex", "Rahul", "Priya", "Arjun", "Tech", "Crypto", "Music", "Gaming", "Sam", "David", "Neha", "Vikas"]
LAST_NAMES = ["Live", "Fan", "World", "King", "Lover", "Pro", "Gamer", "Max", "Boy", "Girl"]

def generate_realistic_username(is_bot=False):
    """
    Generates a realistic username. 
    We don't use 'bot123' because that's an unrealistic signal.
    """
    first = random.choice(FIRST_NAMES)
    
    # 50% chance to have a 'last name' string
    if random.random() > 0.5:
        last = random.choice(LAST_NAMES)
    else:
        last = ""
        
    # 80% chance to have some numbers
    if random.random() > 0.2:
        # Bots might have slightly more numbers on average, but it should still look human-ish
        if is_bot and random.random() > 0.5:
            num = str(random.randint(1000, 99999))
        else:
            num = str(random.randint(10, 9999))
    else:
        num = ""
        
    # Maybe add an underscore
    separator = "_" if random.random() > 0.7 else ""
    
    parts = [first, last]
    parts = [p for p in parts if p]
    base = "".join(parts)
    
    if num:
        return f"{base}{separator}{num}"
    return base

class SimulatedUser:
    def __init__(self, is_bot: bool):
        self.user_id = str(uuid.uuid4())
        self.username = generate_realistic_username(is_bot)
        self.is_bot = is_bot
        # State tracking for the user
        self.message_count = 0
        
    def generate_comment_payload(self, text: str, timestamp_ms: int) -> dict:
        """
        Creates the payload expected by the FastAPI backend.
        Ground truth is NOT included in this payload to prevent the ML from seeing it.
        """
        self.message_count += 1
        return {
            "comment_id": str(uuid.uuid4()),
            "text": text,
            "username": self.username,
            "timestamp": timestamp_ms
        }
