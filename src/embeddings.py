"""OpenAI Embeddings API client wrapper."""

from openai import OpenAI


class EmbeddingClient:
    """Thin wrapper around OpenAI Embeddings API.

    Mirrors LLMClient pattern: thin, no business logic, easily mockable.
    Passes task_type via extra_body for Gemini embedding models only.
    """

    def __init__(
        self, api_key: str, model: str, base_url: str | None = None, dimensions: int | None = None
    ) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._dimensions = dimensions

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
        if not texts:
            return []
        kwargs = {"input": texts, "model": self._model}
        if self._dimensions is not None:
            kwargs["dimensions"] = self._dimensions
        if "gemini" in self._model.lower():
            kwargs["extra_body"] = {"task_type": "SEMANTIC_SIMILARITY"}
        response = self._client.embeddings.create(**kwargs)
        return [item.embedding for item in response.data]
