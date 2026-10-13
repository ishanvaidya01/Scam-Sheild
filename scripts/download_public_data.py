import os
import urllib.request
import zipfile
import pandas as pd
import uuid

# Paths
RAW_DIR = os.path.join("data", "raw", "uci_spam")
PROCESSED_FILE = os.path.join("data", "processed", "uci_spam.csv")
UCI_URL = "https://archive.ics.uci.edu/static/public/380/youtube+spam+collection.zip"

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def download_and_extract():
    ensure_dir(RAW_DIR)
    zip_path = os.path.join(RAW_DIR, "dataset.zip")
    
    if not os.path.exists(zip_path):
        print(f"Downloading UCI dataset from {UCI_URL}...")
        urllib.request.urlretrieve(UCI_URL, zip_path)
        print("Download complete.")
        
    print("Extracting...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(RAW_DIR)

def process_data():
    all_dfs = []
    for file in os.listdir(RAW_DIR):
        if file.endswith(".csv"):
            df = pd.read_csv(os.path.join(RAW_DIR, file))
            # Expected UCI columns: COMMENT_ID, AUTHOR, DATE, CONTENT, CLASS (0=ham, 1=spam)
            
            # Map columns to our schema
            schema_df = pd.DataFrame()
            schema_df['comment_id'] = df['COMMENT_ID'].fillna(pd.Series([str(uuid.uuid4()) for _ in range(len(df))]))
            schema_df['text'] = df['CONTENT']
            schema_df['username'] = df['AUTHOR']
            
            # Convert DATE to timestamp (unix ms)
            # Some dates might be missing or malformed
            schema_df['timestamp'] = pd.to_datetime(df['DATE'], errors='coerce').astype('int64') // 10**6
            # Handle NaT which becomes negative
            schema_df['timestamp'] = schema_df['timestamp'].apply(lambda x: 0 if x < 0 else x)
            
            # Map CLASS
            schema_df['label'] = df['CLASS'].map({1: 'scam', 0: 'genuine'})
            
            all_dfs.append(schema_df)
            
    if all_dfs:
        final_df = pd.concat(all_dfs, ignore_index=True)
        # Filter out rows with empty text
        final_df = final_df[final_df['text'].notna()]
        
        os.makedirs(os.path.dirname(PROCESSED_FILE), exist_ok=True)
        final_df.to_csv(PROCESSED_FILE, index=False)
        print(f"Processed UCI data saved to {PROCESSED_FILE}")
        print(f"Total rows: {len(final_df)}")
        print(final_df['label'].value_counts())
    else:
        print("No CSV files found to process.")

if __name__ == "__main__":
    download_and_extract()
    process_data()
