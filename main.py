import os
import time
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from prisma import Prisma
from dotenv import load_dotenv

from models import (
    VectorStoreCreateRequest,
    VectorStoreResponse,
    VectorStoreSearchRequest,
    VectorStoreSearchResponse,
    SearchResult,
    EmbeddingCreateRequest,
    EmbeddingResponse,
    EmbeddingBatchCreateRequest,
    EmbeddingBatchCreateResponse,
    VectorStoreListResponse,
    ContentChunk,
)
from config import settings
from embedding_service import embedding_service

load_dotenv()

app = FastAPI(
    title="OpenAI Vector Stores API",
    description="OpenAI-compatible Vector Stores API using PGVector",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = Prisma()
security = HTTPBearer()


async def get_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    expected_key = settings.server_api_key
    if credentials.credentials != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return credentials.credentials


@app.on_event("startup")
async def startup():
    await db.connect()


@app.on_event("shutdown")
async def shutdown():
    await db.disconnect()


async def generate_query_embedding(query: str) -> List[float]:
    return await embedding_service.generate_embedding(query)


# -----------------------------
# Vector Stores
# -----------------------------
@app.post("/v1/vector_stores", response_model=VectorStoreResponse)
async def create_vector_store(
    request: VectorStoreCreateRequest, api_key: str = Depends(get_api_key)
):
    try:
        table = settings.table_names["vector_stores"]

        res = await db.query_raw(
            f"""
            INSERT INTO {table}
              (id, name, file_counts, status, usage_bytes, expires_after, metadata, created_at)
            VALUES
              (gen_random_uuid(), $1,
               $2, $3, $4, $5, $6, NOW())
            RETURNING
              id AS id,
              name AS name,
              file_counts AS file_counts,
              status AS status,
              usage_bytes AS usage_bytes,
              expires_after AS expires_after,
              EXTRACT(EPOCH FROM expires_at)::bigint AS expires_at_ts,
              EXTRACT(EPOCH FROM last_active_at)::bigint AS last_active_at_ts,
              metadata AS metadata,
              EXTRACT(EPOCH FROM created_at)::bigint AS created_at_ts
            """,
            request.name,
            {"in_progress": 0, "completed": 0, "failed": 0, "cancelled": 0, "total": 0},
            "completed",
            0,
            request.expires_after,
            request.metadata or {},
        )
        if not res:
            raise HTTPException(status_code=500, detail="Failed to create vector store")

        row = res[0]
        return VectorStoreResponse(
            id=row["id"],
            created_at=int(row["created_at_ts"]) if row.get("created_at_ts") is not None else int(time.time()),
            name=row["name"],
            usage_bytes=row["usage_bytes"] or 0,
            file_counts=row["file_counts"]
            or {"in_progress": 0, "completed": 0, "failed": 0, "cancelled": 0, "total": 0},
            status=row["status"],
            expires_after=row["expires_after"],
            expires_at=int(row["expires_at_ts"]) if row.get("expires_at_ts") is not None else None,
            last_active_at=int(row["last_active_at_ts"]) if row.get("last_active_at_ts") is not None else None,
            metadata=row["metadata"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create vector store: {str(e)}")


@app.get("/v1/vector_stores", response_model=VectorStoreListResponse)
async def list_vector_stores(
    limit: Optional[int] = 20,
    after: Optional[str] = None,
    before: Optional[str] = None,
    api_key: str = Depends(get_api_key),
):
    try:
        limit = min(limit or 20, 100)
        table = settings.table_names["vector_stores"]

        base = f"""
        SELECT
          id AS id,
          name AS name,
          file_counts AS file_counts,
          status AS status,
          usage_bytes AS usage_bytes,
          expires_after AS expires_after,
          EXTRACT(EPOCH FROM expires_at)::bigint AS expires_at_ts,
          EXTRACT(EPOCH FROM last_active_at)::bigint AS last_active_at_ts,
          metadata AS metadata,
          EXTRACT(EPOCH FROM created_at)::bigint AS created_at_ts
        FROM {table}
        """

        clauses = []
        params = []
        i = 1
        if after:
            clauses.append(f"id > ${i}")
            params.append(after)
            i += 1
        if before:
            clauses.append(f"id < ${i}")
            params.append(before)
            i += 1
        if clauses:
            base += " WHERE " + " AND ".join(clauses)

        sql = base + f" ORDER BY created_at DESC LIMIT {limit + 1}"
        rows = await db.query_raw(sql, *params)

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        data: List[VectorStoreResponse] = []
        for r in rows:
            data.append(
                VectorStoreResponse(
                    id=r["id"],
                    created_at=int(r["created_at_ts"]) if r.get("created_at_ts") is not None else None,
                    name=r["name"],
                    usage_bytes=r["usage_bytes"] or 0,
                    file_counts=r["file_counts"]
                    or {"in_progress": 0, "completed": 0, "failed": 0, "cancelled": 0, "total": 0},
                    status=r["status"],
                    expires_after=r["expires_after"],
                    expires_at=int(r["expires_at_ts"]) if r.get("expires_at_ts") is not None else None,
                    last_active_at=int(r["last_active_at_ts"]) if r.get("last_active_at_ts") is not None else None,
                    metadata=r["metadata"],
                )
            )

        first_id = data[0].id if data else None
        last_id = data[-1].id if data else None

        return VectorStoreListResponse(data=data, first_id=first_id, last_id=last_id, has_more=has_more)
    except HTTPException:
        raise
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to list vector stores: {str(e)}")


# -----------------------------
# Search
# -----------------------------
@app.post("/v1/vector_stores/{vector_store_id}/search", response_model=VectorStoreSearchResponse)
@app.post("/vector_stores/{vector_store_id}/search", response_model=VectorStoreSearchResponse)
async def search_vector_store(
    vector_store_id: str, request: VectorStoreSearchRequest, api_key: str = Depends(get_api_key)
):
    try:
        vs_table = settings.table_names["vector_stores"]
        found = await db.query_raw(f"SELECT id AS id FROM {vs_table} WHERE id = $1", vector_store_id)
        if not found:
            raise HTTPException(status_code=404, detail="Vector store not found")

        query_embedding = await generate_query_embedding(request.query)
        query_vec = "[" + ",".join(map(str, query_embedding)) + "]"

        limit = min(request.limit or 20, 100)
        fields = settings.db_fields
        emb_table = settings.table_names["embeddings"]

        i = 1
        params = [query_vec, vector_store_id]
        base = f"""
        SELECT
          {fields.id_field} AS id,
          {fields.content_field} AS content,
          {fields.metadata_field} AS metadata,
          ({fields.embedding_field} <=> ${i}::vector) AS distance
        FROM {emb_table}
        WHERE {fields.vector_store_id_field} = ${i + 1}
        """
        i += 2

        filters = []
        if request.filters:
            for k, v in request.filters.items():
                filters.append(f"{fields.metadata_field}->>${i} = ${i + 1}")
                params.extend([k, str(v)])
                i += 2
        if filters:
            base += " AND " + " AND ".join(filters)

        sql = base + f" ORDER BY distance ASC LIMIT {limit}"
        rows = await db.query_raw(sql, *params)

        results: List[SearchResult] = []
        for r in rows:
            similarity = max(0, 1 - (r["distance"] / 2))
            metadata = r["metadata"] or {}
            filename = metadata.get("filename", "document.txt")
            content_chunks = [ContentChunk(type="text", text=r["content"])]
            results.append(
                SearchResult(
                    file_id=r["id"],
                    filename=filename,
                    score=similarity,
                    attributes=metadata if request.return_metadata else None,
                    content=content_chunks,
                )
            )

        return VectorStoreSearchResponse(search_query=request.query, data=results, has_more=False, next_page=None)
    except HTTPException:
        raise
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


# -----------------------------
# Embeddings
# -----------------------------
@app.post("/v1/vector_stores/{vector_store_id}/embeddings", response_model=EmbeddingResponse)
async def create_embedding(
    vector_store_id: str, request: EmbeddingCreateRequest, api_key: str = Depends(get_api_key)
):
    try:
        vs_table = settings.table_names["vector_stores"]
        ok = await db.query_raw(f"SELECT id AS id FROM {vs_table} WHERE id = $1", vector_store_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Vector store not found")

        emb_vec = "[" + ",".join(map(str, request.embedding)) + "]"
        fields = settings.db_fields
        emb_table = settings.table_names["embeddings"]

        res = await db.query_raw(
            f"""
            INSERT INTO {emb_table}
              ({fields.id_field}, {fields.vector_store_id_field}, {fields.content_field},
               {fields.embedding_field}, {fields.metadata_field}, {fields.created_at_field})
            VALUES
              (gen_random_uuid(), $1, $2, $3::vector, $4, NOW())
            RETURNING
              {fields.id_field} AS id,
              {fields.vector_store_id_field} AS vector_store_id,
              {fields.content_field} AS content,
              {fields.metadata_field} AS metadata,
              EXTRACT(EPOCH FROM {fields.created_at_field})::bigint AS created_at_ts
            """,
            vector_store_id,
            request.content,
            emb_vec,
            request.metadata or {},
        )
        if not res:
            raise HTTPException(status_code=500, detail="Failed to create embedding")

        row = res[0]

        # single assignment to file_counts: +1 to completed & total
        await db.query_raw(
            f"""
            UPDATE {vs_table}
            SET file_counts = jsonb_set(
                                jsonb_set(
                                  COALESCE(file_counts, '{{"in_progress": 0, "completed": 0, "failed": 0, "cancelled": 0, "total": 0}}'::jsonb),
                                  '{{completed}}',
                                  to_jsonb(COALESCE(file_counts->>'completed', '0')::int + 1)
                                ),
                                '{{total}}',
                                to_jsonb(COALESCE(file_counts->>'total', '0')::int + 1)
                              ),
                usage_bytes = COALESCE(usage_bytes, 0) + LENGTH($2),
                last_active_at = NOW()
            WHERE id = $1
            """,
            vector_store_id,
            request.content,
        )

        return EmbeddingResponse(
            id=row["id"],
            vector_store_id=row["vector_store_id"],
            content=row["content"],
            metadata=row["metadata"],
            created_at=int(row["created_at_ts"]) if row.get("created_at_ts") is not None else int(time.time()),
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to create embedding: {str(e)}")


@app.post("/v1/vector_stores/{vector_store_id}/embeddings/batch", response_model=EmbeddingBatchCreateResponse)
async def create_embeddings_batch(
    vector_store_id: str, request: EmbeddingBatchCreateRequest, api_key: str = Depends(get_api_key)
):
    try:
        vs_table = settings.table_names["vector_stores"]
        ok = await db.query_raw(f"SELECT id AS id FROM {vs_table} WHERE id = $1", vector_store_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Vector store not found")

        if not request.embeddings:
            raise HTTPException(status_code=400, detail="No embeddings provided")

        fields = settings.db_fields
        emb_table = settings.table_names["embeddings"]

        vals = []
        params = []
        i = 1
        for e in request.embeddings:
            vec = "[" + ",".join(map(str, e.embedding)) + "]"
            vals.append(f"(gen_random_uuid(), ${i}, ${i+1}, ${i+2}::vector, ${i+3}, NOW())")
            params.extend([vector_store_id, e.content, vec, e.metadata or {}])
            i += 4

        res = await db.query_raw(
            f"""
            INSERT INTO {emb_table}
              ({fields.id_field}, {fields.vector_store_id_field}, {fields.content_field},
               {fields.embedding_field}, {fields.metadata_field}, {fields.created_at_field})
            VALUES
              {", ".join(vals)}
            RETURNING
              {fields.id_field} AS id,
              {fields.vector_store_id_field} AS vector_store_id,
              {fields.content_field} AS content,
              {fields.metadata_field} AS metadata,
              EXTRACT(EPOCH FROM {fields.created_at_field})::bigint AS created_at_ts
            """,
            *params,
        )
        if not res:
            raise HTTPException(status_code=500, detail="Failed to create embeddings")

        total_len = sum(len(e.content) for e in request.embeddings)
        batch_size = len(request.embeddings)

        await db.query_raw(
            f"""
            UPDATE {vs_table}
            SET file_counts = jsonb_set(
                                jsonb_set(
                                  COALESCE(file_counts, '{{"in_progress": 0, "completed": 0, "failed": 0, "cancelled": 0, "total": 0}}'::jsonb),
                                  '{{completed}}',
                                  to_jsonb(COALESCE(file_counts->>'completed', '0')::int + $2)
                                ),
                                '{{total}}',
                                to_jsonb(COALESCE(file_counts->>'total', '0')::int + $2)
                              ),
                usage_bytes = COALESCE(usage_bytes, 0) + $3,
                last_active_at = NOW()
            WHERE id = $1
            """,
            vector_store_id,
            batch_size,
            total_len,
        )

        out = [
            EmbeddingResponse(
                id=r["id"],
                vector_store_id=r["vector_store_id"],
                content=r["content"],
                metadata=r["metadata"],
                created_at=int(r["created_at_ts"]) if r.get("created_at_ts") is not None else int(time.time()),
            )
            for r in res
        ]
        return EmbeddingBatchCreateResponse(data=out, created=int(time.time()))
    except HTTPException:
        raise
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to create embeddings batch: {str(e)}")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": int(time.time())}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)

