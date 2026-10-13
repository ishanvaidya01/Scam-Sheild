"""
attacks/attack_generator.py

Adversarial Red-Team Campaign Generator.
Implements the 5-tier Stealth Ladder + L3-single:
  - L0: Copy-paste burst (identical text across bots)
  - L1: Template variable substitution (handles, amounts, links)
  - L2: LLM paraphrase of scam intent (unique sentences per bot)
  - L3: Context-aware LLM comments with chat-reaction, typos, slang, jittered timing
  - L4: Low-and-slow (many accounts, 1-2 messages each over 10+ minutes)
  - L3-single: 1 stealth account, 1 message (documented limit -> unverifiable)

Caches every generated message on disk (attacks/cache/) for 100% reproducibility.
"""

import os
import sys
import json
import random
import hashlib
from typing import List, Dict, Any, Optional

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CACHE_DIR = os.path.join(ROOT_DIR, "attacks", "cache")
PROMPTS_DIR = os.path.join(ROOT_DIR, "attacks", "prompts")


# ── Built-in Seed Templates for L0 and L1 ─────────────────────────────────────

L0_SEED_MESSAGES = [
    "🔥 SPECIAL GIVEAWAY: Send 0.1 BTC to receive 0.5 BTC back instantly! Check t.me/official_bonus_event",
    "Join the official investment portal today and double your ETH: https://t.me/eth_airdrop_live",
    "Customer support alert: If you lost access to your funds, contact @CryptoHelpDesk on Telegram now!",
    "Massive token launch happening now! Claim your 5,000 free tokens at https://cutt.ly/claim-bonus",
]

L1_TEMPLATES = [
    "Deposit {amount} {coin} and receive {double_amount} {coin} in your wallet! Telegram: @{handle}",
    "Special {coin} promo for this stream: send {amount} to claim bonus via {link}",
    "Reach out to @{handle} on Telegram for assistance with {coin} investment returns",
    "Only {slots} slots left! Send {amount} {coin} to qualify: {link}",
]

COINS = ["BTC", "ETH", "SOL", "USDT"]
HANDLES = ["AlexSupport", "OfficialBonus", "TradeDesk_VIP", "CryptoSupport_Live", "SarahHelper", "CoinAdmin_Pro"]
LINKS = ["t.me/crypto_rewards_2026", "wa.me/447911123456", "cutt.ly/bonus-drop", "linktr.ee/official_prizes"]

# ── High-Quality Pre-Generated LLM Fallbacks (Offline Cache) ─────────────────
# Used when no API key is provided or for completely offline evaluation
L2_SEED_PARAPHRASES = [
    "Anyone else participated in that ether bonus round? Just got 0.4 eth back in my metamask",
    "Just sharing that the telegram promo is actually legit, they doubled my solana in 10 mins",
    "Check out the rewards program on telegram @OfficialBonus, paid out immediately",
    "Sent 0.05 bitcoin to the verified event address and received the bonus transaction right away",
    "You guys should look into the pinned giveaway link, got my deposit matched instantly",
    "Can confirm the airdrop portal works, received 250 usdt directly to my trust wallet",
    "If you want to double your tokens before the round closes check the telegram support desk",
    "Quick heads up that the promotional bonus is still running at cutt.ly/bonus-drop",
    "Legit surprise: transferred 0.1 eth and got the doubled reward back within 5 minutes",
    "Whoever mentioned that telegram channel earlier thanks so much, the payout just arrived",
    "Don't miss the current distribution pool, verified returns on all deposits today",
    "The bonus allocation is filling up fast, message @TradeDesk_VIP to claim before it ends",
]

L3_SEED_CONTEXTUAL = [
    "bro this match is wild haha, btw anyone seen that giveaway link in the chat?",
    "ngl streamer is cracked today lol... also did the payout go through for anyone on t.me/event?",
    "wait what song is this?? sounds crazy. also got my 0.2 eth from the pinned promo earlier",
    "lmao he really missed that shot 💀 check @AlexSupport if you had questions about the drop",
    "W stream as always! btw guys the bonus round on telegram actually doubled my tokens",
    "can we clip that play?? crazy clutch. also verify with @CryptoSupport_Live for the gift cards",
    "bro is locked in right now haha. quick question did the airdrop transaction finish for you?",
    "GG! honestly didn't expect that win. reminder to claim your promo bonus before stream ends",
]

L4_SEED_MESSAGES = [
    "Really enjoying this walkthrough. Quick question: is anyone in here using that Telegram trading group mentioned earlier?",
    "Nice commentary today! By the way, thanks to whoever recommended @SarahHelper, she helped recover my wallet balance.",
    "First time catching the live stream! Loving the vibes. Also found that bonus reward link worked surprisingly fast.",
    "Such a chill stream tonight. Just wanted to ask if the community investment channel is still accepting new members?",
    "Great explanation of the mechanics. Off-topic, but the giveaway distribution mentioned in the Discord went smoothly.",
]


class AttackGenerator:
    """Generates synthetic adversarial campaigns according to the Stealth Ladder."""

    def __init__(self, cache_dir: str = CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        self.openai_key = os.environ.get("OPENAI_API_KEY")
        self.gemini_key = os.environ.get("GEMINI_API_KEY")

    def _get_cache_path(self, cache_key: str) -> str:
        return os.path.join(self.cache_dir, f"{cache_key}.json")

    def _query_llm(self, prompt: str, cache_key: str) -> Optional[List[str]]:
        """Queries LLM with local disk caching."""
        cache_path = self._get_cache_path(cache_key)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0:
                        return data
            except Exception:
                pass

        # Try Google GenAI
        if self.gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=self.gemini_key)
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                )
                text = response.text.strip()
                # Extract JSON array
                start = text.find("[")
                end = text.rfind("]")
                if start != -1 and end != -1:
                    result = json.loads(text[start:end+1])
                    if isinstance(result, list):
                        with open(cache_path, "w", encoding="utf-8") as f:
                            json.dump(result, f, indent=2)
                        return result
            except Exception as e:
                print(f"[AttackGenerator] Gemini API error: {e}")

        # Try OpenAI
        if self.openai_key:
            try:
                import openai
                client = openai.OpenAI(api_key=self.openai_key)
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                )
                text = resp.choices[0].message.content.strip()
                start = text.find("[")
                end = text.rfind("]")
                if start != -1 and end != -1:
                    result = json.loads(text[start:end+1])
                    if isinstance(result, list):
                        with open(cache_path, "w", encoding="utf-8") as f:
                            json.dump(result, f, indent=2)
                        return result
            except Exception as e:
                print(f"[AttackGenerator] OpenAI API error: {e}")

        return None

    def generate_l0_campaign(self, num_bots: int = 5, burst_messages: int = 10) -> List[Dict[str, Any]]:
        """L0: Copy-paste burst. Identical text sent by multiple accounts."""
        text = random.choice(L0_SEED_MESSAGES)
        bot_ids = [f"bot_l0_{i:03d}" for i in range(num_bots)]
        messages = []
        for i in range(burst_messages):
            author = random.choice(bot_ids)
            messages.append({
                "author": author,
                "text": text,
                "stealth_level": "L0",
                "campaign_type": "copy_paste_burst",
            })
        return messages

    def generate_l1_campaign(self, num_bots: int = 6, total_messages: int = 15) -> List[Dict[str, Any]]:
        """L1: Template with variable substitution."""
        template = random.choice(L1_TEMPLATES)
        bot_ids = [f"bot_l1_{i:03d}" for i in range(num_bots)]
        messages = []
        for i in range(total_messages):
            author = random.choice(bot_ids)
            coin = random.choice(COINS)
            amt = round(random.uniform(0.05, 0.5), 2)
            dbl = round(amt * 2.0, 2)
            text = template.format(
                amount=amt,
                coin=coin,
                double_amount=dbl,
                handle=random.choice(HANDLES),
                link=random.choice(LINKS),
                slots=random.randint(3, 15),
            )
            messages.append({
                "author": author,
                "text": text,
                "stealth_level": "L1",
                "campaign_type": "template_substitution",
            })
        return messages

    def generate_l2_campaign(self, num_bots: int = 6) -> List[Dict[str, Any]]:
        """L2: LLM Paraphrase of scam intent. 1 unique sentence per bot."""
        prompt_path = os.path.join(PROMPTS_DIR, "l2_paraphrase.txt")
        prompt = ""
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt = f.read()

        cache_key = "l2_paraphrase_" + hashlib.md5(prompt.encode()).hexdigest()[:10]
        sentences = self._query_llm(prompt, cache_key) or L2_SEED_PARAPHRASES

        # Ensure we have enough sentences
        while len(sentences) < num_bots:
            sentences.extend(L2_SEED_PARAPHRASES)

        bot_ids = [f"bot_l2_{i:03d}" for i in range(num_bots)]
        messages = []
        for idx in range(num_bots):
            messages.append({
                "author": bot_ids[idx],
                "text": sentences[idx % len(sentences)],
                "stealth_level": "L2",
                "campaign_type": "llm_paraphrase",
            })
        return messages

    def generate_l3_campaign(self, chat_topic: str = "esports gameplay", num_bots: int = 5) -> List[Dict[str, Any]]:
        """L3: LLM Context-aware chatter with typos/emoji/slang."""
        prompt_path = os.path.join(PROMPTS_DIR, "l3_contextual.txt")
        prompt_tpl = ""
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_tpl = f.read()

        prompt = prompt_tpl.replace("{chat_topic}", chat_topic).replace("{recent_context}", "Streamer hitting amazing shots, chat hyped")
        cache_key = "l3_contextual_" + hashlib.md5(prompt.encode()).hexdigest()[:10]
        sentences = self._query_llm(prompt, cache_key) or L3_SEED_CONTEXTUAL

        while len(sentences) < num_bots:
            sentences.extend(L3_SEED_CONTEXTUAL)

        bot_ids = [f"bot_l3_{i:03d}" for i in range(num_bots)]
        messages = []
        for idx in range(num_bots):
            messages.append({
                "author": bot_ids[idx],
                "text": sentences[idx % len(sentences)],
                "stealth_level": "L3",
                "campaign_type": "contextual_chameleon",
            })
        return messages

    def generate_l4_campaign(self, chat_topic: str = "chill stream", num_accounts: int = 8) -> List[Dict[str, Any]]:
        """L4: Low-and-slow. Many accounts each posting 1-2 messages spread over 10+ minutes."""
        prompt_path = os.path.join(PROMPTS_DIR, "l4_low_and_slow.txt")
        prompt_tpl = ""
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_tpl = f.read()

        prompt = prompt_tpl.replace("{chat_topic}", chat_topic)
        cache_key = "l4_slow_" + hashlib.md5(prompt.encode()).hexdigest()[:10]
        sentences = self._query_llm(prompt, cache_key) or L4_SEED_MESSAGES

        while len(sentences) < num_accounts:
            sentences.extend(L4_SEED_MESSAGES)

        messages = []
        for idx in range(num_accounts):
            author = f"bot_l4_{idx:03d}"
            messages.append({
                "author": author,
                "text": sentences[idx % len(sentences)],
                "stealth_level": "L4",
                "campaign_type": "low_and_slow",
            })
        return messages

    def generate_l3_single(self) -> Dict[str, Any]:
        """L3-Single: 1 stealth account, 1 message. Documented limit -> expected unverifiable."""
        text = random.choice(L3_SEED_CONTEXTUAL)
        return {
            "author": "bot_stealth_solo",
            "text": text,
            "stealth_level": "L3-single",
            "campaign_type": "isolated_stealth_actor",
        }
