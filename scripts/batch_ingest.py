"""Batch ingestion script — recursively ingest all supported documents in a directory.

Usage:
    # Ingest all docs in a directory (recursive)
    python scripts/batch_ingest.py --path data/documents/fastapi-docs/

    # Limit concurrency (default: 2) to respect API rate limits
    python scripts/batch_ingest.py --path data/documents/fastapi-docs/ --workers 4

    # Filter by file extension
    python scripts/batch_ingest.py --path data/documents/ --ext .md --ext .txt

    # Force rebuild all documents
    python scripts/batch_ingest.py --path data/documents/ --force-rebuild

    # Dry run (collect files only, no ingestion)
    python scripts/batch_ingest.py --path data/documents/ --dry-run

    # Save summary report to JSON file
    python scripts/batch_ingest.py --path data/documents/ --report batch_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# Allow running from project root directly
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_PATH = _PROJECT_ROOT / "backend" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

from rag_mcp.application.handlers import ingest_document  # noqa: E402
from rag_mcp.factory import get_rag, reset_rag  # noqa: E402
from rag_mcp.core.exceptions import IngestionError  # noqa: E402

# Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def _collect_files(
    root: Path,
    recursive: bool = True,
    extensions: list[str] | None = None,
) -> list[Path]:
    """Collect all supported files under a directory.

    Args:
        root: Directory or file path.
        recursive: Whether to recurse into subdirectories.
        extensions: File extensions to include (leading dot, e.g. ['.md', '.pdf']).
                    If None, use supported_extensions from settings.

    Returns:
        Sorted list of matching file paths.
    """
    if root.is_file():
        if extensions is None:
            return [root]
        return [root] if root.suffix.lower() in {e.lower() for e in extensions} else []

    if not root.is_dir():
        return []

    pattern = "**/*" if recursive else "*"
    ext_set = {e.lower() for e in extensions} if extensions else None

    files = []
    for p in root.glob(pattern):
        if not p.is_file():
            continue
        if ext_set is None or p.suffix.lower() in ext_set:
            files.append(p)

    return sorted(files)


def _ingest_one(path: Path, force_rebuild: bool) -> dict:
    """Ingest a single file. Returns a result dict."""
    start = time.perf_counter()
    try:
        rag = get_rag()
        result = ingest_document(rag, str(path), force_rebuild=force_rebuild)
        elapsed = time.perf_counter() - start
        return {
            "file": str(path),
            "filename": path.name,
            "status": result["ingestion_action"],
            "document_id": result["document_id"],
            "chunk_count": result["chunk_count"],
            "trace_id": result["trace_id"],
            "replaced_existing": result["replaced_existing"],
            "elapsed_s": round(elapsed, 2),
        }
    except IngestionError as exc:
        elapsed = time.perf_counter() - start
        return {
            "file": str(path),
            "filename": path.name,
            "status": "error",
            "error": str(exc),
            "elapsed_s": round(elapsed, 2),
        }
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - start
        return {
            "file": str(path),
            "filename": path.name,
            "status": "error",
            "error": f"unexpected: {exc}",
            "elapsed_s": round(elapsed, 2),
        }


def _format_status(status: str) -> str:
    """Return a display symbol for the ingestion status."""
    symbols = {
        "created": "✓",
        "replaced": "↻",
        "skipped": "○",
        "error": "✗",
    }
    return symbols.get(status, "?")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch-ingest documents into RAG-MCP knowledge base."
    )
    parser.add_argument(
        "--path",
        required=True,
        help="Root directory (or single file) to ingest from.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Max concurrent ingestion workers (default: 2). Set to 1 for sequential.",
    )
    parser.add_argument(
        "--ext",
        action="append",
        default=None,
        help="File extension filter (can repeat, e.g. --ext .md --ext .txt). "
        "If omitted, uses supported_extensions from settings.yaml.",
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Force rebuild existing document indexes.",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not recurse into subdirectories.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect and list files without ingesting.",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Save a JSON summary report to the specified path.",
    )
    args = parser.parse_args()

    root = Path(args.path).expanduser().resolve()
    if not root.exists():
        print(f"[error] path does not exist: {root}", file=sys.stderr)
        return 2

    # Collect files
    container = get_rag()
    extensions = args.ext if args.ext else rag.settings.ingestion.supported_extensions
    files = _collect_files(root, recursive=not args.no_recursive, extensions=extensions)
    reset_rag()

    if not files:
        print(
            f"[warn] no files found. extensions={extensions}, path={root}",
            file=sys.stderr,
        )
        return 1

    print(f"[info] found {len(files)} file(s), extensions={extensions}")
    if args.workers > 1:
        print(f"[info] concurrency: {args.workers} workers")

    if args.dry_run:
        print("\n[dry-run] files that would be ingested:")
        for f in files:
            print(f"  {f}")
        return 0

    # Ingest
    max_workers = max(1, args.workers)
    results: list[dict] = []
    start_all = time.perf_counter()

    if max_workers == 1:
        # Sequential mode
        for idx, file_path in enumerate(files, start=1):
            print(f"[{idx}/{len(files)}] {file_path.name} ...", end=" ", flush=True)
            result = _ingest_one(file_path, args.force_rebuild)
            results.append(result)
            symbol = _format_status(result["status"])
            extra = ""
            if result["status"] == "error":
                extra = f" -- {result.get('error', 'unknown')}"
            else:
                extra = f" | chunks={result.get('chunk_count', 0)}"
            print(f"{symbol}{extra}")
    else:
        # Concurrent mode — reuse container per-file (each call gets its own via get_container)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_ingest_one, f, args.force_rebuild): f
                for f in files
            }
            done_count = 0
            for future in as_completed(futures):
                done_count += 1
                file_path = futures[future]
                result = future.result()
                results.append(result)
                symbol = _format_status(result["status"])
                extra = ""
                if result["status"] == "error":
                    extra = f" -- {result.get('error', 'unknown')}"
                else:
                    extra = f" | chunks={result.get('chunk_count', 0)}"
                print(
                    f"[{done_count}/{len(files)}] {file_path.name} {symbol}{extra}"
                )

    elapsed_all = time.perf_counter() - start_all

    # Summary
    succeeded = sum(1 for r in results if r["status"] != "error")
    failed = sum(1 for r in results if r["status"] == "error")
    created = sum(1 for r in results if r["status"] == "created")
    replaced = sum(1 for r in results if r["status"] == "replaced")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    total_chunks = sum(r.get("chunk_count", 0) for r in results)

    print(f"\n{'='*50}")
    print(f"  Total files : {len(files)}")
    print(f"  Created     : {created}")
    print(f"  Replaced    : {replaced}")
    print(f"  Skipped     : {skipped}")
    print(f"  Failed      : {failed}")
    print(f"  Total chunks: {total_chunks}")
    print(f"  Elapsed     : {elapsed_all:.1f}s")
    if args.workers > 1:
        print(f"  Throughput  : {succeeded / max(elapsed_all, 0.1):.1f} files/s")
    print(f"{'='*50}")

    # Save report if requested
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_path": str(root),
            "extensions": extensions,
            "force_rebuild": args.force_rebuild,
            "workers": args.workers,
            "summary": {
                "total": len(files),
                "created": created,
                "replaced": replaced,
                "skipped": skipped,
                "failed": failed,
                "total_chunks": total_chunks,
                "elapsed_s": round(elapsed_all, 1),
            },
            "files": results,
        }
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n[report] saved to {report_path}")

    # Release resources
    reset_rag()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
