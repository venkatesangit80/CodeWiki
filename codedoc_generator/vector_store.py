import json
import sqlite3
import math
import os
import logging
import requests
from typing import Dict, List, Any, Tuple, Optional

logger = logging.getLogger(__name__)

class VectorRecord:
    def __init__(self, record_id: str, repo_id: str, file_path: str, metadata: Dict[str, Any], chunk_text: str, embedding: List[float]):
        self.id = record_id
        self.repo_id = repo_id
        self.file_path = file_path
        self.metadata = metadata
        self.chunk_text = chunk_text
        self.embedding = embedding

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if len(v1) != len(v2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)

class LocalVectorStore:
    def __init__(self, db_path: str, embedding_provider: str, embedding_model: str, embedding_endpoint: str):
        self.db_path = db_path
        self.provider = embedding_provider
        self.model = embedding_model
        self.endpoint = embedding_endpoint
        
        if db_path == ":memory:":
            self.conn = sqlite3.connect(":memory:")
            self._init_db_conn(self.conn)
        else:
            self.conn = None
            # Ensure parent directories exist
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
            self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        self._init_db_conn(conn)
        conn.close()

    def _init_db_conn(self, conn):
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vectors (
                id TEXT PRIMARY KEY,
                repo_id TEXT,
                file_path TEXT,
                metadata TEXT,
                chunk_text TEXT,
                embedding TEXT
            )
        """)
        # Index on repo_id and file_path for fast pre-filtering
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_repo ON vectors (repo_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_filepath ON vectors (file_path)")
        conn.commit()

    def _get_connection(self) -> Tuple[sqlite3.Connection, bool]:
        if self.db_path == ":memory:":
            return self.conn, False
        return sqlite3.connect(self.db_path), True

    def __del__(self):
        if getattr(self, "conn", None) is not None:
            try:
                self.conn.close()
            except Exception:
                pass

    def get_embedding(self, text: str) -> List[float]:
        if getattr(self, "provider", "").lower() in ("mock", "in-memory", "none"):
            return []
        try:
            # Clean up the URL format
            url = self.endpoint.rstrip("/")
            if not url.endswith("/embeddings"):
                url = f"{url}/embeddings"
                
            headers = {"Content-Type": "application/json"}
            payload = {
                "model": self.model,
                "input": [text]
            }
            
            # Simple API call to local server
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            res_data = response.json()
            
            # Parse OpenAI/Ollama compatible output
            if "data" in res_data and len(res_data["data"]) > 0:
                return res_data["data"][0]["embedding"]
            elif "embedding" in res_data:
                # Ollama legacy /api/embeddings response format
                return res_data["embedding"]
            else:
                logger.error(f"Invalid embedding response format: {res_data}")
                return []
        except Exception as e:
            logger.error(f"Error calling embedding model at {self.endpoint}: {e}")
            return []

    def upsert(self, record_id: str, repo_id: str, file_path: str, metadata: Dict[str, Any], chunk_text: str):
        embedding = self.get_embedding(chunk_text)
        if not embedding:
            logger.warning(f"Could not generate embedding for {record_id}, saving dummy zero vector")
            embedding = [0.0] * 384  # standard fallback dimension
            
        conn, should_close = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO vectors (id, repo_id, file_path, metadata, chunk_text, embedding) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record_id,
                    repo_id,
                    file_path,
                    json.dumps(metadata),
                    chunk_text,
                    json.dumps(embedding)
                )
            )
            conn.commit()
        finally:
            if should_close:
                conn.close()

    def delete_by_filepath(self, repo_id: str, file_path: str):
        conn, should_close = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM vectors WHERE repo_id = ? AND file_path = ?", (repo_id, file_path))
            conn.commit()
        finally:
            if should_close:
                conn.close()

    def delete_by_repo(self, repo_id: str):
        conn, should_close = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM vectors WHERE repo_id = ?", (repo_id,))
            conn.commit()
        finally:
            if should_close:
                conn.close()

    def retrieve(self, query: str, filters: Dict[str, Any], top_k: int = 10) -> List[Tuple[VectorRecord, float]]:
        """
        Retrieves matching chunks based on query similarity.
        Filters can contain: repo_id, file_path_prefix, etc.
        """
        # If query is empty, just fetch all matching records without embeddings
        if not query:
            conn, should_close = self._get_connection()
            try:
                cursor = conn.cursor()
                sql = "SELECT id, repo_id, file_path, metadata, chunk_text, embedding FROM vectors WHERE 1=1"
                params = []
                if "repo_id" in filters:
                    sql += " AND repo_id = ?"
                    params.append(filters["repo_id"])
                cursor.execute(sql, params)
                rows = cursor.fetchall()
            finally:
                if should_close:
                    conn.close()
            
            results = []
            for row in rows:
                rec_id, repo_id, file_path, meta_str, chunk_text, emb_str = row
                metadata = json.loads(meta_str)
                if "file_path_prefix" in filters:
                    if not file_path.startswith(filters["file_path_prefix"]):
                        continue
                record = VectorRecord(rec_id, repo_id, file_path, metadata, chunk_text, [])
                results.append((record, 1.0))
            return results[:top_k]

        query_vector = self.get_embedding(query)
        if not query_vector:
            logger.warning("Could not compute embedding for search query, falling back to SQLite keyword search")
            conn, should_close = self._get_connection()
            try:
                cursor = conn.cursor()
                sql = "SELECT id, repo_id, file_path, metadata, chunk_text, embedding FROM vectors WHERE 1=1"
                params = []
                if "repo_id" in filters:
                    sql += " AND repo_id = ?"
                    params.append(filters["repo_id"])
                
                # Add LIKE conditions for words in query
                words = [w.strip().replace("'", "").replace('"', '') for w in query.split() if len(w.strip()) > 2]
                if words:
                    like_clauses = " AND (" + " OR ".join("chunk_text LIKE ?" for _ in words) + ")"
                    sql += like_clauses
                    for w in words:
                        params.append(f"%{w}%")
                        
                cursor.execute(sql, params)
                rows = cursor.fetchall()
            finally:
                if should_close:
                    conn.close()
            
            results = []
            for row in rows:
                rec_id, repo_id, file_path, meta_str, chunk_text, emb_str = row
                metadata = json.loads(meta_str)
                if "file_path_prefix" in filters:
                    if not file_path.startswith(filters["file_path_prefix"]):
                        continue
                
                # Calculate simple keyword overlap relevance score
                text_lower = chunk_text.lower()
                score = sum(1.0 for w in words if w.lower() in text_lower)
                
                record = VectorRecord(rec_id, repo_id, file_path, metadata, chunk_text, [])
                results.append((record, score))
                
            # Sort by relevance score in descending order
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]

        conn, should_close = self._get_connection()
        try:
            cursor = conn.cursor()

            # Build SQL query based on filters
            sql = "SELECT id, repo_id, file_path, metadata, chunk_text, embedding FROM vectors WHERE 1=1"
            params = []
            if "repo_id" in filters:
                sql += " AND repo_id = ?"
                params.append(filters["repo_id"])
            
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        finally:
            if should_close:
                conn.close()

        results: List[Tuple[VectorRecord, float]] = []
        for row in rows:
            rec_id, repo_id, file_path, meta_str, chunk_text, emb_str = row
            metadata = json.loads(meta_str)
            
            # Apply dynamic filters not easily done in simple SQL (like file path prefix)
            if "file_path_prefix" in filters:
                if not file_path.startswith(filters["file_path_prefix"]):
                    continue
            
            embedding = json.loads(emb_str)
            similarity = cosine_similarity(query_vector, embedding)
            
            record = VectorRecord(
                record_id=rec_id,
                repo_id=repo_id,
                file_path=file_path,
                metadata=metadata,
                chunk_text=chunk_text,
                embedding=embedding
            )
            results.append((record, similarity))

        # Sort by similarity descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
