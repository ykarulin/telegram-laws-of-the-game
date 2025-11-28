"""Regression tests for LLM tool calling and agentic loop.

These tests ensure that the tool calling implementation remains robust
against future changes and edge cases.

Regression scenarios covered:
1. NoneType error when model returns tool calls (original issue)
2. Multiple sequential tool calls in one request
3. Tool call with malformed JSON arguments
4. Tool call with missing required parameters
5. Tool executor errors and exception handling
6. Max iterations limit enforcement
7. Invalid model responses (neither content nor tool_calls)
"""

import pytest
import json
from unittest.mock import MagicMock, patch
from src.core.llm import LLMClient
from src.exceptions import LLMError


class TestToolCallingRegression:
    """Regression tests for tool calling functionality."""

    def test_regression_none_type_error_with_tool_calls(self):
        """Regression: Prevent 'NoneType' object has no attribute 'strip' error.

        Original issue: When model returns tool_calls, content is None.
        Calling .strip() on None caused AttributeError.

        This test ensures the fix detects None content and processes tool calls instead.
        """
        mock_client = MagicMock()

        # First response: tool call with None content
        mock_response_tool_call = MagicMock()
        mock_response_tool_call.choices[0].message.content = None
        mock_response_tool_call.choices[0].message.tool_calls = [
            MagicMock(
                id="call_123",
                function=MagicMock(
                    name="lookup_documents",
                    arguments='{"document_names": ["Doc1"], "query": "test"}'
                )
            )
        ]

        # Second response: final answer
        mock_response_final = MagicMock()
        mock_response_final.choices[0].message.content = "Final answer"
        mock_response_final.choices[0].message.tool_calls = None

        mock_client.chat.completions.create.side_effect = [
            mock_response_tool_call,
            mock_response_final,
        ]

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client
            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            def mock_executor(tool_name: str, **kwargs) -> str:
                return "Tool executed"

            # Should NOT raise AttributeError on None.strip()
            response = client.generate_response(
                "Test",
                tools=[{"type": "function", "function": {"name": "lookup_documents"}}],
                tool_executor=mock_executor,
            )

            assert response == "Final answer"
            assert mock_client.chat.completions.create.call_count == 2

    def test_regression_multiple_tool_calls_sequential(self):
        """Regression: Handle multiple tool calls in sequence.

        Ensure the agentic loop can handle multiple tool calls that occur
        across different iterations (call tool1, get results, call tool2, etc).
        """
        mock_client = MagicMock()

        # First response: first tool call
        response_1 = MagicMock()
        response_1.choices[0].message.content = None
        response_1.choices[0].message.tool_calls = [
            MagicMock(
                id="call_1",
                function=MagicMock(
                    name="lookup_documents",
                    arguments='{"document_names": ["Doc1"], "query": "q1"}'
                )
            )
        ]

        # Second response: second tool call
        response_2 = MagicMock()
        response_2.choices[0].message.content = None
        response_2.choices[0].message.tool_calls = [
            MagicMock(
                id="call_2",
                function=MagicMock(
                    name="lookup_documents",
                    arguments='{"document_names": ["Doc2"], "query": "q2"}'
                )
            )
        ]

        # Third response: final answer
        response_3 = MagicMock()
        response_3.choices[0].message.content = "Answer after 2 tool calls"
        response_3.choices[0].message.tool_calls = None

        mock_client.chat.completions.create.side_effect = [
            response_1,
            response_2,
            response_3,
        ]

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client
            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            call_count = 0

            def mock_executor(tool_name: str, **kwargs) -> str:
                nonlocal call_count
                call_count += 1
                return f"Result from tool call {call_count}"

            response = client.generate_response(
                "Test",
                tools=[{"type": "function", "function": {"name": "lookup_documents"}}],
                tool_executor=mock_executor,
            )

            assert response == "Answer after 2 tool calls"
            assert mock_client.chat.completions.create.call_count == 3
            assert call_count == 2  # Tool executor called twice

    def test_regression_malformed_tool_arguments_json(self):
        """Regression: Handle malformed JSON in tool arguments.

        If the model returns invalid JSON in function.arguments,
        the code should handle it gracefully and continue.
        """
        mock_client = MagicMock()

        # First response: tool call with invalid JSON
        response_tool = MagicMock()
        response_tool.choices[0].message.content = None
        response_tool.choices[0].message.tool_calls = [
            MagicMock(
                id="call_bad",
                function=MagicMock(
                    name="lookup_documents",
                    arguments='{"invalid json": }'  # Invalid JSON
                )
            )
        ]

        # Second response: model recovers with final answer
        response_final = MagicMock()
        response_final.choices[0].message.content = "Recovered and answered"
        response_final.choices[0].message.tool_calls = None

        mock_client.chat.completions.create.side_effect = [
            response_tool,
            response_final,
        ]

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client
            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            def mock_executor(tool_name: str, **kwargs) -> str:
                # Should not be called due to JSON parse error
                raise AssertionError("Executor should not be called")

            response = client.generate_response(
                "Test",
                tools=[{"type": "function", "function": {"name": "lookup_documents"}}],
                tool_executor=mock_executor,
            )

            # Should recover and get final answer
            assert response == "Recovered and answered"

    def test_regression_tool_executor_raises_exception(self):
        """Regression: Handle exceptions from tool executor.

        If the tool executor raises an exception, the error should be
        caught and returned as a tool result for the model to handle.
        """
        mock_client = MagicMock()

        # First response: tool call
        response_tool = MagicMock()
        response_tool.choices[0].message.content = None
        response_tool.choices[0].message.tool_calls = [
            MagicMock(
                id="call_error",
                function=MagicMock(
                    name="lookup_documents",
                    arguments='{"document_names": ["Doc1"], "query": "q"}'
                )
            )
        ]

        # Second response: model handles the error
        response_final = MagicMock()
        response_final.choices[0].message.content = "I encountered an error"
        response_final.choices[0].message.tool_calls = None

        mock_client.chat.completions.create.side_effect = [
            response_tool,
            response_final,
        ]

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client
            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            def failing_executor(tool_name: str, **kwargs) -> str:
                raise ValueError("Tool database connection failed")

            response = client.generate_response(
                "Test",
                tools=[{"type": "function", "function": {"name": "lookup_documents"}}],
                tool_executor=failing_executor,
            )

            # Should recover with final answer
            assert response == "I encountered an error"
            # Verify the error was passed to the model
            call_args = mock_client.chat.completions.create.call_args_list[1]
            messages = call_args.kwargs["messages"]
            tool_result = messages[-1]
            assert tool_result["role"] == "tool"
            assert "Tool database connection failed" in tool_result["content"]

    def test_regression_max_iterations_limit(self):
        """Regression: Enforce max_tool_iterations limit.

        If the model keeps making tool calls beyond the limit,
        the loop should stop and raise an error.
        """
        mock_client = MagicMock()

        # Create 11 tool call responses (to exceed default limit of 10)
        responses = []
        for i in range(11):
            response = MagicMock()
            response.choices[0].message.content = None
            response.choices[0].message.tool_calls = [
                MagicMock(
                    id=f"call_{i}",
                    function=MagicMock(
                        name="lookup_documents",
                        arguments='{"document_names": ["Doc"], "query": "q"}'
                    )
                )
            ]
            responses.append(response)

        mock_client.chat.completions.create.side_effect = responses

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client
            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            def mock_executor(tool_name: str, **kwargs) -> str:
                return "Result"

            # Should raise error due to max iterations
            with pytest.raises(LLMError):
                client.generate_response(
                    "Test",
                    tools=[{"type": "function", "function": {"name": "lookup_documents"}}],
                    tool_executor=mock_executor,
                    max_tool_iterations=10,
                )

    def test_regression_custom_max_iterations(self):
        """Regression: Support custom max_tool_iterations parameter.

        Verify that custom iteration limits are respected.
        """
        mock_client = MagicMock()

        # Create 4 tool call responses
        responses = []
        for i in range(4):
            response = MagicMock()
            response.choices[0].message.content = None
            response.choices[0].message.tool_calls = [
                MagicMock(
                    id=f"call_{i}",
                    function=MagicMock(
                        name="lookup_documents",
                        arguments='{"document_names": ["Doc"], "query": "q"}'
                    )
                )
            ]
            responses.append(response)

        mock_client.chat.completions.create.side_effect = responses

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client
            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            def mock_executor(tool_name: str, **kwargs) -> str:
                return "Result"

            # Should raise error with custom limit of 3
            with pytest.raises(LLMError):
                client.generate_response(
                    "Test",
                    tools=[{"type": "function", "function": {"name": "lookup_documents"}}],
                    tool_executor=mock_executor,
                    max_tool_iterations=3,
                )

    def test_regression_invalid_response_neither_content_nor_tools(self):
        """Regression: Handle invalid response with neither content nor tool_calls.

        If the model returns a response with neither content nor tool_calls,
        the code should raise an appropriate error.
        """
        mock_client = MagicMock()

        # Response with neither content nor tool_calls
        invalid_response = MagicMock()
        invalid_response.choices[0].message.content = None
        invalid_response.choices[0].message.tool_calls = None

        mock_client.chat.completions.create.return_value = invalid_response

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client
            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            def mock_executor(tool_name: str, **kwargs) -> str:
                return "Result"

            with pytest.raises(LLMError):
                client.generate_response(
                    "Test",
                    tools=[{"type": "function", "function": {"name": "lookup_documents"}}],
                    tool_executor=mock_executor,
                )

    def test_regression_tool_calls_with_empty_arguments(self):
        """Regression: Handle tool calls with empty argument objects.

        Tool calls with {} as arguments should be handled gracefully.
        """
        mock_client = MagicMock()

        # Tool call with empty arguments
        response_tool = MagicMock()
        response_tool.choices[0].message.content = None
        response_tool.choices[0].message.tool_calls = [
            MagicMock(
                id="call_empty",
                function=MagicMock(
                    name="lookup_documents",
                    arguments='{}'  # Empty object
                )
            )
        ]

        # Final response
        response_final = MagicMock()
        response_final.choices[0].message.content = "Handled empty args"
        response_final.choices[0].message.tool_calls = None

        mock_client.chat.completions.create.side_effect = [
            response_tool,
            response_final,
        ]

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client
            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            def mock_executor(tool_name: str, **kwargs) -> str:
                # Should be called with no keyword arguments
                assert len(kwargs) == 0
                return "Handled"

            response = client.generate_response(
                "Test",
                tools=[{"type": "function", "function": {"name": "lookup_documents"}}],
                tool_executor=mock_executor,
            )

            assert response == "Handled empty args"

    def test_regression_multiple_tool_calls_single_request(self):
        """Regression: Handle multiple tool calls in a single model response.

        Some models might return multiple tool calls at once.
        All should be executed and their results collected.
        """
        mock_client = MagicMock()

        # Response with 3 tool calls at once
        response_tool = MagicMock()
        response_tool.choices[0].message.content = None
        response_tool.choices[0].message.tool_calls = [
            MagicMock(
                id="call_1",
                function=MagicMock(
                    name="lookup_documents",
                    arguments='{"document_names": ["Doc1"], "query": "q1"}'
                )
            ),
            MagicMock(
                id="call_2",
                function=MagicMock(
                    name="lookup_documents",
                    arguments='{"document_names": ["Doc2"], "query": "q2"}'
                )
            ),
            MagicMock(
                id="call_3",
                function=MagicMock(
                    name="lookup_documents",
                    arguments='{"document_names": ["Doc3"], "query": "q3"}'
                )
            ),
        ]

        # Final response
        response_final = MagicMock()
        response_final.choices[0].message.content = "Answered with 3 doc searches"
        response_final.choices[0].message.tool_calls = None

        mock_client.chat.completions.create.side_effect = [
            response_tool,
            response_final,
        ]

        with patch("src.core.llm.OpenAI") as mock_openai:
            mock_openai.return_value = mock_client
            client = LLMClient("test-key", "gpt-4-turbo", 4096)
            client.client = mock_client

            execution_count = 0

            def mock_executor(tool_name: str, **kwargs) -> str:
                nonlocal execution_count
                execution_count += 1
                return f"Doc {execution_count} results"

            response = client.generate_response(
                "Test",
                tools=[{"type": "function", "function": {"name": "lookup_documents"}}],
                tool_executor=mock_executor,
            )

            assert response == "Answered with 3 doc searches"
            assert execution_count == 3  # All 3 tools should have been executed

            # Verify all 3 tool results were added to messages
            call_args = mock_client.chat.completions.create.call_args_list[1]
            messages = call_args.kwargs["messages"]
            tool_results = [m for m in messages if m.get("role") == "tool"]
            assert len(tool_results) == 3
