"""
Starter dataset seeding module.
Executes authentic dynamic extraction across the starter corpus with zero hard-coded facts.
"""
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.ingest_starter_corpus import run_ingestion

def seed_data():
    run_ingestion(clean=True)

if __name__ == "__main__":
    seed_data()
