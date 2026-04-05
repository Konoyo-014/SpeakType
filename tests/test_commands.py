"""Tests for voice command detection and processing."""

import pytest
from speaktype.commands import (
    process_punctuation_commands,
    detect_edit_command,
)


class TestPunctuationCommands:
    def test_structural_new_line(self):
        result = process_punctuation_commands("hello new line world")
        assert "\n" in result
        assert "new line" not in result

    def test_structural_new_paragraph(self):
        result = process_punctuation_commands("hello new paragraph world")
        assert "\n\n" in result
        assert "new paragraph" not in result

    def test_structural_tab(self):
        result = process_punctuation_commands("hello tab world")
        assert "\t" in result

    def test_structural_chinese(self):
        result = process_punctuation_commands("hello 换行 world")
        assert "\n" in result

    def test_punctuation_period_at_end(self):
        result = process_punctuation_commands("hello world period")
        assert result.strip().endswith(".")

    def test_punctuation_comma_at_end(self):
        result = process_punctuation_commands("hello world comma")
        assert "," in result

    def test_punctuation_question_mark(self):
        result = process_punctuation_commands("what is this question mark")
        assert "?" in result

    def test_no_false_positive_period(self):
        # "period" in the middle of speech should not be replaced
        result = process_punctuation_commands("the period of time was long")
        assert "period" in result.lower() or "." not in result[:20]

    def test_chinese_punctuation(self):
        result = process_punctuation_commands("你好 句号")
        assert "\u3002" in result  # 。

    def test_multiple_commands(self):
        result = process_punctuation_commands("hello new line world new line end")
        assert result.count("\n") >= 2

    def test_empty_input(self):
        assert "" == process_punctuation_commands("")

    def test_no_commands(self):
        text = "this is a normal sentence"
        assert text == process_punctuation_commands(text)


class TestEditCommands:
    def test_make_shorter(self):
        is_edit, cmd = detect_edit_command("make this shorter")
        assert is_edit
        assert "shorter" in cmd.lower()

    def test_make_formal(self):
        is_edit, cmd = detect_edit_command("make it formal")
        assert is_edit

    def test_fix_grammar(self):
        is_edit, cmd = detect_edit_command("fix the grammar")
        assert is_edit

    def test_translate_to(self):
        is_edit, cmd = detect_edit_command("translate to Chinese")
        assert is_edit

    def test_chinese_edit(self):
        is_edit, cmd = detect_edit_command("\u7f29\u77ed")  # 缩短
        assert is_edit

    def test_not_edit_command(self):
        is_edit, cmd = detect_edit_command("hello world this is a dictation")
        assert not is_edit
        assert cmd == ""

    def test_summarize(self):
        is_edit, cmd = detect_edit_command("summarize this")
        assert is_edit

    def test_clean_up(self):
        is_edit, cmd = detect_edit_command("clean this up")
        assert is_edit
