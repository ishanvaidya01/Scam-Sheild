import os
import sys
import pandas as pd

def label_data(input_file):
    if not os.path.exists(input_file):
        print(f"File not found: {input_file}")
        return
        
    df = pd.read_csv(input_file)
    
    if 'label' not in df.columns:
        df['label'] = None
        
    unlabeled = df[df['label'].isna()]
    if len(unlabeled) == 0:
        print("All rows are already labeled!")
        return
        
    print(f"Found {len(unlabeled)} unlabeled rows out of {len(df)} total.")
    print("Labels: [s] scam | [c] coordinated_spam | [g] genuine | [q] quit")
    
    for idx, row in unlabeled.iterrows():
        print("-" * 50)
        print(f"User : {row['username']}")
        print(f"Text : {row['text']}")
        print("-" * 50)
        
        while True:
            choice = input("Label (s/c/g/q): ").strip().lower()
            if choice == 's':
                df.at[idx, 'label'] = 'scam'
                break
            elif choice == 'c':
                df.at[idx, 'label'] = 'coordinated_spam'
                break
            elif choice == 'g':
                df.at[idx, 'label'] = 'genuine'
                break
            elif choice == 'q':
                # Save and quit
                out_file = input_file.replace('raw', 'processed')
                os.makedirs(os.path.dirname(out_file), exist_ok=True)
                df.to_csv(out_file, index=False)
                print(f"Saved progress to {out_file}")
                return
            else:
                print("Invalid choice.")
                
    out_file = input_file.replace('raw', 'processed')
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    df.to_csv(out_file, index=False)
    print(f"All done! Saved to {out_file}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python label_data.py <path_to_raw_csv>")
        sys.exit(1)
    label_data(sys.argv[1])
