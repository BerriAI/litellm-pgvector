from typing import Dict, Optional
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class DatabaseFieldConfig(BaseModel):
    """Configuration for database field mappings"""
    id_field: str = "id"
    content_field: str = "content"
    metadata_field: str = "metadata"
    embedding_field: str = "embedding"
    vector_store_id_field: str = "vector_store_id"
    created_at_field: str = "created_at"


class EmbeddingConfig(BaseModel):
    """Configuration for embedding generation via LiteLLM proxy"""
    model: str = "text-embedding-ada-002"
    base_url: str = "http://localhost:4000"  # LiteLLM proxy URL
    api_key: str
    dimensions: int = 1536


class Settings(BaseSettings):
    """Application settings"""
    # Database configuration
    database_url: str = "postgresql://username:password@localhost:5432/vectordb?schema=public"
    
    # API configuration
    server_api_key: str = "your-api-key-here"
    port: int = 8000
    host: str = "0.0.0.0"
    
    # Database field mappings
    db_fields: DatabaseFieldConfig = DatabaseFieldConfig()
    
    # Embedding configuration
    embedding: EmbeddingConfig
    
    class Config:
        env_file = ".env"
        env_nested_delimiter = "__"
        case_sensitive = False
        
        # Allow environment variables like:
        # DB_FIELDS__ID_FIELD=custom_id
        # EMBEDDING__MODEL=text-embedding-3-small
        # EMBEDDING__API_BASE=https://api.openai.com/v1
        
    @property
    def table_names(self) -> Dict[str, str]:
        """Get table names"""
        return {
            "vector_stores": "vector_stores",
            "embeddings": "embeddings"
        }


# Global settings instance
settings = Settings() 