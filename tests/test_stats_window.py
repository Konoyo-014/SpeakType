from datetime import datetime

from speaktype.i18n import set_language
from speaktype.stats_window import (
    stats_day_label,
    stats_metric_values,
    stats_summary_text,
    stats_window_recent_rows,
    wrapped_text_height,
)


def test_stats_window_recent_rows_keep_latest_first_and_full_text():
    entries = [
        {"timestamp": "2026-05-07T09:00:00", "polished": "first", "app": "Notes", "duration": 1.2},
        {
            "timestamp": "2026-05-07T10:00:00",
            "polished": "这是一条很长的听写记录，用来确认统计窗口不会在数据层提前截断最近听写文本。",
            "app": "Codex",
            "duration": 2.5,
        },
    ]

    rows = stats_window_recent_rows(entries, limit=2)

    assert rows[0]["timestamp"] == "2026-05-07 10:00"
    assert rows[0]["app"] == "Codex"
    assert rows[0]["duration"] == 2.5
    assert rows[0]["text"].endswith("最近听写文本。")
    assert rows[1]["text"] == "first"


def test_wrapped_text_height_grows_for_long_cjk_text():
    short = wrapped_text_height("短文本", 520)
    long = wrapped_text_height("这是一段用于测试统计窗口多行高度估算的中文内容。" * 8, 520)

    assert long > short


def test_stats_window_uses_localized_duration_units():
    set_language("zh")
    stats = {"total_entries": 3, "total_words": 1280, "total_duration_min": 2.5}

    summary = stats_summary_text(stats)
    metrics = dict(stats_metric_values(stats))

    assert "2.5 分钟" in summary
    assert metrics["总时长"] == "2.5 分钟"
    assert metrics["平均时长/次"].endswith("秒")


def test_stats_day_label_uses_chinese_weekdays():
    set_language("zh")

    assert stats_day_label(datetime(2026, 5, 8)) == "05/08 周五"
