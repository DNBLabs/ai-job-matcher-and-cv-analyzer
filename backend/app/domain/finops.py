"""FinOps helpers for estimating OpenAI token costs without logging PII."""

# GPT-4o-mini list pricing (USD per 1M tokens) used for planning estimates.
# Source: https://openai.com/api/pricing/ (captured during Task 9 implementation).
_GPT4O_MINI_INPUT_USD_PER_MILLION = 0.15
_GPT4O_MINI_OUTPUT_USD_PER_MILLION = 0.60


def estimate_gpt4o_mini_usd(*, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost for a GPT-4o-mini call from token usage counts.

    Args:
        prompt_tokens: Input tokens reported by the provider.
        completion_tokens: Output tokens reported by the provider.

    Returns:
        float: Rounded estimated USD cost for FinOps audit metadata.
    """
    input_cost = (prompt_tokens / 1_000_000) * _GPT4O_MINI_INPUT_USD_PER_MILLION
    output_cost = (completion_tokens / 1_000_000) * _GPT4O_MINI_OUTPUT_USD_PER_MILLION
    return round(input_cost + output_cost, 6)
