OPENAI_COMPATIBLE_MAX_TOKENS = 393_216
OPENAI_COMPATIBLE_MIN_TOKENS = 1


def clamp_openai_compatible_max_tokens(max_tokens: int) -> int:
    return max(OPENAI_COMPATIBLE_MIN_TOKENS, min(max_tokens, OPENAI_COMPATIBLE_MAX_TOKENS))
