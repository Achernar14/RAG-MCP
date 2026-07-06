"""Fetch documents from a GitHub repository's docs/ directory.

Usage:
    # Fetch FastAPI docs (default)
    python scripts/fetch_docs.py

    # Fetch a specific repo's docs
    python scripts/fetch_docs.py --repo encode/httpx

    # Custom branch and docs directory
    python scripts/fetch_docs.py --repo fastapi/fastapi --branch master --docs-dir docs/en/docs

    # Specify output directory
    python scripts/fetch_docs.py --output data/documents/my-docs/
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Allow running from project root directly
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_OUTPUT_BASE = _PROJECT_ROOT / "data" / "documents"

# Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def _run_git(args: list[str], cwd: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a git command and return the completed process."""
    cmd = ["git"] + args
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _check_git() -> bool:
    """Check if git is available."""
    try:
        result = _run_git(["--version"])
        return result.returncode == 0
    except FileNotFoundError:
        return False
    except Exception:
        return False


def fetch_docs(
    repo: str,
    *,
    branch: str | None = None,
    docs_dir: str = "docs",
    output: Path | None = None,
) -> tuple[int, Path]:
    """Fetch .md documents from a GitHub repository.

    Uses shallow sparse checkout for minimal download.

    Returns (file_count, output_path).
    """
    repo_url = f"https://github.com/{repo}.git"
    repo_name = repo.split("/")[-1]
    output_path = output or (_OUTPUT_BASE / f"{repo_name}-docs")

    print(f"[repo] {repo_url}")
    print(f"[docs-dir] {docs_dir}")

    with tempfile.TemporaryDirectory(prefix=f"ragmcp_fetch_{repo_name}_") as tmp:
        tmp_path = Path(tmp)

        # ── 1. Shallow sparse clone ──────────────────────
        # Try sparse checkout first (git >= 2.25), fall back to full shallow clone
        print("[clone] shallow cloning (sparse, depth=1)...")
        clone_args = [
            "clone",
            "--depth=1",
            "--filter=blob:none",
            "--sparse",
            repo_url,
            str(tmp_path),
        ]
        result = _run_git(clone_args)

        if result.returncode != 0:
            # Fallback: full shallow clone without sparse filter
            print("[clone] sparse clone failed, trying full shallow clone...")
            clone_args = ["clone", "--depth=1", repo_url, str(tmp_path)]
            result = _run_git(clone_args)
            if result.returncode != 0:
                print(f"[error] clone failed:\n{result.stderr}", file=sys.stderr)
                return 0, output_path

        # ── 2. Sparse checkout to docs/ ──────────────────
        if "--sparse" in clone_args:
            result = _run_git(["sparse-checkout", "set", docs_dir], cwd=tmp_path)
            if result.returncode != 0:
                print(f"[warn] sparse-checkout set '{docs_dir}' failed, will scan entire repo")

        # ── 3. Collect .md files ─────────────────────────
        docs_path = tmp_path / docs_dir
        if not docs_path.exists():
            print(f"[warn] '{docs_dir}/' not found in repo root; attempting to locate...")
            # Try common docs paths
            candidates = [
                tmp_path / "docs",
                tmp_path / "documentation",
                tmp_path,
            ]
            docs_path = None
            for cand in candidates:
                if cand.exists():
                    md_files = list(cand.rglob("*.md"))
                    if md_files:
                        docs_path = cand
                        print(f"[found] using '{cand.relative_to(tmp_path)}/' ({len(md_files)} .md files)")
                        break
            if docs_path is None:
                print("[error] no .md files found in repo", file=sys.stderr)
                return 0, output_path

        md_files = sorted(docs_path.rglob("*.md"))
        if not md_files:
            print("[error] no .md files found under docs/", file=sys.stderr)
            return 0, output_path

        print(f"[found] {len(md_files)} .md files")

        # ── 4. Copy to output ────────────────────────────
        output_path.mkdir(parents=True, exist_ok=True)
        copied = 0
        for src in md_files:
            # Preserve subdirectory structure relative to docs_path
            rel = src.relative_to(docs_path)
            dst = output_path / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1

    print(f"[done] {copied} files → {output_path}")
    return copied, output_path


def main() -> int:
    if not _check_git():
        print("[error] git is not available; please install git and try again", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(
        description="Fetch .md documents from a GitHub repository's docs/ directory."
    )
    parser.add_argument(
        "--repo",
        default="fastapi/fastapi",
        help="GitHub repository in owner/repo format (default: fastapi/fastapi)",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Branch to clone (default: repo default branch)",
    )
    parser.add_argument(
        "--docs-dir",
        default="docs",
        help="Path within repo to scan for .md files (default: docs)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory (default: data/documents/{repo}-docs/)",
    )
    args = parser.parse_args()

    if "/" not in args.repo or args.repo.count("/") != 1:
        print("[error] --repo must be in 'owner/repo' format", file=sys.stderr)
        return 2

    output = Path(args.output) if args.output else None
    count, out_path = fetch_docs(
        repo=args.repo,
        branch=args.branch,
        docs_dir=args.docs_dir,
        output=output,
    )

    if count == 0:
        print("[warn] no documents were fetched", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
