import time
import json
import threading
from websocket import create_connection
from scripts.sim_engine.evaluator import Evaluator
from scripts.sim_engine.scenarios.base import BaseScenario

class SimulatorEngine:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws = None
        self.evaluator = Evaluator()
        self.running = False
        self.sent_messages = {} # Store info to print cleanly on response
        
    def connect(self):
        print(f"Connecting to {self.ws_url}...")
        self.ws = create_connection(self.ws_url)
        self.running = True
        
        # Start listener thread
        threading.Thread(target=self._listen, daemon=True).start()
        
    def _listen(self):
        while self.running:
            try:
                res = self.ws.recv()
                data = json.loads(res)
                if data.get("type") in ["SENSITIVITY_ACK", "STATS"]:
                    continue
                    
                receive_time = time.time()
                self.evaluator.record_prediction(data, receive_time)
                
                # Clean Output Formatting
                comment_id = data.get("comment_id")
                if comment_id in self.sent_messages:
                    orig = self.sent_messages[comment_id]
                    username = orig["username"]
                    text = orig["text"]
                    truth = orig["ground_truth"]
                    
                    tier = data.get("tier_label", "Unknown")
                    score = data.get("trust_score", 1.0)
                    reasons = data.get("reasons", [])
                    
                    indicator = "[BOT]" if truth == "BOT" else "[GEN]"
                    
                    print(f"\n{indicator} {username}: {text}".encode('ascii', 'ignore').decode('ascii'))
                    if score < 0.4:
                        print(f"  └── [FLAGGED] [Score: {score:.2f} | Tier: {tier}]".encode('ascii', 'ignore').decode('ascii'))
                        for r in reasons:
                            print(f"      - {r.get('text')} ({r.get('signal')})".encode('ascii', 'ignore').decode('ascii'))
                    else:
                        print(f"  └── [PASSED] [Score: {score:.2f} | Tier: {tier}]".encode('ascii', 'ignore').decode('ascii'))
                    
            except Exception as e:
                if self.running:
                    print(f"WS error: {e}")
                break
                
    def run_scenario(self, scenario: BaseScenario):
        if not self.ws:
            self.connect()
            
        print(f"\nStarting scenario: {scenario.__class__.__name__}")
        start_time_ms = int(time.time() * 1000)
        timeline = list(scenario.generate_timeline(start_time_ms))
        
        if not timeline:
            print("No events in timeline.")
            return
            
        first_event_ms = timeline[0]["timestamp_ms"]
        sim_start_time = time.time()
        print(f"Simulating {len(timeline)} messages over {scenario.duration_sec} seconds...\n")
        
        for event in timeline:
            target_ms = event["timestamp_ms"]
            offset_sec = (target_ms - first_event_ms) / 1000.0
            send_at = sim_start_time + offset_sec
            
            now = time.time()
            if send_at > now:
                time.sleep(send_at - now)
                
            payload = event["payload"]
            truth = event["ground_truth"]
            
            # Store for printing later
            self.sent_messages[payload["comment_id"]] = {
                "text": payload["text"],
                "username": payload["username"],
                "ground_truth": truth
            }
            
            self.evaluator.record_ground_truth(payload["comment_id"], truth, time.time())
            self.ws.send(json.dumps(payload))
            
        print("\nTimeline finished. Waiting for final responses...")
        time.sleep(4) 
        
    def stop(self):
        self.running = False
        if self.ws:
            self.ws.close()
            
    def print_results(self):
        self.evaluator.print_metrics()
