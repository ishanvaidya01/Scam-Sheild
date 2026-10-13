from abc import ABC, abstractmethod
from typing import List, Dict, Any, Generator

class BaseScenario(ABC):
    def __init__(self, num_genuine: int, num_bots: int, duration_sec: int):
        self.num_genuine = num_genuine
        self.num_bots = num_bots
        self.duration_sec = duration_sec
        self.genuine_users = []
        self.bot_users = []
        
    def setup_users(self):
        from scripts.sim_engine.user_model import SimulatedUser
        self.genuine_users = [SimulatedUser(is_bot=False) for _ in range(self.num_genuine)]
        self.bot_users = [SimulatedUser(is_bot=True) for _ in range(self.num_bots)]
        
    @abstractmethod
    def generate_timeline(self, start_time_ms: int) -> Generator[Dict[str, Any], None, None]:
        """
        Yields a sequence of events.
        An event should be a dictionary containing at least:
        - 'timestamp_ms': When this event happens
        - 'payload': The actual message dictionary to send
        - 'ground_truth': 'BOT' or 'GENUINE'
        """
        pass
