import sys
import subprocess
import argparse
from pathlib import Path

def run_ui():
    """Runs Streamlit application."""
    app_path = Path(__file__).parent / "app" / "ui" / "streamlit_app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path)], check=True)

def run_api():
    """Runs FastAPI uvicorn server."""
    subprocess.run([
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "0.0.0.0", "--port", "8000", "--reload"
    ], check=True)

def run_ingest(pdf_path: str, max_chunks: int = 15):
    """Ingests a PDF from command line."""
    from app.services.pipeline import KnowledgeLayerPipeline
    pipeline = KnowledgeLayerPipeline()
    p = Path(pdf_path)
    if not p.exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)
    print(f"Ingesting: {pdf_path} (max_chunks={max_chunks})...")
    result = pipeline.process_pdf(p, filename=p.name, max_chunks=max_chunks)
    print("Ingestion Result:", result)

def run_tests():
    """Runs pytest suite."""
    subprocess.run([sys.executable, "-m", "pytest", "tests/", "-v"], check=True)

def main():
    parser = argparse.ArgumentParser(description="Fact Knowledge Layer CLI")
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # ui
    subparsers.add_parser("ui", help="Launch Streamlit Web UI")

    # api
    subparsers.add_parser("api", help="Launch FastAPI REST Backend")

    # ingest
    ingest_parser = subparsers.add_parser("ingest", help="Ingest a PDF file")
    ingest_parser.add_argument("pdf_path", type=str, help="Path to PDF")
    ingest_parser.add_argument("--max-chunks", type=int, default=15, help="Limit number of chunks to process")

    # test
    subparsers.add_parser("test", help="Run automated test suite")

    args = parser.parse_args()

    if args.command == "ui":
        run_ui()
    elif args.command == "api":
        run_api()
    elif args.command == "ingest":
        run_ingest(args.pdf_path, args.max_chunks)
    elif args.command == "test":
        run_tests()
    else:
        print("Usage: python run.py [ui | api | ingest <path> | test]")
        print("Defaulting to launching Streamlit UI...")
        run_ui()

if __name__ == "__main__":
    main()
