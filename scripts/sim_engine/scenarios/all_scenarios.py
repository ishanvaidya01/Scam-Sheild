import random
from scripts.sim_engine.scenarios.base import BaseScenario

def generate_genuine_events(genuine_users, duration_sec, start_time_ms, num_events=50):
    events = []
    prefixes = ["wow", "lmao", "honestly", "guys", "bro", "wait", "ok but", "so", "actually"]
    subjects = ["this stream", "the audio", "that gameplay", "the last match", "his reaction", "the chat", "my internet", "this game"]
    suffixes = ["is crazy", "is so good", "lagging for anyone else?", "needs to be clipped", "is hilarious", "making me sleepy", "W", "L"]
    questions = ["what song is this?", "where is he playing?", "anyone know his rank?", "how long has he been live?", "what's the score?"]
    
    for i in range(num_events):
        user = random.choice(genuine_users)
        if random.random() > 0.3:
            text = f"{random.choice(prefixes)} {random.choice(subjects)} {random.choice(suffixes)}"
        else:
            text = random.choice(questions)
        extra = random.choice(["", ".", "...", "!", " ??", " lol", " 😂", " 💀", f" {i}"])
        text += extra
        
        offset_ms = random.randint(0, duration_sec * 1000)
        events.append({
            "timestamp_ms": start_time_ms + offset_ms,
            "user": user,
            "text": text,
            "ground_truth": "GENUINE"
        })
    return events

class SelfRepeatScenario(BaseScenario):
    """A single bot repeating variations of the same crypto message."""
    def generate_timeline(self, start_time_ms: int):
        self.setup_users()
        events = generate_genuine_events(self.genuine_users, self.duration_sec, start_time_ms, num_events=60)
        
        bot = self.bot_users[0]
        base_msg = "Send 0.1 BTC to my wallet and I'll send 0.5 BTC back immediately! Limited offer"
        for i in range(12):  # Increased from 5 to 12
            offset_ms = random.randint(0, self.duration_sec * 1000)
            events.append({
                "timestamp_ms": start_time_ms + offset_ms,
                "user": bot,
                "text": base_msg + ("!" * i),
                "ground_truth": "BOT"
            })
            
        events.sort(key=lambda x: x["timestamp_ms"])
        for e in events:
            yield {"timestamp_ms": e["timestamp_ms"], "payload": e["user"].generate_comment_payload(e["text"], e["timestamp_ms"]), "ground_truth": e["ground_truth"]}

class CryptoRingScenario(BaseScenario):
    """
    Simulates a coordinated bot ring posting similar crypto scam templates.
    Meanwhile, genuine users post normal chatter.
    """
    def generate_timeline(self, start_time_ms: int):
        self.setup_users()
        events = []
        
        # Build highly diverse genuine messages so they don't accidentally trigger
        # the Coordination Engine's exact-match or semantic similarity thresholds.
        prefixes = ["wow", "lmao", "honestly", "guys", "bro", "wait", "ok but", "so", "actually"]
        subjects = ["this stream", "the audio", "that gameplay", "the last match", "his reaction", "the chat", "my internet", "this game"]
        suffixes = ["is crazy", "is so good", "lagging for anyone else?", "needs to be clipped", "is hilarious", "making me sleepy", "W", "L"]
        questions = ["what song is this?", "where is he playing?", "anyone know his rank?", "how long has he been live?", "what's the score?"]
        
        for i in range(80):
            user = random.choice(self.genuine_users)
            
            # Generate a highly unique message
            if random.random() > 0.3:
                text = f"{random.choice(prefixes)} {random.choice(subjects)} {random.choice(suffixes)}"
            else:
                text = random.choice(questions)
            
            # Add some random punctuation/emojis to ensure uniqueness and prevent 100% exact matches
            extra = random.choice(["", ".", "...", "!", " ??", " lol", " 😂", " 💀", f" {i}"])
            text += extra
            
            offset_ms = random.randint(0, self.duration_sec * 1000)
            events.append({
                "timestamp_ms": start_time_ms + offset_ms,
                "user": user,
                "text": text,
                "ground_truth": "GENUINE"
            })
            
        # Coordinated crypto bots (bursting similar messages)
        base_scam_msgs = [
            "Send 0.1 BTC and receive 0.2 BTC instantly!",
            "Deposit 0.1 BTC to receive 0.2 BTC!",
            "Send Bitcoin and receive double your investment!",
            "Double your BTC now by sending to the pinned address"
        ]
        
        # Bots coordinate a burst roughly halfway through
        burst_start_ms = start_time_ms + (self.duration_sec * 1000 // 2)
        for i in range(25):
            user = random.choice(self.bot_users)
            base = random.choice(base_scam_msgs)
            # Add slight variations to bypass exact-match filters
            variation = "!" * random.randint(0, 3)
            text = f"{base} {variation}".strip()
            
            offset_ms = random.randint(0, 5000) # tight 5-second burst
            events.append({
                "timestamp_ms": burst_start_ms + offset_ms + (i * 200),
                "user": user,
                "text": text,
                "ground_truth": "BOT"
            })
            
        # Sort events chronologically
        events.sort(key=lambda x: x["timestamp_ms"])
        
        for event in events:
            user = event["user"]
            payload = user.generate_comment_payload(event["text"], event["timestamp_ms"])
            yield {
                "timestamp_ms": event["timestamp_ms"],
                "payload": payload,
                "ground_truth": event["ground_truth"]
            }

class ParaphraseAttackScenario(BaseScenario):
    """Coordinated bots posting semantically similar crypto fraud messages."""
    def generate_timeline(self, start_time_ms: int):
        self.setup_users()
        events = generate_genuine_events(self.genuine_users, self.duration_sec, start_time_ms, num_events=80)
        
        paraphrases = [
            "You can make $5000 a week trading crypto, dm me for signals",
            "Message me to learn how to earn huge dollars daily with bitcoin",
            "I'm teaching people to make 5k bucks every 24h using cryptocurrency",
            "Hit my DMs if you want to generate passive income in crypto profits",
            "Want to earn five thousand dollars a day with BTC? Message me",
            "DM for guaranteed 10x crypto returns within a month",
            "I will guide you on how to invest in Ethereum and make massive profit",
            "Text me on whatsapp to get VIP crypto trading signals"
        ]
        burst_start = start_time_ms + random.randint(2000, 5000)
        
        for i in range(24):
            text = random.choice(paraphrases)
            user = self.bot_users[i % len(self.bot_users)]
            events.append({
                "timestamp_ms": burst_start + (i * 1000),
                "user": user,
                "text": text,
                "ground_truth": "BOT"
            })
            
        events.sort(key=lambda x: x["timestamp_ms"])
        for e in events:
            yield {"timestamp_ms": e["timestamp_ms"], "payload": e["user"].generate_comment_payload(e["text"], e["timestamp_ms"]), "ground_truth": e["ground_truth"]}

class BurstAttackScenario(BaseScenario):
    """A sudden high-volume burst of identical crypto giveaway messages."""
    def generate_timeline(self, start_time_ms: int):
        self.setup_users()
        events = generate_genuine_events(self.genuine_users, self.duration_sec, start_time_ms, num_events=80)
        
        burst_start = start_time_ms + 10000
        for i in range(35):
            user = random.choice(self.bot_users)
            events.append({
                "timestamp_ms": burst_start + random.randint(0, 3000),
                "user": user,
                "text": f"MASSIVE ETHEREUM AIRDROP GIVEAWAY - CLICK LINK IN BIO {i}",
                "ground_truth": "BOT"
            })
            
        events.sort(key=lambda x: x["timestamp_ms"])
        for e in events:
            yield {"timestamp_ms": e["timestamp_ms"], "payload": e["user"].generate_comment_payload(e["text"], e["timestamp_ms"]), "ground_truth": e["ground_truth"]}

class BotHubScenario(BaseScenario):
    """A central template distributor with child bots echoing crypto fraud."""
    def generate_timeline(self, start_time_ms: int):
        self.setup_users()
        events = generate_genuine_events(self.genuine_users, self.duration_sec, start_time_ms, num_events=70)
        
        hub_bot = self.bot_users[0]
        child_bots = self.bot_users[1:]
        
        hub_time = start_time_ms + 2000
        for loop in range(3):
            events.append({
                "timestamp_ms": hub_time + (loop * 10000),
                "user": hub_bot,
                "text": "I invested $500 with @CryptoTraderPro and got $5000 back in 2 days! He's a genius.",
                "ground_truth": "BOT"
            })
            
            for i, child in enumerate(child_bots):
                events.append({
                    "timestamp_ms": hub_time + (loop * 10000) + 2000 + (i * 1000),
                    "user": child,
                    "text": f"Yes! @CryptoTraderPro changed my life, highly recommend {i}",
                    "ground_truth": "BOT"
                })
            
        events.sort(key=lambda x: x["timestamp_ms"])
        for e in events:
            yield {"timestamp_ms": e["timestamp_ms"], "payload": e["user"].generate_comment_payload(e["text"], e["timestamp_ms"]), "ground_truth": e["ground_truth"]}

class MixedAttackScenario(BaseScenario):
    """A complex timeline transitioning through multiple crypto attack types with high volume."""
    def generate_timeline(self, start_time_ms: int):
        self.setup_users()
        events = generate_genuine_events(self.genuine_users, self.duration_sec, start_time_ms, num_events=120)
        
        bot1 = self.bot_users[0]
        for i in range(8):
            events.append({"timestamp_ms": start_time_ms + 1000 + i*3000, "user": bot1, "text": "Send 1 SOL to my wallet for 2 SOL back guaranteed!", "ground_truth": "BOT"})
            
        burst_start = start_time_ms + 10000
        for i in range(25):
            events.append({"timestamp_ms": burst_start + i*300, "user": random.choice(self.bot_users[1:4]), "text": "FREE BTC GIVEAWAY CLAIM YOUR REWARD NOW", "ground_truth": "BOT"})
            
        hub_time = start_time_ms + 20000
        events.append({"timestamp_ms": hub_time, "user": self.bot_users[0], "text": "I quit my job after @TraderMax helped me earn 10x profit on crypto.", "ground_truth": "BOT"})
        for i in range(6):
            events.append({"timestamp_ms": hub_time + 1000 + i*1500, "user": random.choice(self.bot_users[1:]), "text": f"@TraderMax is 100% legit, he helped me pay off my debt {i}", "ground_truth": "BOT"})

        events.sort(key=lambda x: x["timestamp_ms"])
        for e in events:
            yield {"timestamp_ms": e["timestamp_ms"], "payload": e["user"].generate_comment_payload(e["text"], e["timestamp_ms"]), "ground_truth": e["ground_truth"]}
