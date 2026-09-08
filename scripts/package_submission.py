import os
import sys
import zipfile
from pathlib import Path
from typing import Optional

# Ensure stdout handles unicode
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

EXCLUDE_DIRS = {
    "node_modules",
    ".next",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".vscode",
    ".idea",
    "venv",
    ".venv",
    "env",
    "dist",
    "build",
}

EXCLUDE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".log",
    ".tmp",
    ".db",
    ".db-shm",
    ".db-wal",
    ".db-journal",
}

EXCLUDE_FILES = {
    ".env",
    "SuperJoin_Submission.zip",
    "SuperJoin.zip",
    "superjoin-vit-2026-assignment.pdf",
}

def is_excluded(item: Path, root_dir: Path) -> bool:
    rel_path = item.relative_to(root_dir)
    parts = rel_path.parts

    # Exclude directories
    if any(part in EXCLUDE_DIRS for part in parts[:-1]):
        return True

    # Exclude extensions
    if item.suffix.lower() in EXCLUDE_EXTENSIONS:
        return True

    # Exclude specific files
    if item.name in EXCLUDE_FILES:
        return True

    # Exclude any .env file other than .env.example
    if item.name.startswith(".env") and item.name != ".env.example":
        return True

    # Exclude any assignment PDF
    if "assignment" in item.name.lower() and item.name.lower().endswith(".pdf"):
        return True

    # Exclude zip and temporary files
    if item.name.endswith(".zip") or item.name.startswith("tmp_"):
        return True

    return False

def create_clean_zip(output_zip_path: Optional[str] = None) -> Path:
    root_dir = Path(__file__).resolve().parent.parent
    
    # Target paths: SuperJoin_Submission.zip and SuperJoin.zip in parent directory
    if output_zip_path:
        target_paths = [Path(output_zip_path)]
    else:
        target_paths = [
            root_dir.parent / "SuperJoin_Submission.zip",
            root_dir.parent / "SuperJoin.zip",
        ]

    print("=" * 70)
    print("📦 Creating Clean, Lightweight SuperJoin Project Submission Archive")
    print("=" * 70)

    # Collect files to package
    files_to_package = []
    total_uncompressed_bytes = 0

    for item in sorted(root_dir.rglob("*")):
        if not item.is_file():
            continue
        if is_excluded(item, root_dir):
            continue

        rel_path = item.relative_to(root_dir)
        files_to_package.append((item, rel_path))
        total_uncompressed_bytes += item.stat().st_size

    for zip_path in target_paths:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for item, rel_path in files_to_package:
                # Include standard root folder SuperJoin/ for clean extraction
                arcname = f"SuperJoin/{rel_path.as_posix()}"
                zipf.write(item, arcname=arcname)

        # Strict validation of generated zip
        with zipfile.ZipFile(zip_path, "r") as check_zip:
            names = check_zip.namelist()
            assert not any(part == ".git" for n in names for part in Path(n).parts), f"Error: .git directory found in {zip_path.name}"
            assert not any(n.endswith("/.env") or n == "SuperJoin/.env" or n == ".env" for n in names), f"Error: .env file found in {zip_path.name}"
            assert not any("assignment" in n.lower() and n.endswith(".pdf") for n in names), f"Error: assignment PDF found in {zip_path.name}"
            assert any(n.endswith(".env.example") for n in names), f"Error: .env.example missing from {zip_path.name}"

        zip_size_bytes = zip_path.stat().st_size
        zip_size_mb = zip_size_bytes / (1024 * 1024)
        uncompressed_mb = total_uncompressed_bytes / (1024 * 1024)

        print(f"\n✅ Successfully created: {zip_path.name}")
        print(f"  • Location           : {zip_path}")
        print(f"  • Files Packaged     : {len(files_to_package)} files")
        print(f"  • Uncompressed Size  : {uncompressed_mb:.2f} MB")
        print(f"  • Compressed ZIP Size: {zip_size_mb:.2f} MB")
        print(f"  • Excluded Folders   : node_modules (~453 MB), .next (~140 MB), .git (~19 MB), caches (~15 MB)")
        print(f"  • Excluded Files     : .env (local secrets), superjoin-vit-2026-assignment.pdf")
        print(f"  • Verification       : PASSED (Zero .git, Zero .env, Zero assignment PDFs)")

    print(f"\n🚀 Ready for GitHub / Submission without leaks or bloat.")
    print("=" * 70)

    return target_paths[0]

def clean_local_temp_files(clean_node_modules: bool = False):
    """Removes local build artifacts (.next, __pycache__, .pytest_cache, zip files, and db caches) to reclaim disk space."""
    root_dir = Path(__file__).resolve().parent.parent
    print("🧹 Cleaning local temporary build artifacts...")

    reclaimed_bytes = 0

    # Clean zip files inside project root
    for zip_file in root_dir.glob("*.zip"):
        if zip_file.is_file():
            reclaimed_bytes += zip_file.stat().st_size
            zip_file.unlink(missing_ok=True)

    # Clean __pycache__
    for pycache in root_dir.rglob("__pycache__"):
        if pycache.is_dir():
            for f in pycache.rglob("*"):
                if f.is_file():
                    reclaimed_bytes += f.stat().st_size
            import shutil
            shutil.rmtree(pycache, ignore_errors=True)

    # Clean .pytest_cache
    pytest_cache = root_dir / ".pytest_cache"
    if pytest_cache.exists():
        for f in pytest_cache.rglob("*"):
            if f.is_file():
                reclaimed_bytes += f.stat().st_size
        import shutil
        shutil.rmtree(pytest_cache, ignore_errors=True)

    # Clean frontend/.next
    next_dir = root_dir / "frontend" / ".next"
    if next_dir.exists():
        for f in next_dir.rglob("*"):
            if f.is_file():
                reclaimed_bytes += f.stat().st_size
        import shutil
        shutil.rmtree(next_dir, ignore_errors=True)

    # Clean data/processed/*.db
    db_file = root_dir / "data" / "processed" / "fact_knowledge.db"
    if db_file.exists():
        reclaimed_bytes += db_file.stat().st_size
        db_file.unlink(missing_ok=True)

    # Clean node_modules if requested
    if clean_node_modules:
        nm_dir = root_dir / "frontend" / "node_modules"
        if nm_dir.exists():
            for f in nm_dir.rglob("*"):
                if f.is_file():
                    reclaimed_bytes += f.stat().st_size
            import shutil
            shutil.rmtree(nm_dir, ignore_errors=True)

    reclaimed_mb = reclaimed_bytes / (1024 * 1024)
    print(f"✅ Cleaned temporary files. Reclaimed {reclaimed_mb:.2f} MB of disk space.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        clean_local_temp_files()
    else:
        create_clean_zip()
