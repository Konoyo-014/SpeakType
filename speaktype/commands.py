"""Voice command detection and processing."""

import re

# Structural commands - unambiguous, safe to replace directly
STRUCTURAL_COMMANDS = {
    "new line": "\n",
    "line break": "\n",
    "new paragraph": "\n\n",
    "tab": "\t",
    "换行": "\n",
    "新行": "\n",
    "新段落": "\n\n",
    "下一段": "\n\n",
}

# Punctuation commands - only matched at end of clause to avoid false positives
# These are appended after the preceding text (e.g., "hello period" -> "hello.")
PUNCTUATION_COMMANDS = {
    "period": ".",
    "full stop": ".",
    "comma": ",",
    "question mark": "?",
    "exclamation mark": "!",
    "exclamation point": "!",
    "colon": ":",
    "semicolon": ";",
    "open quote": '"',
    "close quote": '"',
    "句号": "。",
    "逗号": "，",
    "问号": "？",
    "感叹号": "！",
    "冒号": "：",
    "分号": "；",
}

# Edit commands that trigger LLM processing on selected text
EDIT_COMMAND_PATTERNS = [
    # English - these should be the ENTIRE spoken text (anchored to start)
    r"^make (?:this|it) shorter\.?$",
    r"^make (?:this|it) longer\.?$",
    r"^make (?:this|it) (?:more )?formal\.?$",
    r"^make (?:this|it) (?:more )?casual\.?$",
    r"^make (?:this|it) (?:more )?friendly\.?$",
    r"^make (?:this|it) (?:more )?professional\.?$",
    r"^make (?:this|it) (?:sound )?(?:more )?(?:kind|kinder|polite|politer)\.?$",
    r"^change (?:the )?tone to (\w+)\.?$",
    r"^translate (?:this )?(?:to|into) (\w+)\.?$",
    r"^fix (?:the )?(?:grammar|typo|typos|spelling)\.?$",
    r"^clean (?:this )?up\.?$",
    r"^reformat (?:this)?\.?$",
    r"^restructure (?:this)?\.?$",
    r"^summarize (?:this)?\.?$",
    r"^explain (?:this)?\.?$",
    r"^create a (?:punchy )?reply\.?$",
    r"^reply to (?:this)?\.?$",
    # Chinese
    r"^缩短[。]?$",
    r"^扩展[。]?$",
    r"^正式一点[。]?$",
    r"^随意一点[。]?$",
    r"^翻译成(.+)[。]?$",
    r"^修正语法[。]?$",
    r"^整理一下[。]?$",
    r"^总结(?:一下)?[。]?$",
    r"^解释(?:一下)?[。]?$",
    r"^回复[。]?$",
]


def process_punctuation_commands(text: str) -> str:
    """Replace spoken voice commands with their symbols.

    Structural commands (new line, new paragraph) are replaced anywhere.
    Punctuation commands are only replaced when they appear at the end of a
    clause (followed by end-of-string, another punctuation command, or a
    structural command) to avoid false positives like "period of time".
    """
    result = text

    # 1. Replace structural commands (always safe - unambiguous)
    for cmd, symbol in sorted(STRUCTURAL_COMMANDS.items(), key=lambda x: -len(x[0])):
        if cmd.isascii():
            pattern = re.compile(r'\b' + re.escape(cmd) + r'\b', re.IGNORECASE)
        else:
            pattern = re.compile(re.escape(cmd))
        result = pattern.sub(symbol, result)

    # 2. Replace punctuation commands only at end of text or before structural breaks
    for cmd, symbol in sorted(PUNCTUATION_COMMANDS.items(), key=lambda x: -len(x[0])):
        if cmd.isascii():
            # Match "word period" at end-of-string or before newline/tab
            pattern = re.compile(
                r'\b' + re.escape(cmd) + r'(?=\s*(?:$|\n|\t))',
                re.IGNORECASE
            )
        else:
            pattern = re.compile(re.escape(cmd) + r'(?=\s*(?:$|\n|\t))')
        result = pattern.sub(symbol, result)

    # Clean up extra spaces around inserted punctuation
    result = re.sub(r'\s+([.。,，?？!！:：;；])', r'\1', result)

    return result


def detect_edit_command(text: str) -> tuple[bool, str]:
    """Check if the transcribed text is an edit command.
    Returns (is_edit_command, command_text).
    """
    text_lower = text.strip().lower()
    for pattern in EDIT_COMMAND_PATTERNS:
        if re.search(pattern, text_lower):
            return True, text.strip()
    return False, ""


def build_edit_prompt(command: str, selected_text: str, tone: str = "neutral") -> str:
    """Build a prompt for the LLM to process an edit command on selected text."""
    return f"""You are a text editing assistant. The user has selected the following text and given a voice command to modify it.

Selected text:
\"\"\"{selected_text}\"\"\"

Voice command: {command}
Context tone: {tone}

Apply the user's command to the selected text. Return ONLY the modified text, nothing else. No explanations, no quotes around it."""
