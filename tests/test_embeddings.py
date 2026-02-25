"""Tests for src.embeddings."""

from unittest.mock import MagicMock, patch

from src.embeddings import EmbeddingClient


def test_base_url_passed_to_client():
    with patch("src.embeddings.OpenAI") as MockOpenAI:
        EmbeddingClient(
            api_key="test-key",
            model="text-embedding-3-large",
            base_url="https://proxy.example.com/v1",
        )
        MockOpenAI.assert_called_once_with(
            api_key="test-key", base_url="https://proxy.example.com/v1"
        )


def test_base_url_none_by_default():
    with patch("src.embeddings.OpenAI") as MockOpenAI:
        EmbeddingClient(api_key="test-key", model="text-embedding-3-large")
        MockOpenAI.assert_called_once_with(api_key="test-key", base_url=None)


def test_embed_returns_vectors():
    with patch("src.embeddings.OpenAI") as MockOpenAI:
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        mock_emb1 = MagicMock()
        mock_emb1.embedding = [0.1, 0.2, 0.3]
        mock_emb2 = MagicMock()
        mock_emb2.embedding = [0.4, 0.5, 0.6]

        mock_response = MagicMock()
        mock_response.data = [mock_emb1, mock_emb2]
        mock_client.embeddings.create.return_value = mock_response

        client = EmbeddingClient(api_key="test-key", model="text-embedding-3-large")
        result = client.embed(["hello", "world"])

        assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_client.embeddings.create.assert_called_once_with(
            input=["hello", "world"],
            model="text-embedding-3-large",
        )


def test_embed_gemini_sends_task_type():
    with patch("src.embeddings.OpenAI") as MockOpenAI:
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        mock_emb = MagicMock()
        mock_emb.embedding = [0.1, 0.2, 0.3]
        mock_response = MagicMock()
        mock_response.data = [mock_emb]
        mock_client.embeddings.create.return_value = mock_response

        client = EmbeddingClient(api_key="test-key", model="gemini-embedding-001")
        client.embed(["hello"])

        mock_client.embeddings.create.assert_called_once_with(
            input=["hello"],
            model="gemini-embedding-001",
            extra_body={"task_type": "SEMANTIC_SIMILARITY"},
        )


def test_model_property():
    with patch("src.embeddings.OpenAI"):
        client = EmbeddingClient(api_key="test-key", model="custom-embed")
        assert client.model == "custom-embed"
