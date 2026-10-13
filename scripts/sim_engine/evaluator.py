class Evaluator:
    def __init__(self):
        self.ground_truth_map = {}  # comment_id -> "BOT" or "GENUINE"
        self.predictions = {}       # comment_id -> result_dict
        self.start_times = {}       # comment_id -> time.time()
        self.latencies = []
        
    def record_ground_truth(self, comment_id: str, ground_truth: str, send_time: float):
        self.ground_truth_map[comment_id] = ground_truth
        self.start_times[comment_id] = send_time
        
    def record_prediction(self, result: dict, receive_time: float):
        comment_id = result.get("comment_id")
        if comment_id in self.start_times:
            latency = receive_time - self.start_times[comment_id]
            self.latencies.append(latency)
        
        self.predictions[comment_id] = result
        
    def print_metrics(self):
        print("\n" + "="*50)
        print("       SCAM SHIELD ADVERSARIAL SIMULATOR   ")
        print("="*50)
        
        tp = fp = tn = fn = 0
        
        for comment_id, truth in self.ground_truth_map.items():
            if comment_id not in self.predictions:
                continue
                
            pred_tier = self.predictions[comment_id].get("tier", "trusted")
            # In Scam Shield, 'scam' and 'high_risk' and 'suspicious' usually mean flagged.
            # Let's consider tier == "scam" or "high_risk" as BOT prediction.
            # Based on the architecture:
            # scam < 0.2, high_risk < 0.4, suspicious < 0.6
            # Let's use < 0.4 (high_risk and scam) as a positive prediction for BOT.
            
            score = self.predictions[comment_id].get("trust_score", 1.0)
            is_pred_bot = score < 0.4 
            is_actual_bot = truth == "BOT"
            
            if is_actual_bot and is_pred_bot:
                tp += 1
            elif is_actual_bot and not is_pred_bot:
                fn += 1
            elif not is_actual_bot and is_pred_bot:
                fp += 1
            elif not is_actual_bot and not is_pred_bot:
                tn += 1
                
        total = tp + fp + tn + fn
        if total == 0:
            print("No predictions received.")
            return
            
        accuracy = (tp + tn) / total
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        avg_latency_ms = (sum(self.latencies) / len(self.latencies)) * 1000 if self.latencies else 0
        
        print(f"Messages generated:        {len(self.ground_truth_map)}")
        print(f"Messages received/scored:  {total}")
        print(f"Ground-truth bot count:    {list(self.ground_truth_map.values()).count('BOT')}")
        print(f"Predicted bot/scam count:  {tp + fp}")
        print("-" * 30)
        print(f"True Positives (TP):       {tp}")
        print(f"False Positives (FP):      {fp}")
        print(f"True Negatives (TN):       {tn}")
        print(f"False Negatives (FN):      {fn}")
        print("-" * 30)
        print(f"Accuracy:                  {accuracy:.2f}")
        print(f"Precision:                 {precision:.2f}")
        print(f"Recall:                    {recall:.2f}")
        print(f"F1-score:                  {f1:.2f}")
        print(f"Average detection latency: {avg_latency_ms:.0f} ms")
        print("="*50)
