import os
import yaml
from typing import List, Optional
from pydantic import BaseModel, Field

class RepoConfig(BaseModel):
    repo_id: str
    branch: Optional[str] = "main"
    local_path: Optional[str] = None  # If already cloned/local
    url: Optional[str] = None

class GitHubConfig(BaseModel):
    auth_token_env: str = "GITHUB_PAT"
    token: Optional[str] = None
    api_endpoint: str = "https://api.github.com"

class LLMConfig(BaseModel):
    provider: str = "ollama"  # ollama | vllm | lmstudio | openai-compatible | nats
    endpoint: str = "http://localhost:11434/v1"
    model: str = "qwen2.5-coder:7b"
    context_window_tokens: int = 128000
    temperature: float = 0.2
    nats_user: Optional[str] = None
    nats_password: Optional[str] = None

class EmbeddingConfig(BaseModel):
    provider: str = "ollama"
    model: str = "nomic-embed-text"
    endpoint: str = "http://localhost:11434/v1"

class VectorStoreConfig(BaseModel):
    backend: str = "sqlite"  # sqlite | json
    path: str = "./.codedoc/vector_store"

class AnalysisConfig(BaseModel):
    ignore_paths: List[str] = Field(default_factory=lambda: [".git", "node_modules", "dist", "build", "__pycache__", "venv"])
    module_granularity: str = "directory"  # directory | top_level_package
    call_graph_traversal_depth: int = 5

class OutputConfig(BaseModel):
    formats: List[str] = Field(default_factory=lambda: ["markdown"])
    output_dir: str = "./docs/codedoc"

class GeneratorConfig(BaseModel):
    repos: List[RepoConfig] = Field(default_factory=list)
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)

    @classmethod
    def load_from_yaml(cls, path: str) -> "GeneratorConfig":
        if not os.path.exists(path):
            return cls()
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        return cls(**data)

    def save_to_yaml(self, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            yaml.safe_dump(self.model_dump(), f, default_flow_style=False)
