"""Platform-specific creative guidance for inspiration generation."""

PLATFORM_LABELS: dict[str, str] = {
    "qidian": "起点中文网",
    "jjwxc": "晋江文学城",
    "ao3": "AO3",
    "wattpad": "Wattpad",
}

PLATFORM_STYLE_PROMPTS: dict[str, str] = {
    "qidian": (
        "面向起点中文网读者：突出清晰升级体系、持续正反馈、强开篇钩子与可扩展长线冲突；"
        "如使用金手指，必须说明限制、成长路径和阶段性回报。"
    ),
    "jjwxc": (
        "面向晋江文学城读者：突出人物情感弧线、关系张力、价值选择与细腻叙事；"
        "核心矛盾应同时推动人物关系和个人成长。"
    ),
    "ao3": (
        "面向 AO3 读者：突出角色关系、CP 化学反应、多元表达与明确内容预期；"
        "若涉及同人元素，不得直接挪用受版权保护作品的原文或独占设定。"
    ),
    "wattpad": (
        "面向 Wattpad 读者：突出高概念卖点、短章节悬念、强情绪节奏和国际读者易理解的背景；"
        "首章应快速建立人物目标和关系冲突。"
    ),
}


def get_platform_style_prompt(platform: str | None) -> str:
    """Return deterministic platform guidance without inventing a default platform."""
    if not platform:
        return ""
    return PLATFORM_STYLE_PROMPTS.get(platform.strip().lower(), "")
