from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    ollama_base_url: str = "http://localhost:11434"
    # qwen2.5:7b-instruct, not the sibling repo's llama3.2:3b - evaluated
    # both live (see DECISIONS.md) since this graph's router/critique/tool
    # loop is more demanding than the sibling's single-tool lookup. Result:
    # llama3.2:3b ignored the order_id present in the question and called
    # search_my_orders instead of get_order_status in both test cases;
    # qwen2.5:7b-instruct extracted it correctly every time. Router accuracy
    # for both models was mediocre with a bare zero-shot prompt (2/3 and
    # 1/3) but qwen2.5:7b-instruct reached 5/5 once the prompt included
    # few-shot examples - a few-shot router prompt is required, not optional.
    ollama_chat_model: str = "qwen2.5:7b-instruct"
    ollama_embed_model: str = "nomic-embed-text"

    order_platform_gateway_url: str = "http://localhost:8080"

    langfuse_host: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""


settings = Settings()  # type: ignore[call-arg]
