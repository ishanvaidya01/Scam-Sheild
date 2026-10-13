"""
install.py — One-shot setup script for Scam Shield v2.

Run this after cloning the repo:
    python install.py
"""
import subprocess
import sys


def run(cmd, desc):
    print(f"\n{'='*60}")
    print(f"▶  {desc}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"⚠  Warning: '{cmd}' exited with code {result.returncode}")
    else:
        print(f"✅  Done: {desc}")


if __name__ == "__main__":
    run(
        f"{sys.executable} -m pip install -r backend/requirements.txt",
        "Installing Python dependencies",
    )
    run(
        f"{sys.executable} -m spacy download en_core_web_sm",
        "Downloading spaCy NLP model (en_core_web_sm)",
    )
    run(
        f"{sys.executable} scripts/download_public_data.py",
        "Downloading & processing UCI YouTube Spam dataset",
    )
    print("\n" + "="*60)
    print("🛡️  Scam Shield v2 setup complete!")
    print("="*60)
    print("\nTo run the backend:")
    print("  cd backend && uvicorn main:app --reload")
    print("\nThen load the extension from the 'extension/' folder in Chrome.")
