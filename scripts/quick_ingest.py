"""Quick ingestion helper -- ingest a single file or a whole directory.

Usage:
    # 摄入单个文件
    python scripts/quick_ingest.py --path path/to/doc.md

    # 摄入目录下所有支持的文档（递归）
    python scripts/quick_ingest.py --path path/to/docs/ --recursive

    # 强制重建已存在的文档索引
    python scripts/quick_ingest.py --path path/to/doc.md --force-rebuild

支持的文件扩展名由 settings.yaml 中 ingestion.supported_extensions 决定（默认 .txt/.md/.pdf）。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Windows 控制台默认 GBK 编码，无法输出 ✓/✗ 等 Unicode 符号，强制 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 允许从项目根目录直接运行脚本（未 pip install 时回退到 src 路径）
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_PATH = _PROJECT_ROOT / "backend" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

from rag_mcp.application.dto.models import IngestRequest  # noqa: E402
from rag_mcp.core.container import get_container, reset_container  # noqa: E402
from rag_mcp.core.exceptions import IngestionError  # noqa: E402


def _ingest_one(path: Path, force_rebuild: bool) -> tuple[bool, str]:
    """Ingest a single file. Returns (success, message)."""
    container = get_container()
    try:
        response = container.ingest_use_case.execute(
            IngestRequest(path=str(path), force_rebuild=force_rebuild)
        )
    except IngestionError as exc:
        return False, f"ingestion error: {exc}"
    except Exception as exc:  # noqa: BLE001 -- 摄入脚本需汇总任意失败
        return False, f"unexpected error: {exc}"

    action = response.ingestion_action
    marker = "↻ replaced" if response.replaced_existing else f"✓ {action}"
    msg = (
        f"{marker}: {path.name} "
        f"| chunks={response.chunk_count} "
        f"| doc_id={response.document_id} "
        f"| trace={response.trace_id}"
    )
    return True, msg


def _collect_files(path: Path, recursive: bool, extensions: list[str]) -> list[Path]:
    """Collect candidate files from a file or directory path."""
    ext_set = {ext.lower() for ext in extensions}
    if path.is_file():
        return [path] if path.suffix.lower() in ext_set else []
    if not path.is_dir():
        return []
    pattern = "**/*" if recursive else "*"
    return sorted(
        p for p in path.glob(pattern) if p.is_file() and p.suffix.lower() in ext_set
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Quick-ingest a file or directory into the RAG-MCP knowledge base."
    )
    parser.add_argument(
        "--path", required=True, help="文件或目录路径（目录默认非递归）"
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="目录递归摄入所有子目录中的文档",
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="强制重建已存在文档的索引（替换式）",
    )
    args = parser.parse_args()

    target = Path(args.path).expanduser().resolve()
    if not target.exists():
        print(f"[error] 路径不存在: {target}", file=sys.stderr)
        return 2

    container = get_container()
    extensions = container.settings.ingestion.supported_extensions
    files = _collect_files(target, args.recursive, extensions)

    if not files:
        print(
            f"[warn] 未找到可摄入的文件。支持扩展名: {extensions}。路径: {target}",
            file=sys.stderr,
        )
        return 1

    print(f"[info] 发现 {len(files)} 个文件待摄入，扩展名: {extensions}")
    start = time.perf_counter()
    succeeded = 0
    failed = 0
    for idx, file_path in enumerate(files, start=1):
        ok, msg = _ingest_one(file_path, args.force_rebuild)
        prefix = f"[{idx}/{len(files)}]"
        if ok:
            succeeded += 1
            print(f"{prefix} {msg}")
        else:
            failed += 1
            print(f"{prefix} ✗ {file_path.name} -- {msg}", file=sys.stderr)

    elapsed = time.perf_counter() - start
    print(
        f"\n[done] 成功 {succeeded} | 失败 {failed} | 耗时 {elapsed:.1f}s",
    )

    # 释放容器持有的向量库等资源
    reset_container()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
