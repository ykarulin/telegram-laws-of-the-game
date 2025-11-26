"""Tests for LLM integration module."""
import pytest
from unittest.mock import MagicMock, patch
from src.core.llm import LLMClient, SYSTEM_PROMPT, get_system_prompt
from src.constants import TelegramLimits
from src.exceptions import LLMError


class TestLLMClient:
    """Test LLMClient class."""

    def test_initialization(self):
        """Test LLMClient initialization."""
        with patch("src.core.llm.OpenAI"):
            client = LLMClient(
                api_key="test-key",
                model="gpt-4-turbo",
                max_tokens=4096,
            )

            assert client.model == "gpt-4-turbo"
            assert client.max_tokens == 4096

    def test_generate_response_success(self):
        """Test successful response generation."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "What is offside?"

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            response = client.generate_response("What is offside?")

            assert response == "What is offside?"
            assert client.client.chat.completions.create.called

    def test_generate_response_truncates_to_telegram_limit(self):
        """Test response truncation to Telegram message limit."""
        long_response = "x" * (TelegramLimits.MAX_MESSAGE_LENGTH + 100)
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = long_response

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            response = client.generate_response("Test")

            assert len(response) <= TelegramLimits.MAX_MESSAGE_LENGTH
            assert response.endswith("...")

    def test_generate_response_with_whitespace(self):
        """Test response with surrounding whitespace is stripped."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "  Response text  \n"

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            response = client.generate_response("Test")

            assert response == "Response text"

    def test_generate_response_handles_rate_limit_error(self):
        """Test handling of rate limit errors."""
        from openai import RateLimitError

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.chat.completions.create.side_effect = RateLimitError(
            "Rate limit exceeded", response=mock_response, body={"error": "rate_limit"}
        )

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client

            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            with pytest.raises(LLMError, match="Rate limit exceeded"):
                client.generate_response("Test")

    def test_generate_response_handles_api_connection_error(self):
        """Test handling of API connection errors."""
        from openai import APIConnectionError

        mock_client = MagicMock()
        mock_request = MagicMock()
        mock_client.chat.completions.create.side_effect = APIConnectionError(
            message="Connection failed", request=mock_request
        )

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client

            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            with pytest.raises(LLMError, match="Failed to connect"):
                client.generate_response("Test")

    def test_generate_response_handles_api_error(self):
        """Test handling of general API errors."""
        from openai import APIError

        mock_client = MagicMock()
        mock_request = MagicMock()
        mock_client.chat.completions.create.side_effect = APIError(
            "API error", request=mock_request, body={"error": "api_error"}
        )

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client

            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            with pytest.raises(LLMError, match="OpenAI API error"):
                client.generate_response("Test")

    def test_generate_response_retries_with_max_completion_tokens(self):
        """Test that max_tokens is retried with max_completion_tokens if needed."""
        from openai import APIError

        mock_client = MagicMock()
        mock_request = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "This is a test response."

        # First call fails with max_tokens error, second call succeeds
        mock_client.chat.completions.create.side_effect = [
            APIError(
                "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.",
                request=mock_request,
                body={"error": "unsupported_parameter"},
            ),
            mock_response,
        ]

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client

            client = LLMClient("test-key", "gpt-5-mini", 4096)
            client.client = mock_client

            response = client.generate_response("Test")

            assert response == "This is a test response."
            # Should have been called twice: once with max_tokens, once with max_completion_tokens
            assert mock_client.chat.completions.create.call_count == 2

    def test_generate_response_handles_unexpected_error(self):
        """Test handling of unexpected errors."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Unexpected error")

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client

            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            with pytest.raises(LLMError, match="unexpected error"):
                client.generate_response("Test")

    def test_generate_response_with_conversation_context(self):
        """Test response generation with conversation context."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Passive offside means..."

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            # Build conversation context
            conversation_context = [
                {"role": "user", "content": "What is offside?"},
                {"role": "assistant", "content": "Offside is when a player is ahead..."},
                {"role": "user", "content": "What about passive offside?"},
                {"role": "assistant", "content": "Passive offside occurs when..."},
            ]

            response = client.generate_response(
                "Can you elaborate?", conversation_context=conversation_context
            )

            assert response == "Passive offside means..."

            # Verify the API was called with the context
            call_args = mock_client.chat.completions.create.call_args
            messages = call_args.kwargs["messages"]

            # Should have: system + 4 context messages + 1 current user message
            assert len(messages) == 6
            assert messages[0]["role"] == "system"
            assert messages[1]["role"] == "user"
            assert messages[1]["content"] == "What is offside?"
            assert messages[-1]["role"] == "user"
            assert messages[-1]["content"] == "Can you elaborate?"

    def test_generate_response_without_conversation_context(self):
        """Test response generation without conversation context."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Offside is..."

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            response = client.generate_response("What is offside?", conversation_context=None)

            assert response == "Offside is..."

            # Verify the API was called with only system + user message
            call_args = mock_client.chat.completions.create.call_args
            messages = call_args.kwargs["messages"]

            assert len(messages) == 2
            assert messages[0]["role"] == "system"
            assert messages[1]["role"] == "user"

    def test_generate_response_empty_conversation_context(self):
        """Test response generation with empty conversation context list."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Offside is..."

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            # Empty list should be treated same as None
            response = client.generate_response(
                "What is offside?", conversation_context=[]
            )

            assert response == "Offside is..."

            # Verify the API was called with only system + user message
            call_args = mock_client.chat.completions.create.call_args
            messages = call_args.kwargs["messages"]

            assert len(messages) == 2

    def test_count_tokens_estimate(self):
        """Test token count estimation."""
        with patch("src.core.llm.OpenAI"):
            client = LLMClient("test-key", "gpt-4-turbo", 4096)

            # Rough estimate: 4 chars per token
            text = "Hello world!"  # 12 chars
            estimated_tokens = client.count_tokens_estimate(text)

            assert estimated_tokens == 3

    def test_system_prompt_is_defined(self):
        """Test that system prompt is properly defined."""
        assert SYSTEM_PROMPT is not None
        assert "football" in SYSTEM_PROMPT.lower() or "rules" in SYSTEM_PROMPT.lower()

    def test_telegram_message_limit_is_correct(self):
        """Test that Telegram message limit is set correctly."""
        assert TelegramLimits.MAX_MESSAGE_LENGTH == 4096
