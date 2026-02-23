"""OpenAI Embeddings API client wrapper."""

from openai import OpenAI


class EmbeddingClient:
    """Thin wrapper around OpenAI Embeddings API.

    Mirrors LLMClient pattern: thin, no business logic, easily mockable.
    Uses extra_body to pass task_type for DeutschlandGPT compatibility.
    """

    def __init__(
        self, api_key: str, model: str, base_url: str | None = None
    ) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    @property
    def model(self) -> str:
        """The embedding model name."""
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors (one per input text).
        """
        response = self._client.embeddings.create(
            input=texts,
            model=self._model,
            extra_body={"task_type": "SEMANTIC_SIMILARITY"},
        )
        return [item.embedding for item in response.data]
