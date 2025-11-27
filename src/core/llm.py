"""LLM integration module for OpenAI API."""
import logging
from datetime import datetime, timezone
from openai import OpenAI, APIError, RateLimitError, APIConnectionError
from src.exceptions import LLMError
from src.constants import TelegramLimits

logger = logging.getLogger(__name__)


def get_system_prompt() -> str:
    """Get the system prompt with current date and time in GMT/UTC.

    Returns:
        System prompt string with current GMT datetime information.
    """
    current_datetime = datetime.now(timezone.utc).strftime("%A, %B %d, %Y at %I:%M %p GMT")
    return f"""You are an expert in football (soccer) rules.
Current date and time (GMT): {current_datetime}

GUIDELINES:
- Only answer questions about football (soccer) rules, laws of the game, VAR procedures, and related regulations.
- Reject off-topic questions politely without offering to help with non-football topics.
- Answer questions clearly and accurately based on the Laws of the Game.
- Keep responses concise and informative.
- If you're unsure about a rule, say so explicitly.
- Do NOT end your response by prompting the user for follow-up questions or asking for scenarios.
- Do NOT invite the user to provide additional details or examples.
- Do NOT add closing statements that invite further interaction, such as "If you need..." or "Feel free to ask..." or similar phrases in any language.
- End your response with the answer itself. No additional invitations or prompts should follow your main content."""


def get_system_prompt_with_document_selection(
    document_list: str = "",
    max_lookups: int = 5,
    max_chunks: int = 5,
    similarity_threshold: float = 0.7,
) -> str:
    """Get the system prompt with document selection tool instructions.

    This prompt variant enables the LLM to use the lookup_documents tool
    to select and search specific documents from the knowledge base.

    Args:
        document_list: Formatted list of available documents (one per line, numbered)
        max_lookups: Maximum number of tool calls allowed per request
        max_chunks: Maximum chunks per lookup call
        similarity_threshold: Default minimum similarity threshold for searches

    Returns:
        System prompt string with tool instructions

    Examples:
        >>> prompt = get_system_prompt_with_document_selection(
        ...     document_list="1. Laws of Game 2024-25\n2. VAR Guidelines",
        ...     max_lookups=5,
        ...     max_chunks=5
        ... )
        >>> "lookup_documents" in prompt
        True
    """
    current_datetime = datetime.now(timezone.utc).strftime("%A, %B %d, %Y at %I:%M %p GMT")

    base_guidelines = """You are an expert in football (soccer) rules.
Current date and time (GMT): {datetime}

CORE GUIDELINES:
- Only answer questions about football (soccer) rules, laws of the game, VAR procedures, and related regulations.
- Reject off-topic questions politely without offering to help with non-football topics.
- Answer questions clearly and accurately based on the Laws of the Game.
- Keep responses concise and informative.
- If you're unsure about a rule, say so explicitly.
- Do NOT end your response by prompting the user for follow-up questions or asking for scenarios.
- Do NOT invite the user to provide additional details or examples.
- Do NOT add closing statements that invite further interaction, such as "If you need..." or "Feel free to ask..." or similar phrases in any language.
- End your response with the answer itself. No additional invitations or prompts should follow your main content.

DOCUMENT SELECTION AND LOOKUP:
You have access to the following documents in the knowledge base:

{documents}

USING THE LOOKUP TOOL:
Use the "lookup_documents" tool to search for relevant information in specific documents.
This tool lets you search within documents you select, rather than doing a general search.

Tool parameters:
- document_names: List of document names to search (from the list above)
- query: Your search query (e.g., "offside rule", "handball definition")
- top_k: Number of results to return (1 to {max_chunks}, default: 3)
- min_similarity: Minimum relevance score, 0.0-1.0 (default: {similarity_threshold})

Guidelines for tool use:
- Identify which documents are most relevant to the user's question
- Use the tool to search only those documents
- You can use the tool up to {max_lookups} times per request to search different documents
- If you use the tool and find relevant information, use it in your answer
- If you don't use the tool, the system will fall back to searching all documents

Example tool usage:
If asked "What is the offside rule?", you might:
1. Use the tool to search "Laws of Game 2024-25" for "offside"
2. Get back relevant sections from Law 11
3. Use those sections to answer the question accurately"""

    return base_guidelines.format(
        datetime=current_datetime,
        documents=document_list if document_list else "[No documents available]",
        max_chunks=max_chunks,
        max_lookups=max_lookups,
        similarity_threshold=similarity_threshold,
    )


# Default system prompt (for backward compatibility with tests)
SYSTEM_PROMPT = get_system_prompt()


class LLMClient:
    """OpenAI LLM client for generating responses."""

    # Models that use max_completion_tokens instead of max_tokens
    # Includes gpt-4o and newer models, and experimental models like gpt-5-mini
    MODELS_WITH_COMPLETION_TOKENS = {
        "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo",
        "gpt-5", "gpt-5-mini", "o1", "o1-mini", "o3", "o3-mini"
    }

    def __init__(self, api_key: str, model: str, max_tokens: int, temperature: float = 0.7):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key
            model: Model name (e.g., 'gpt-4-turbo')
            max_tokens: Maximum tokens for responses
            temperature: Temperature for response generation (0.0-2.0, default 0.7)
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        # Check if this model requires max_completion_tokens
        self.use_completion_tokens = any(model.startswith(m) for m in self.MODELS_WITH_COMPLETION_TOKENS)
        logger.info(f"LLM initialized with model: {self.model}, temperature: {self.temperature}")

    def generate_response(self, user_message: str, conversation_context: list = None) -> str:
        """Generate a response using OpenAI API.

        Args:
            user_message: The user's input message
            conversation_context: Optional list of previous messages in conversation.
                                 Each item should be a dict with 'role' and 'content' keys.
                                 Will be inserted between system prompt and current user message.

        Returns:
            Generated response text, truncated to Telegram limit if necessary

        Raises:
            ValueError: If response generation fails
        """
        try:
            logger.debug(f"Generating response for: {user_message[:50]}...")

            # Build the messages list with current datetime in system prompt
            messages = [{"role": "system", "content": get_system_prompt()}]

            # Add conversation context if provided
            if conversation_context:
                messages.extend(conversation_context)
                logger.debug(f"Using conversation context with {len(conversation_context)} messages")

            # Add current user message
            messages.append({"role": "user", "content": user_message})

            # Build the request parameters
            request_params = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
            }

            # Use the correct parameter name based on model
            if self.use_completion_tokens:
                request_params["max_completion_tokens"] = self.max_tokens
            else:
                request_params["max_tokens"] = self.max_tokens

            try:
                response = self.client.chat.completions.create(**request_params)
            except APIError as e:
                # If we get an error about max_tokens vs max_completion_tokens, retry with the other parameter
                error_str = str(e)
                if "max_tokens" in error_str and "max_completion_tokens" in error_str:
                    logger.debug(
                        f"Model {self.model} parameter mismatch, retrying with alternate parameter..."
                    )
                    # Swap the parameter and retry
                    if "max_tokens" in request_params:
                        del request_params["max_tokens"]
                        request_params["max_completion_tokens"] = self.max_tokens
                    else:
                        del request_params["max_completion_tokens"]
                        request_params["max_tokens"] = self.max_tokens
                    response = self.client.chat.completions.create(**request_params)
                else:
                    # Log the error details for debugging
                    logger.error(f"OpenAI API error: {error_str}")
                    logger.debug(f"Request params: model={request_params.get('model')}, messages count={len(request_params.get('messages', []))}")
                    # Re-raise if it's a different error
                    raise

            # Extract the response text
            reply_text = response.choices[0].message.content.strip()
            logger.debug(f"Generated response ({len(reply_text)} chars)")

            # Truncate to Telegram message limit
            if len(reply_text) > TelegramLimits.MAX_MESSAGE_LENGTH:
                logger.warning(
                    f"Response truncated from {len(reply_text)} to {TelegramLimits.MAX_MESSAGE_LENGTH} chars"
                )
                reply_text = reply_text[: TelegramLimits.MAX_MESSAGE_LENGTH - 3] + "..."

            return reply_text

        except RateLimitError:
            logger.error("Rate limit exceeded. Please try again later.")
            raise LLMError("Rate limit exceeded. Please try again later.")
        except APIConnectionError as e:
            logger.error(f"OpenAI API connection error: {e}")
            raise LLMError("Failed to connect to OpenAI API. Please try again later.")
        except APIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise LLMError(f"OpenAI API error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during LLM generation: {e}")
            raise LLMError("An unexpected error occurred. Please try again later.")

    def count_tokens_estimate(self, text: str) -> int:
        """Estimate token count (rough approximation).

        OpenAI models typically use ~4 characters per token on average.

        Args:
            text: Text to estimate tokens for

        Returns:
            Estimated token count
        """
        return len(text) // 4
