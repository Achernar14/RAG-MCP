#!/usr/bin/env python3
"""One-time migration: ChromaDB → Weaviate Embedded.

Usage:
    cd backend
    python ../scripts/migrate_chroma_to_weaviate.py \
        --chroma-path ../data/vector_store/chroma_live \
        --chroma-collection rag_mcp_live \
        --weaviate-data-path ../data/vector_store/weaviate \
        --weaviate-collection RAG_MCP
"""

from __future__ import annotations

import argparse
from pathlib import Path
from uuid import NAMESPACE_DNS, uuid5

import chromadb
import weaviate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances
from weaviate.embedded import EmbeddedOptions


def migrate(args: argparse.Namespace) -> None:
    # --- 源: ChromaDB ---
    chroma = chromadb.PersistentClient(path=args.chroma_path)
    src = chroma.get_or_create_collection(args.chroma_collection)
    all_ids = src.get(include=[])["ids"]
    if not all_ids:
        print("ChromaDB collection 为空，无需迁移。")
        return

    print(f"ChromaDB 中发现 {len(all_ids)} 条记录")

    batch_size = 200
    records: list[dict] = []
    for i in range(0, len(all_ids), batch_size):
        batch_ids = all_ids[i : i + batch_size]
        result = src.get(
            ids=batch_ids,
            include=["documents", "embeddings", "metadatas"],
        )
        for j in range(len(result["ids"])):
            records.append({
                "id": result["ids"][j],
                "text": result["documents"][j],
                "vector": result["embeddings"][j],
                "metadata": result["metadatas"][j],
            })

    # --- 目标: Weaviate Embedded ---
    data_dir = Path(args.weaviate_data_path)
    data_dir.mkdir(parents=True, exist_ok=True)

    client = weaviate.WeaviateClient(
        embedded_options=EmbeddedOptions(
            persistence_data_path=str(data_dir),
            version="1.37.2",
            hostname="127.0.0.1",
            port=8079,
            additional_env_vars={"LOG_LEVEL": "error"},
        ),
    )
    client.connect()

    if not client.collections.exists(args.weaviate_collection):
        client.collections.create(
            name=args.weaviate_collection,
            vector_config=Configure.Vectors.self_provided(
                vector_index_config=Configure.VectorIndex.hnsw(
                    distance_metric=VectorDistances.COSINE,
                ),
            ),
            properties=[
                Property(name="text", data_type=DataType.TEXT),
                Property(name="document_id", data_type=DataType.TEXT),
                Property(name="chunk_index", data_type=DataType.INT),
            ],
        )

    collection = client.collections.use(args.weaviate_collection)

    with collection.batch.fixed_size(batch_size=200) as batch:
        for rec in records:
            meta = rec["metadata"] or {}
            batch.add_object(
                properties={
                    "text": rec["text"] or "",
                    "document_id": meta.get("document_id", ""),
                    "chunk_index": int(meta.get("chunk_index", 0)),
                },
                vector=rec["vector"],
                uuid=str(uuid5(NAMESPACE_DNS, rec["id"])),
            )

    failed = collection.batch.failed_objects
    if failed:
        print(f"WARNING: {len(failed)} 条记录写入失败")
        for f in failed[:5]:
            print(f"  - {f.message}")
    else:
        print(f"成功迁移 {len(records)} 条记录到 Weaviate")

    client.close()
    chroma.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate data from ChromaDB to Weaviate Embedded")
    parser.add_argument("--chroma-path", required=True, help="ChromaDB persistence directory")
    parser.add_argument("--chroma-collection", default="rag_mcp_live", help="Source collection name")
    parser.add_argument("--weaviate-data-path", required=True, help="Weaviate data directory")
    parser.add_argument("--weaviate-collection", default="RAG_MCP", help="Target collection name")
    migrate(parser.parse_args())
