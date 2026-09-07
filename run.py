import sys
import subprocess
import argparse
from pathlib import Path
from typing import Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

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

def run_frontend():
    """Runs Next.js React frontend."""
    frontend_dir = Path(__file__).parent / "frontend"
    subprocess.run(["npm", "run", "dev"], cwd=str(frontend_dir), shell=True, check=True)

def run_ingest(pdf_path: str, max_chunks: Optional[int] = None):
    """Ingests an arbitrary PDF from command line, processing all chunks by default."""
    from app.services.pipeline import KnowledgeLayerPipeline
    pipeline = KnowledgeLayerPipeline()
    p = Path(pdf_path)
    if not p.exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)
    chunk_msg = f"max_chunks={max_chunks}" if max_chunks else "processing all pages"
    print(f"Ingesting: {pdf_path} ({chunk_msg})...")
    result = pipeline.process_pdf(p, filename=p.name, max_chunks=max_chunks)
    print("Ingestion Result:", result)

def run_corpus(clean: bool = True):
    """Ingests the full starter corpus dynamically from scratch."""
    from scripts.ingest_starter_corpus import run_ingestion
    run_ingestion(clean=clean)

def run_tests():
    """Runs pytest suite."""
    subprocess.run([sys.executable, "-m", "pytest", "tests/", "-v"], check=True)

def main():
    parser = argparse.ArgumentParser(description="Fact Knowledge Layer CLI")
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # ui
    subparsers.add_parser("ui", help="Launch Streamlit Web UI (port 8501)")

    # api
    subparsers.add_parser("api", help="Launch FastAPI REST Backend (port 8000)")

    # frontend
    subparsers.add_parser("frontend", help="Launch Next.js React Web UI (port 3000)")

    # corpus
    corpus_parser = subparsers.add_parser("corpus", help="Dynamically ingest the 6 starter PDFs")
    corpus_parser.add_argument("--append", action="store_true", help="Append without clearing existing DB")

    # ingest
    ingest_parser = subparsers.add_parser("ingest", help="Ingest an arbitrary PDF file")
    ingest_parser.add_argument("pdf_path", type=str, help="Path to PDF")
    ingest_parser.add_argument("--max-chunks", type=int, default=None, help="Optional chunk limit (default: all pages)")

    # test
    subparsers.add_parser("test", help="Run automated test suite")

    args = parser.parse_args()

    if args.command == "ui":
        run_ui()
    elif args.command == "frontend":
        run_frontend()
    elif args.command == "api":
        run_api()
    elif args.command == "corpus":
        run_corpus(clean=not args.append)
    elif args.command == "ingest":
        run_ingest(args.pdf_path, args.max_chunks)
    elif args.command == "test":
        run_tests()
    else:
        print("Usage: python run.py [frontend | api | ui | corpus | ingest <path> | test]")
        print("Defaulting to launching Next.js Frontend...")
        run_frontend()

if __name__ == "__main__":
    main()
