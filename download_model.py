"""Download the fine-tuned BERT fake news model into ./bert_fake_news_model.

Model: https://huggingface.co/Pulk17/Fake-News-Detection (bert-base-uncased, Apache-2.0).
Output index 1 = Real, 0 = Fake.
"""
from pathlib import Path

from huggingface_hub import snapshot_download

MODEL_ID = "Pulk17/Fake-News-Detection"
MODEL_DIR = Path(__file__).resolve().parent / "bert_fake_news_model"

if __name__ == "__main__":
    snapshot_download(MODEL_ID, local_dir=MODEL_DIR, allow_patterns=["*.json", "*.txt", "*.safetensors"])
    print(f"Model saved to {MODEL_DIR}")
