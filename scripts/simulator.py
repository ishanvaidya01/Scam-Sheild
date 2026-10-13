import argparse
import sys
import os

# Ensure the root directory is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from scripts.sim_engine.engine import SimulatorEngine
from scripts.sim_engine.scenarios.all_scenarios import (
    SelfRepeatScenario, ParaphraseAttackScenario, BurstAttackScenario, 
    BotHubScenario, MixedAttackScenario, CryptoRingScenario
)

WS_URL = "ws://localhost:8000/ws"

def main():
    parser = argparse.ArgumentParser(description="Scam Shield Synthetic Adversarial Simulator")
    parser.add_argument("--scenario", type=str, required=True, 
                        choices=["crypto_ring", "self_repeat", "paraphrase_attack", "burst_attack", "bot_hub", "mixed_attack"], 
                        help="The attack scenario to run")
    parser.add_argument("--intensity", type=str, default="medium", choices=["low", "medium", "high"], help="Attack intensity")
    
    args = parser.parse_args()
    
    if args.scenario == "crypto_ring":
        scenario = CryptoRingScenario(num_genuine=5, num_bots=5, duration_sec=25)
    elif args.scenario == "self_repeat":
        scenario = SelfRepeatScenario(num_genuine=5, num_bots=1, duration_sec=20)
    elif args.scenario == "paraphrase_attack":
        scenario = ParaphraseAttackScenario(num_genuine=5, num_bots=5, duration_sec=25)
    elif args.scenario == "burst_attack":
        scenario = BurstAttackScenario(num_genuine=5, num_bots=5, duration_sec=20)
    elif args.scenario == "bot_hub":
        scenario = BotHubScenario(num_genuine=5, num_bots=4, duration_sec=25)
    elif args.scenario == "mixed_attack":
        scenario = MixedAttackScenario(num_genuine=8, num_bots=5, duration_sec=30)
    else:
        print(f"Unknown scenario: {args.scenario}")
        return
        
    engine = SimulatorEngine(WS_URL)
    
    try:
        engine.run_scenario(scenario)
    except KeyboardInterrupt:
        print("\nSimulation aborted by user.")
    finally:
        engine.print_results()
        engine.stop()

if __name__ == "__main__":
    main()
