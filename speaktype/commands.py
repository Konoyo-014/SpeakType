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

# Standalone "do something to the app itself" commands. These are detected
# in the same place as edit commands but invoke a different code path —
# instead of asking the LLM to rewrite selected text, the app does
# something locally (undo last insertion, copy clipboard, etc.).
ACTION_COMMAND_PATTERNS = {
    "undo_last": [
        r"^undo (?:that|last|last dictation)\.?$",
        r"^scratch that\.?$",
        r"^撤销(?:刚才|刚刚|上次|上一句)?[。]?$",
        r"^撤回[。]?$",
    ],
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
    "open double quote": '"',
    "close double quote": '"',
    "open single quote": "'",
    "close single quote": "'",
    "open parenthesis": "(",
    "close parenthesis": ")",
    "open parentheses": "(",
    "close parentheses": ")",
    "open bracket": "[",
    "close bracket": "]",
    "open square bracket": "[",
    "close square bracket": "]",
    "句号": "。",
    "逗号": "，",
    "问号": "？",
    "感叹号": "！",
    "冒号": "：",
    "分号": "；",
    "左引号": "“",
    "右引号": "”",
    "左双引号": "“",
    "右双引号": "”",
    "左单引号": "‘",
    "右单引号": "’",
    "左括号": "（",
    "右括号": "）",
    "左圆括号": "（",
    "右圆括号": "）",
    "左方括号": "[",
    "右方括号": "]",
    "左书名号": "《",
    "右书名号": "》",
}

_DELIMITER_PAIRS = (
    (("open quote", "open double quote"), ("close quote", "close double quote")),
    (("open single quote",), ("close single quote",)),
    (("open parenthesis", "open parentheses"), ("close parenthesis", "close parentheses")),
    (("open bracket", "open square bracket"), ("close bracket", "close square bracket")),
    (("左引号", "左双引号"), ("右引号", "右双引号")),
    (("左单引号",), ("右单引号",)),
    (("左括号", "左圆括号"), ("右括号", "右圆括号")),
    (("左方括号",), ("右方括号",)),
    (("左书名号",), ("右书名号",)),
)
_OPENING_COMMANDS = {command: index for index, (opening, _) in enumerate(_DELIMITER_PAIRS)
                     for command in opening}
_CLOSING_COMMANDS = {command: index for index, (_, closing) in enumerate(_DELIMITER_PAIRS)
                     for command in closing}
_HORIZONTAL_SPACE = " \r\f\v"


def _command_pattern(command: str) -> str:
    if command.isascii():
        words = r"[^\S\n\t]+".join(re.escape(word) for word in command.split())
        return r"(?<!\w)" + words + r"(?!\w)"
    return re.escape(command)


_PUNCTUATION_ALTERNATIVES = "|".join(
    _command_pattern(command) for command in sorted(PUNCTUATION_COMMANDS, key=len, reverse=True)
)
_PUNCTUATION_TOKEN_RE = re.compile(_PUNCTUATION_ALTERNATIVES, re.IGNORECASE)
_PUNCTUATION_CHAIN_RE = re.compile(
    r"(?:" + _PUNCTUATION_ALTERNATIVES + r")(?:[^\S\n\t]*(?:"
    + _PUNCTUATION_ALTERNATIVES + r"))*[^\S\n\t]*(?=$|\n|\t)",
    re.IGNORECASE,
)

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
    r"^bullet (?:point|list) (?:this|it)\.?$",
    r"^turn (?:this|it) into (?:a )?(?:list|bullets|bullet points)\.?$",
    r"^make (?:this|it) (?:a )?headline\.?$",
    r"^expand on (?:this|it)\.?$",
    r"^simplify (?:this|it)?\.?$",
    r"^add details\.?$",
    r"^remove details\.?$",
    r"^proofread (?:this)?\.?$",
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
    r"^改成列表[。]?$",
    r"^改成要点[。]?$",
    r"^改成标题[。]?$",
    r"^润色一下[。]?$",
    r"^更简洁[。]?$",
    r"^更详细[。]?$",
]


def process_punctuation_commands(text: str) -> str:
    """Replace spoken voice commands with their symbols.

    Structural commands become line breaks or tabs. A sequence of spoken
    punctuation commands is converted at the end of a clause. Matching
    opening quotes and brackets are also converted when their closing
    command belongs to that sequence.
    """
    result = text

    # 清除结构命令周围的口述空格，保留换行和制表符。
    for cmd, symbol in sorted(STRUCTURAL_COMMANDS.items(), key=lambda x: -len(x[0])):
        pattern = re.compile(r"[^\S\n\t]*" + _command_pattern(cmd) + r"[^\S\n\t]*", re.IGNORECASE)
        result = pattern.sub(symbol, result)

    tokens = list(_PUNCTUATION_TOKEN_RE.finditer(result))
    accepted = {
        chain.start() + token.start()
        for chain in _PUNCTUATION_CHAIN_RE.finditer(result)
        for token in _PUNCTUATION_TOKEN_RE.finditer(chain.group())
    }
    opening_tokens = {index: [] for index in range(len(_DELIMITER_PAIRS))}
    previous_end = 0
    for token in tokens:
        if "\n" in result[previous_end:token.start()] or "\t" in result[previous_end:token.start()]:
            for pending in opening_tokens.values():
                pending.clear()
        command = " ".join(token.group().lower().split())
        if command in _OPENING_COMMANDS:
            opening_tokens[_OPENING_COMMANDS[command]].append(token.start())
        elif command in _CLOSING_COMMANDS:
            pending = opening_tokens[_CLOSING_COMMANDS[command]]
            if pending:
                opening_start = pending.pop()
                if token.start() in accepted:
                    accepted.add(opening_start)
        previous_end = token.end()

    output = ""
    cursor = 0
    trim_next_space = False
    for token in tokens:
        if token.start() not in accepted:
            continue
        command = " ".join(token.group().lower().split())
        between = result[cursor:token.start()]
        if trim_next_space:
            between = between.lstrip(_HORIZONTAL_SPACE)
        output += between
        opening = command in _OPENING_COMMANDS
        if not opening or not command.isascii():
            output = output.rstrip(_HORIZONTAL_SPACE)
        output += PUNCTUATION_COMMANDS[command]
        trim_next_space = opening
        cursor = token.end()
    remainder = result[cursor:]
    return output + (remainder.lstrip(_HORIZONTAL_SPACE) if trim_next_space else remainder)


def detect_edit_command(text: str) -> tuple[bool, str]:
    """Check if the transcribed text is an edit command.
    Returns (is_edit_command, command_text).
    """
    text_lower = text.strip().lower()
    for pattern in EDIT_COMMAND_PATTERNS:
        if re.search(pattern, text_lower):
            return True, text.strip()
    return False, ""


def detect_action_command(text: str) -> str | None:
    """Check if the transcribed text is a local action command.

    Action commands operate on the app itself (e.g. undo the last
    dictation) instead of asking the LLM to rewrite anything. Returns the
    action id (e.g. ``"undo_last"``) or ``None`` if no match.
    """
    text_lower = text.strip().lower()
    for action_id, patterns in ACTION_COMMAND_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return action_id
    return None


def build_edit_prompt(command: str, selected_text: str, tone: str = "neutral") -> str:
    """Build a prompt for the LLM to process an edit command on selected text."""
    return f"""You are a text editing assistant. The user has selected the following text and given a voice command to modify it.

Selected text:
\"\"\"{selected_text}\"\"\"

Voice command: {command}
Context tone: {tone}

Apply the user's command to the selected text. Return ONLY the modified text, nothing else. No explanations, no quotes around it."""
