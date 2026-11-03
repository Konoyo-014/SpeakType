from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
import re
import subprocess

import AppKit
import objc
from Foundation import NSObject, NSIndexSet, NSMakeRect, NSMakeSize

from .config import ensure_config_dir, load_custom_dictionary
from .hotwords import (
    HotwordStore, MAX_ALIASES_PER_TERM, MAX_ALIAS_CHARS, MAX_TERM_CHARS,
    _entry_applies, _match_key, _replacement_pattern,
)
from .i18n import get_language, t


FILTERS = ("all", "active", "pending", "disabled")
SCENES = ("", "email", "chat", "code", "notes", "default")
EXPORT_SCHEMA = "speaktype.hotwords"


def _w(zh, en):
    return en if get_language() == "en" else zh


def _confidence_percent(value) -> str:
    confidence = max(0.0, min(1.0, float(value or 0)))
    return f"{round(confidence * 100):.0f}%"


def _short_date(value: str) -> str:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%Y-%m-%d") if value else ""


def _top_counter_keys(mapping: dict, limit: int = 2) -> str:
    pairs = sorted(mapping.items(), key=lambda item: int(item[1]), reverse=True)
    return ", ".join(str(key) for key, _ in pairs[:limit] if key)


def hotword_window_rows(entries: list[dict], query: str = "", filter_id: str = "all") -> list[dict]:
    if filter_id not in FILTERS:
        raise ValueError(f"Unknown hotword filter: {filter_id}")
    query = query.strip().casefold()
    rows = []
    for entry in entries:
        active = bool(entry.get("active"))
        disabled = bool(entry.get("user_disabled"))
        state = "active" if active else "disabled" if disabled else "pending"
        if filter_id != "all" and state != filter_id:
            continue
        searchable = " ".join([entry["term"], *entry.get("aliases", []),
                               entry.get("scope_app", ""), entry.get("scope_scene", "")]).casefold()
        if query and query not in searchable:
            continue
        rows.append({
            **entry, "term": entry["term"], "active": active, "state": state,
            "confidence": _confidence_percent(entry.get("confidence")),
            "observations": int(entry.get("observations", 0)),
            "updated": _short_date(entry.get("updated_at") or entry.get("last_seen_at") or ""),
            "alias_list": list(entry.get("aliases", [])),
            "aliases": ", ".join(entry.get("aliases", [])),
            "apps": _top_counter_keys(entry.get("apps", {})),
        })
    return sorted(rows, key=lambda row: (FILTERS.index(row["state"]), -row["observations"], row["term"].casefold()))


def active_hotword_context_text(entries: list[dict]) -> str:
    return " ".join(row["term"] for row in hotword_window_rows(entries) if row["active"])


def active_hotword_context_copy_state(entries: list[dict]) -> dict:
    text = active_hotword_context_text(entries)
    count = sum(1 for entry in entries if entry.get("active"))
    return {"text": text, "count": count, "should_copy": bool(text),
            "feedback": t("hotwords_copy_done", count=count) if text else t("hotwords_copy_empty")}


def hotword_reveal_feedback(file_exists: bool) -> str:
    return t("hotwords_reveal_done_file" if file_exists else "hotwords_reveal_done_folder")


def _display_len(text: str) -> int:
    return sum(2 if ord(character) > 127 else 1 for character in str(text or ""))


def hotword_row_detail(row_data: dict) -> str:
    parts = []
    if row_data.get("aliases"):
        parts.append(t("hotwords_aliases", aliases=row_data["aliases"]))
    if row_data.get("apps"):
        parts.append(t("hotwords_apps", apps=row_data["apps"]))
    return "  ·  ".join(parts) if parts else t("hotwords_no_extra")


def hotword_row_metrics(row_data: dict, width: int = 612) -> dict:
    text_width = max(220, width - 62)
    title_lines = min(2, max(1, math.ceil(_display_len(row_data.get("term", "")) / max(24, int(text_width / 8.5)))))
    detail = hotword_row_detail(row_data)
    detail_lines = min(4, max(1, math.ceil(_display_len(detail) / max(28, int(text_width / 7)))))
    title_height = 20 if title_lines == 1 else 38
    detail_height = detail_lines * 18
    return {"text_width": text_width, "title_height": title_height, "detail_height": detail_height,
            "row_height": max(92, 14 + title_height + 22 + 6 + detail_height + 12), "detail": detail}


def hotword_rows_document_height(rows: list[dict], width: int = 652, min_height: int = 368) -> int:
    return max(min_height, 16 + sum(hotword_row_metrics(row, width)["row_height"] + 8 for row in rows))


def validate_hotword_import(payload) -> list[dict]:
    if not isinstance(payload, dict) or set(payload) != {"schema", "version", "entries"}:
        raise ValueError(_w("JSON 顶层需要 schema、version 和 entries 三个字段。", "JSON must contain exactly schema, version and entries."))
    if payload["schema"] != EXPORT_SCHEMA or type(payload["version"]) is not int or payload["version"] != 1:
        raise ValueError(_w("文件格式应为 speaktype.hotwords，版本应为 1。", "Expected schema speaktype.hotwords, version 1."))
    entries = payload["entries"]
    if not isinstance(entries, list) or len(entries) > 1000:
        raise ValueError(_w("entries 应为数组，最多包含 1000 条词语。", "entries must be an array with at most 1,000 words."))
    allowed = {"term", "aliases", "enabled", "scope_app", "scope_scene", "state", "confidence", "observations", "source", "user_confirmed",
               "approved_aliases", "alias_confidences"}
    seen = set()
    validated = []
    for index, entry in enumerate(entries, 1):
        prefix = _w(f"第 {index} 条：", f"Entry {index}: ")
        if not isinstance(entry, dict) or set(entry) - allowed or "term" not in entry:
            raise ValueError(prefix + _w("词语字段缺失或包含未知字段。", "Missing term or unknown fields."))
        term = entry["term"]
        if not isinstance(term, str) or not 2 <= len(term.strip()) <= MAX_TERM_CHARS:
            raise ValueError(prefix + _w(f"标准拼写需要 2 至 {MAX_TERM_CHARS} 个字符。", f"Term needs 2–{MAX_TERM_CHARS} characters."))
        if any(ord(character) < 32 for character in term) or any(character in term for character in "，。！？；：、,!?;:") or term.strip().endswith("."):
            raise ValueError(prefix + _w("标准拼写需要是词语或简短名称。", "Term must be a word or short name."))
        key = " ".join(term.split()).casefold()
        if key in seen:
            raise ValueError(prefix + _w(f"标准拼写重复：{term}", f"Duplicate term: {term}"))
        seen.add(key)
        aliases = entry.get("aliases", [])
        if not isinstance(aliases, list) or len(aliases) > MAX_ALIASES_PER_TERM or any(
            not isinstance(alias, str) or not alias.strip() or len(alias.strip()) > MAX_ALIAS_CHARS
            or any(ord(character) < 32 for character in alias) for alias in aliases
        ):
            raise ValueError(prefix + _w(f"误识别写法需要是最多 {MAX_ALIASES_PER_TERM} 条非空字符串，每条最多 {MAX_ALIAS_CHARS} 个字符。", f"aliases must contain at most {MAX_ALIASES_PER_TERM} nonempty strings of up to {MAX_ALIAS_CHARS} characters."))
        state = entry.get("state")
        if "state" in entry and state not in FILTERS[1:]:
            raise ValueError(prefix + _w("state 需要为 active、pending 或 disabled。", "state must be active, pending or disabled."))
        enabled = entry.get("enabled", state == "active" if state is not None else True)
        if not isinstance(enabled, bool):
            raise ValueError(prefix + _w("enabled 需要为 true 或 false。", "enabled must be true or false."))
        if state is not None and enabled != (state == "active"):
            raise ValueError(prefix + _w("state 与 enabled 的状态不同。", "state and enabled disagree."))
        scope_app = entry.get("scope_app", "")
        scope_scene = entry.get("scope_scene", "")
        if not isinstance(scope_app, str) or len(scope_app) > 200 or any(ord(character) < 32 for character in scope_app):
            raise ValueError(prefix + _w("应用范围需要是最多 200 个字符的单行文字。", "scope_app must be a single-line string of up to 200 characters."))
        if scope_scene not in SCENES:
            raise ValueError(prefix + _w("场景需要留空或使用 email、chat、code、notes、default。", "scope_scene must be empty or email, chat, code, notes, default."))
        metadata = {}
        alias_names = {alias.strip() for alias in aliases}
        if "approved_aliases" in entry:
            approved = entry["approved_aliases"]
            if not isinstance(approved, list) or any(not isinstance(alias, str) or alias.strip() not in alias_names for alias in approved):
                raise ValueError(prefix + _w("approved_aliases 需要是误识别写法的子集。", "approved_aliases must be a subset of aliases."))
            approved = [alias.strip() for alias in approved]
            if len(approved) != len(set(approved)) or (state == "pending" and approved):
                raise ValueError(prefix + _w("已批准写法不能重复，待确认词语的已批准写法需要为空。", "Approved aliases cannot repeat, and pending words must have none."))
            metadata["approved_aliases"] = approved
        if "alias_confidences" in entry:
            confidences = entry["alias_confidences"]
            if not isinstance(confidences, dict) or any(
                not isinstance(alias, str) or alias.strip() not in alias_names
                or isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence) or not 0 <= confidence <= 1
                for alias, confidence in confidences.items()
            ):
                raise ValueError(prefix + _w("alias_confidences 需要使用现有误识别写法作为字段，数值为 0 至 1 之间的有限数字。", "alias_confidences must use existing aliases with finite numeric values from 0 to 1."))
            metadata["alias_confidences"] = {alias.strip(): confidence for alias, confidence in confidences.items()}
        if "user_confirmed" in entry:
            if not isinstance(entry["user_confirmed"], bool):
                raise ValueError(prefix + _w("user_confirmed 需要为 true 或 false。", "user_confirmed must be true or false."))
            if state == "pending" and entry["user_confirmed"]:
                raise ValueError(prefix + _w("待确认词语的 user_confirmed 需要为 false。", "Pending words must have user_confirmed set to false."))
            metadata["user_confirmed"] = entry["user_confirmed"]
        if "confidence" in entry:
            confidence = entry["confidence"]
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError(prefix + _w("confidence 需要为 0 至 1 之间的有限数字。", "confidence must be a finite number from 0 to 1."))
            metadata["confidence"] = confidence
        if "observations" in entry:
            if type(entry["observations"]) is not int or entry["observations"] < 0:
                raise ValueError(prefix + _w("observations 需要为非负整数。", "observations must be a nonnegative integer."))
            metadata["observations"] = entry["observations"]
        if "source" in entry:
            if entry["source"] not in ("manual", "post_edit", "imported") or (state == "pending" and entry["source"] == "manual"):
                raise ValueError(prefix + _w("source 需要为 manual、post_edit 或 imported；待确认词语需要保留学习来源。", "source must be manual, post_edit or imported; pending words need a learning source."))
            metadata["source"] = entry["source"]
        validated.append({"term": term.strip(), "aliases": [alias.strip() for alias in aliases],
                          "enabled": enabled, "scope_app": scope_app.strip(), "scope_scene": scope_scene,
                          **({"state": state} if state is not None else {}), **metadata})
    return validated


def hotword_export_payload(entries: list[dict]) -> dict:
    return {"schema": EXPORT_SCHEMA, "version": 1, "entries": [
        {"term": entry["term"], "aliases": list(entry.get("aliases", [])), "enabled": bool(entry.get("active")),
         "state": "active" if entry.get("active") else "disabled" if entry.get("user_disabled") else "pending",
         "scope_app": entry.get("scope_app", ""), "scope_scene": entry.get("scope_scene", ""),
         "source": "manual" if entry.get("source") == "dictionary" else entry.get("source", "post_edit"), "confidence": entry.get("confidence", 0.5),
         "observations": entry.get("observations", 0), "user_confirmed": entry.get("user_confirmed", False),
         "approved_aliases": list(entry.get("approved_aliases", entry.get("aliases", []) if entry.get("source") == "manual" or entry.get("user_confirmed") else [])),
         "alias_confidences": dict(entry.get("alias_confidences", {alias: entry.get("confidence", 0.5) for alias in entry.get("aliases", [])}))}
        for entry in entries
    ]}


def _running_application_names():
    return [{"name": str(app.localizedName() or ""), "bundle_id": str(app.bundleIdentifier() or "")}
            for app in AppKit.NSWorkspace.sharedWorkspace().runningApplications()]


def _app_scope_overlaps(left, right, applications):
    left = str(left or "").casefold()
    right = str(right or "").casefold()
    if not left or not right or left == right:
        return True
    left_keys = {left}
    right_keys = {right}
    known_bundle_ids = set()
    for application in applications:
        keys = {application["name"].casefold(), application["bundle_id"].casefold()}
        known_bundle_ids.add(application["bundle_id"].casefold())
        if left in keys:
            left_keys.update(keys)
        if right in keys:
            right_keys.update(keys)
    if left_keys & right_keys:
        return True
    left_is_id = "." in left
    right_is_id = "." in right
    if left_is_id == right_is_id:
        return False
    bundle_id = left if left_is_id else right
    return bundle_id not in known_bundle_ids


def hotword_alias_conflicts(entries, *, app_info=None, scene=""):
    applications = _running_application_names()
    enabled = [entry for entry in entries if entry.get("active")
               and (app_info is None or _entry_applies(entry, app_info, scene))]
    candidates = {}
    for entry in enabled:
        for value, is_alias in [(entry["term"], False), *[(alias, True) for alias in entry.get("aliases", [])]]:
            candidates.setdefault(_match_key(value), []).append((value, is_alias, entry))
    conflicts = []
    for values in candidates.values():
        targets = set()
        aliases = set()
        canonical_terms = set()
        for index, (left_value, left_alias, left) in enumerate(values):
            for right_value, right_alias, right in values[index + 1:]:
                if left["term"].casefold() == right["term"].casefold() or not (left_alias or right_alias):
                    continue
                left_scene = left.get("scope_scene", "")
                right_scene = right.get("scope_scene", "")
                if left_scene and right_scene and left_scene != right_scene:
                    continue
                if not _app_scope_overlaps(left.get("scope_app"), right.get("scope_app"), applications):
                    continue
                targets.update((left["term"], right["term"]))
                if left_alias:
                    aliases.add(left_value)
                if right_alias:
                    aliases.add(right_value)
                if not left_alias:
                    canonical_terms.add(left["term"])
                if not right_alias:
                    canonical_terms.add(right["term"])
        if targets:
            conflicts.append({"aliases": sorted(aliases), "terms": sorted(targets), "canonical_terms": sorted(canonical_terms)})
    return conflicts


def _conflict_message(conflicts):
    details = []
    for conflict in conflicts:
        detail = f"{', '.join(conflict['aliases'])} → {', '.join(conflict['terms'])}"
        if conflict["canonical_terms"]:
            names = ", ".join(conflict["canonical_terms"])
            detail += _w(f"；已有标准拼写 {names} 会优先保留", f"; saved spelling {names} takes precedence")
        details.append(detail)
    return _w("误识别写法存在冲突：", "Conflicting misspellings: ") + "; ".join(details)


class _VocabularyBackgroundView(AppKit.NSView):
    def drawRect_(self, rect):
        AppKit.NSColor.windowBackgroundColor().setFill()
        AppKit.NSRectFill(rect)


class _HotwordsDelegate(NSObject):
    def initWithController_(self, controller):
        self = objc.super(_HotwordsDelegate, self).init()
        if self is not None:
            self._controller = controller
        return self

    def controlTextDidChange_(self, notification):
        if notification.object() == self._controller._search_field:
            self._controller._render_rows()
        else:
            self._controller._editor_changed()

    def textDidChange_(self, notification):
        if notification.object() == self._controller._aliases_view:
            self._controller._editor_changed()

    def onDraftChanged_(self, sender):
        self._controller._editor_changed()

    def windowShouldClose_(self, sender):
        self._controller._capture_draft()
        return True

    def windowWillClose_(self, notification):
        self._controller._capture_draft()

    def onFilter_(self, sender):
        self._controller._render_rows()

    def onSelect_(self, sender):
        self._controller.select_entry(self._controller._visible_rows[sender.tag()]["term"])

    def numberOfRowsInTableView_(self, table):
        return len(self._controller._visible_rows)

    def tableView_objectValueForTableColumn_row_(self, table, column, row):
        entry = self._controller._visible_rows[row]
        if column.identifier() == "term":
            return entry["term"] + (" •" if entry["term"] in self._controller._drafts else "")
        return {"active": _w("已启用", "Enabled"), "pending": _w("待确认", "Review"),
                "disabled": _w("已停用", "Disabled")}[entry["state"]]

    def tableViewSelectionDidChange_(self, notification):
        if self._controller._updating_table:
            return
        index = self._controller._table.selectedRow()
        if index >= 0:
            self._controller.select_entry(self._controller._visible_rows[index]["term"])

    def onNew_(self, sender):
        self._controller.new_entry()

    def onSave_(self, sender):
        self._controller.save_entry()

    def onToggle_(self, sender):
        self._controller.toggle_entry()

    def onDelete_(self, sender):
        self._controller.delete_entry()

    def onTest_(self, sender):
        self._controller.test_text()

    def onImport_(self, sender):
        self._controller.choose_import()

    def onExport_(self, sender):
        self._controller.choose_export()

    def onRefresh_(self, sender):
        self._controller.refresh()

    def onCopyContext_(self, sender):
        self._controller.copy_context()

    def onReveal_(self, sender):
        self._controller.reveal_store()

    def onClose_(self, sender):
        self._controller.close()


class HotwordsWindowController:
    WIDTH = 840
    HEIGHT = 650
    ROW_WIDTH = 236

    def __init__(self, hotwords: HotwordStore | None = None, on_change=None, on_test=None, test_status=None,
                 dictionary_loader=load_custom_dictionary):
        if not callable(dictionary_loader):
            raise TypeError("dictionary_loader must be callable")
        self.hotwords = hotwords if hotwords is not None else HotwordStore()
        self.on_change = on_change
        self.on_test = on_test
        self.test_status = test_status
        self.dictionary_loader = dictionary_loader
        self.window = None
        self._delegate = None
        self._rows_view = None
        self._summary_field = None
        self._copy_feedback_field = None
        self._last_entries = []
        self._visible_rows = []
        self._selected_term = None
        self._drafts = {}
        self._form_baseline = None
        self._form_ready = False
        self._updating_table = False

    def show(self):
        if self.window is None:
            self._build_window()
        self.refresh()
        self.window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)

    def close(self):
        if self.window:
            self._capture_draft()
            self.window.close()

    def refresh(self):
        self._capture_draft()
        self._last_entries = self._merged_entries()
        if self._rows_view is not None:
            self._render_rows()
            if self._selected_term:
                entry = next((entry for entry in self._last_entries if entry["term"] == self._selected_term), None)
                if entry is None:
                    draft = self._drafts.pop(self._selected_term, None)
                    if draft is not None:
                        self._drafts[None] = draft
                    self._selected_term = None
            self._load_form(self._selected_term)
            self._test_status_field.setStringValue_(str(self.test_status()) if self.test_status is not None else "")
            self._test_status_field.setToolTip_(self._test_status_field.stringValue())

    def _merged_entries(self):
        return self.hotwords.get_all(dictionary=self.dictionary_loader())

    def _notify_change(self):
        if self.on_change is not None:
            self.on_change()

    def copy_context(self):
        state = active_hotword_context_copy_state(self._last_entries)
        if state["should_copy"]:
            pasteboard = AppKit.NSPasteboard.generalPasteboard()
            pasteboard.clearContents()
            pasteboard.setString_forType_(state["text"], AppKit.NSPasteboardTypeString)
        self._set_status(state["feedback"])

    def reveal_store(self):
        ensure_config_dir()
        path = self.hotwords._path
        subprocess.run(["open", "-R", str(path)] if path.exists() else ["open", str(path.parent)], check=True)
        self._set_status(hotword_reveal_feedback(path.exists()))

    def _build_window(self):
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, self.WIDTH, self.HEIGHT),
            AppKit.NSTitledWindowMask | AppKit.NSClosableWindowMask | AppKit.NSMiniaturizableWindowMask,
            AppKit.NSBackingStoreBuffered, False)
        self.window.setReleasedWhenClosed_(False)
        self.window.setTitle_(_w("SpeakType · 热词词典", "SpeakType · Vocabulary"))
        self.window.setTabbingMode_(AppKit.NSWindowTabbingModeDisallowed)
        self.window.setBackgroundColor_(AppKit.NSColor.windowBackgroundColor())
        self.window.center()
        self._delegate = _HotwordsDelegate.alloc().initWithController_(self)
        self.window.setDelegate_(self._delegate)
        root = _VocabularyBackgroundView.alloc().initWithFrame_(NSMakeRect(0, 0, self.WIDTH, self.HEIGHT))
        self.window.setContentView_(root)
        self._sidebar = AppKit.NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, 260, self.HEIGHT))
        self._sidebar.setMaterial_(AppKit.NSVisualEffectMaterialSidebar)
        self._sidebar.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
        self._sidebar.setState_(AppKit.NSVisualEffectStateActive)
        root.addSubview_(self._sidebar)
        self._separator(root, 260, 0, 1, self.HEIGHT)
        self._search_field = AppKit.NSSearchField.alloc().initWithFrame_(NSMakeRect(12, 602, 236, 28))
        self._search_field.setPlaceholderString_(_w("搜索词语或错误写法", "Search words or misspellings"))
        self._search_field.setDelegate_(self._delegate)
        self._search_field.setFont_(AppKit.NSFont.systemFontOfSize_(13))
        self._search_field.setControlSize_(AppKit.NSControlSizeSmall)
        self._sidebar.addSubview_(self._search_field)
        self._filter = AppKit.NSSegmentedControl.alloc().initWithFrame_(NSMakeRect(12, 568, 236, 26))
        self._filter.setSegmentCount_(4)
        for index, label in enumerate((_w("全部", "All"), _w("已启用", "Enabled"), _w("待确认", "Review"), _w("已停用", "Disabled"))):
            self._filter.setLabel_forSegment_(label, index)
            self._filter.setWidth_forSegment_(56, index)
        self._filter.setFont_(AppKit.NSFont.systemFontOfSize_(11))
        self._filter.setControlSize_(AppKit.NSControlSizeSmall)
        self._filter.setSelectedSegment_(0)
        self._filter.setTarget_(self._delegate)
        self._filter.setAction_(b"onFilter:")
        self._sidebar.addSubview_(self._filter)
        scroll = AppKit.NSScrollView.alloc().initWithFrame_(NSMakeRect(8, 80, 244, 476))
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        scroll.setDrawsBackground_(False)
        scroll.setBorderType_(AppKit.NSNoBorder)
        self._sidebar.addSubview_(scroll)
        self._table = AppKit.NSTableView.alloc().initWithFrame_(NSMakeRect(0, 0, self.ROW_WIDTH, 476))
        self._table.setHeaderView_(None)
        self._table.setRowHeight_(28)
        self._table.setIntercellSpacing_(NSMakeSize(6, 4))
        self._table.setBackgroundColor_(AppKit.NSColor.clearColor())
        self._table.setSelectionHighlightStyle_(AppKit.NSTableViewSelectionHighlightStyleSourceList)
        self._table.setStyle_(AppKit.NSTableViewStyleSourceList)
        self._table.setAllowsEmptySelection_(True)
        self._table.setAllowsMultipleSelection_(False)
        self._table.setDelegate_(self._delegate)
        self._table.setDataSource_(self._delegate)
        self._table.setAccessibilityLabel_(_w("热词列表", "Vocabulary list"))
        for identifier, width, size in (("term", 142, 13), ("state", 82, 11)):
            column = AppKit.NSTableColumn.alloc().initWithIdentifier_(identifier)
            column.setWidth_(width)
            column.setEditable_(False)
            column.dataCell().setFont_(AppKit.NSFont.systemFontOfSize_(size))
            column.dataCell().setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
            self._table.addTableColumn_(column)
        scroll.setDocumentView_(self._table)
        self._rows_view = self._table
        self._empty_view = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(12, 370, 236, 150))
        self._sidebar.addSubview_(self._empty_view)
        self._empty_title = self._label(self._empty_view, "", 0, 114, 236, 22, 13, bold=True)
        self._empty_detail = self._label(self._empty_view, "", 0, 0, 236, 108, 12, muted=True, wraps=True)
        self._summary_field = self._label(self._sidebar, "", 12, 49, 236, 20, 11, muted=True)
        self._button(self._sidebar, _w("添加词语", "Add word"), b"onNew:", 10, 10, 82)
        self._button(self._sidebar, _w("导入", "Import"), b"onImport:", 98, 10, 70)
        self._button(self._sidebar, _w("导出", "Export"), b"onExport:", 174, 10, 70)
        editor = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(280, 318, 540, 312))
        root.addSubview_(editor)
        self._editor_title = self._label(editor, _w("添加词语", "Add a word"), 0, 282, 400, 22, 13, bold=True)
        self._entry_meta_field = self._label(editor, "", 0, 258, 540, 18, 11, muted=True)
        self._enabled_check = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(422, 280, 118, 24))
        self._enabled_check.setButtonType_(AppKit.NSButtonTypeSwitch)
        self._enabled_check.setTitle_(_w("启用词语", "Enabled"))
        self._enabled_check.setState_(AppKit.NSControlStateValueOn)
        self._enabled_check.setTarget_(self._delegate)
        self._enabled_check.setAction_(b"onDraftChanged:")
        self._enabled_check.setFont_(AppKit.NSFont.systemFontOfSize_(12))
        self._enabled_check.setControlSize_(AppKit.NSControlSizeSmall)
        editor.addSubview_(self._enabled_check)
        self._label(editor, _w("标准拼写", "Correct spelling"), 0, 225, 540, 20, 12, muted=True)
        self._term_field = self._field(editor, 0, 195, 540, _w("例如 Qwen3-ASR、NeurIPS、张明远", "e.g. Qwen3-ASR, NeurIPS, a person's name"))
        self._term_field.setAccessibilityLabel_(_w("标准拼写", "Correct spelling"))
        self._term_field.setDelegate_(self._delegate)
        self._label(editor, _w("误识别写法 · 每行一个", "Misspellings · one per line"), 0, 165, 252, 20, 12, muted=True)
        self._aliases_view = self._text_area(editor, NSMakeRect(0, 65, 252, 94), editable=True)
        self._aliases_view.setAccessibilityLabel_(_w("误识别写法，每行一个", "Misspellings, one per line"))
        self._aliases_view.setDelegate_(self._delegate)
        self._label(editor, _w("应用范围（可选）", "App scope (optional)"), 276, 165, 264, 20, 12, muted=True)
        self._app_field = self._field(editor, 276, 132, 264, _w("留空用于全部应用", "Empty for all apps"))
        self._app_field.setDelegate_(self._delegate)
        self._scene_picker = self._scene_popup(editor, 276, 93, 264, include_all=True)
        self._scene_picker.setTarget_(self._delegate)
        self._scene_picker.setAction_(b"onDraftChanged:")
        self._delete_button = self._button(editor, _w("删除词语", "Delete"), b"onDelete:", 0, 12, 84)
        self._toggle_button = self._button(editor, _w("停用词语", "Disable"), b"onToggle:", 92, 12, 92)
        self._save_button = self._button(editor, _w("保存词语", "Save word"), b"onSave:", 432, 12, 108, primary=True)
        self._save_button.setKeyEquivalent_("s")
        self._save_button.setKeyEquivalentModifierMask_(AppKit.NSEventModifierFlagCommand)
        self._separator(root, 280, 306, 540)
        test_panel = AppKit.NSView.alloc().initWithFrame_(NSMakeRect(280, 78, 540, 218))
        root.addSubview_(test_panel)
        self._label(test_panel, _w("纠错测试", "Test corrections"), 0, 194, 540, 22, 13, bold=True)
        self._test_status_field = self._label(test_panel, "", 0, 163, 540, 27, 11, muted=True, wraps=True)
        self._label(test_panel, _w("转写文字", "Transcript text"), 0, 140, 252, 20, 12, muted=True)
        self._label(test_panel, _w("替换结果", "Replacement result"), 276, 140, 264, 20, 12, muted=True)
        self._test_input = self._text_area(test_panel, NSMakeRect(0, 82, 252, 54), editable=True)
        self._test_output = self._text_area(test_panel, NSMakeRect(276, 82, 264, 54), editable=False)
        self._test_input.setAccessibilityLabel_(_w("测试转写文字", "Test transcript text"))
        self._test_output.setAccessibilityLabel_(_w("替换结果", "Replacement result"))
        self._test_app_field = self._field(test_panel, 0, 40, 178, _w("测试应用（可留空）", "Test app (optional)"))
        self._test_scene_picker = self._scene_popup(test_panel, 188, 40, 172, include_all=False)
        self._button(test_panel, _w("测试替换", "Run test"), b"onTest:", 424, 40, 116)
        self._changes_field = self._label(test_panel, _w("输入包含误识别写法的句子。", "Enter a sentence containing a misspelling."), 0, 3, 540, 30, 11, muted=True, wraps=True)
        self._copy_feedback_field = self._label(root, _w("保存在本机，保存后立即生效。", "Stored on this Mac. Saved changes apply immediately."), 280, 18, 540, 42, 11, muted=True, wraps=True)
        self.new_entry()

    def _separator(self, view, x, y, width, height=1):
        line = AppKit.NSBox.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
        line.setBoxType_(AppKit.NSBoxSeparator)
        view.addSubview_(line)

    def _scene_popup(self, view, x, y, width, include_all):
        popup = AppKit.NSPopUpButton.alloc().initWithFrame_(NSMakeRect(x, y, width, 26))
        popup.addItemsWithTitles_([_w("全部场景", "All contexts") if include_all else _w("测试场景：全部", "Test context: all"),
                                  _w("邮件", "Email"), _w("聊天", "Chat"), _w("代码", "Code"), _w("笔记", "Notes"), _w("其他应用", "Other apps")])
        popup.setFont_(AppKit.NSFont.systemFontOfSize_(12))
        popup.setControlSize_(AppKit.NSControlSizeSmall)
        view.addSubview_(popup)
        return popup

    def _field(self, view, x, y, width, placeholder):
        field = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, width, 26))
        field.setPlaceholderString_(placeholder)
        field.setFont_(AppKit.NSFont.systemFontOfSize_(13))
        field.setControlSize_(AppKit.NSControlSizeSmall)
        field.setTextColor_(AppKit.NSColor.labelColor())
        view.addSubview_(field)
        return field

    def _text_area(self, view, frame, *, editable):
        scroll = AppKit.NSScrollView.alloc().initWithFrame_(frame)
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        scroll.setBorderType_(AppKit.NSBezelBorder if editable else AppKit.NSNoBorder)
        scroll.setDrawsBackground_(editable)
        text = AppKit.NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, frame.size.width - 4, frame.size.height))
        text.setEditable_(editable)
        text.setSelectable_(True)
        text.setRichText_(False)
        text.setAllowsUndo_(editable)
        text.setFont_(AppKit.NSFont.systemFontOfSize_(13))
        text.setTextColor_(AppKit.NSColor.labelColor())
        text.setBackgroundColor_(AppKit.NSColor.textBackgroundColor())
        text.setDrawsBackground_(editable)
        text.setTextContainerInset_(NSMakeSize(7, 6))
        text.setHorizontallyResizable_(False)
        text.setVerticallyResizable_(True)
        text.textContainer().setWidthTracksTextView_(True)
        text.textContainer().setContainerSize_(NSMakeSize(frame.size.width - 4, 1000000))
        text.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        scroll.setDocumentView_(text)
        view.addSubview_(scroll)
        return text

    def _button(self, view, title, action, x, y, width, *, primary=False):
        button = AppKit.NSButton.alloc().initWithFrame_(NSMakeRect(x, y, width, 26))
        button.setTitle_(title)
        button.setTarget_(self._delegate)
        button.setAction_(action)
        button.setBezelStyle_(AppKit.NSBezelStyleRounded)
        button.setControlSize_(AppKit.NSControlSizeSmall)
        button.setFont_(AppKit.NSFont.systemFontOfSize_(12))
        if primary:
            button.setBezelColor_(AppKit.NSColor.controlAccentColor())
        view.addSubview_(button)
        return button

    def _label(self, view, text, x, y, width, height, size=13, *, bold=False, muted=False, wraps=False):
        label = AppKit.NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
        label.setStringValue_(text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setTextColor_(AppKit.NSColor.secondaryLabelColor() if muted else AppKit.NSColor.labelColor())
        label.setFont_(AppKit.NSFont.systemFontOfSize_weight_(size, AppKit.NSFontWeightSemibold if bold else AppKit.NSFontWeightRegular))
        label.cell().setLineBreakMode_(AppKit.NSLineBreakByWordWrapping if wraps else AppKit.NSLineBreakByTruncatingTail)
        label.cell().setWraps_(wraps)
        label.setUsesSingleLineMode_(not wraps)
        view.addSubview_(label)
        return label

    def _render_rows(self):
        active = sum(1 for entry in self._last_entries if entry.get("active"))
        pending = sum(1 for entry in self._last_entries if not entry.get("active") and not entry.get("user_disabled"))
        self._summary_field.setStringValue_(_w(f"{len(self._last_entries)} 个词语 · {active} 已启用 · {pending} 待确认", f"{len(self._last_entries)} words · {active} enabled · {pending} review"))
        self._visible_rows = hotword_window_rows(self._last_entries, self._search_field.stringValue(), FILTERS[self._filter.selectedSegment()])
        self._updating_table = True
        self._table.reloadData()
        index = next((index for index, row in enumerate(self._visible_rows) if row["term"] == self._selected_term), None)
        if index is None:
            self._table.deselectAll_(None)
        else:
            self._table.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(index), False)
        self._updating_table = False
        self._empty_view.setHidden_(bool(self._visible_rows))
        if not self._visible_rows:
            title = _w("添加第一个常用词", "Add your first word") if not self._last_entries else _w("没有符合条件的词语", "No matching words")
            detail = _w("点击下方“添加词语”，保存人名、项目名或专业词语。常见的错误写法可以一起保存。", "Choose Add word below for names, projects or terminology. Include recurring misspellings when needed.") if not self._last_entries else _w("更换搜索文字，或切换到“全部”。", "Change the search or choose All.")
            self._empty_title.setStringValue_(title)
            self._empty_detail.setStringValue_(detail)

    def new_entry(self):
        self._capture_draft()
        self._load_form(None)
        self.window.makeFirstResponder_(self._term_field)

    def select_entry(self, term):
        self._capture_draft()
        self._load_form(term)

    def _form_values(self):
        return {"term": str(self._term_field.stringValue()), "aliases": str(self._aliases_view.string()),
                "scope_app": str(self._app_field.stringValue()), "scene_index": self._scene_picker.indexOfSelectedItem(),
                "enabled": bool(self._enabled_check.state())}

    def _capture_draft(self):
        if not self._form_ready:
            return
        values = self._form_values()
        if values != self._form_baseline:
            self._drafts[self._selected_term] = values
        else:
            self._drafts.pop(self._selected_term, None)

    def has_unsaved_changes(self):
        self._capture_draft()
        return bool(self._drafts)

    def _load_form(self, term):
        self._form_ready = False
        self._selected_term = term
        entry = next((entry for entry in self._last_entries if entry["term"] == term), {})
        self._form_baseline = {"term": entry.get("term", ""), "aliases": "\n".join(entry.get("aliases", [])),
                               "scope_app": entry.get("scope_app", ""),
                               "scene_index": SCENES.index(entry.get("scope_scene", "")),
                               "enabled": bool(entry.get("active", True))}
        values = self._drafts.get(term, self._form_baseline)
        self._term_field.setStringValue_(values["term"])
        self._aliases_view.setString_(values["aliases"])
        self._app_field.setStringValue_(values["scope_app"])
        self._scene_picker.selectItemAtIndex_(values["scene_index"])
        self._enabled_check.setState_(AppKit.NSControlStateValueOn if values["enabled"] else AppKit.NSControlStateValueOff)
        self._toggle_button.setTitle_(_w("停用词语", "Disable") if entry.get("active") else _w("启用词语", "Enable"))
        self._toggle_button.setEnabled_(bool(entry))
        self._delete_button.setEnabled_(bool(entry))
        source = {"manual": _w("手动添加", "Added manually"), "post_edit": _w("从修改中学习", "Learned from edits"),
                  "imported": _w("从文件导入", "Imported from a file"),
                  "dictionary": _w("原有词典", "Existing dictionary")}.get(entry.get("source"), "")
        observations = entry.get("observations", 0)
        if observations:
            source += _w(f" · 观察 {observations} 次", f" · {observations} {'observation' if observations == 1 else 'observations'}")
        self._entry_meta_field.setStringValue_(source)
        self._form_ready = True
        self._editor_changed()
        self._render_rows()

    def _editor_changed(self):
        if not self._form_ready:
            return
        self._capture_draft()
        title = _w("编辑词语", "Edit word") if self._selected_term is not None else _w("添加词语", "Add a word")
        dirty = self._selected_term in self._drafts
        self._editor_title.setStringValue_(title + (_w(" · 尚未保存", " · Unsaved") if dirty else ""))
        if self._drafts:
            self._set_status(_w(f"有 {len(self._drafts)} 个未保存的词条，切换词语和关闭窗口会保留本次草稿。", f"{len(self._drafts)} unsaved drafts. Switching words or closing this window keeps them for this session."))
        else:
            self._set_status(_w("词典保存在本机，保存后立即生效。", "Stored on this Mac. Changes apply as soon as you save."))

    def _set_status(self, text, *, error=False):
        if self._copy_feedback_field is not None:
            self._copy_feedback_field.setStringValue_(text)
            self._copy_feedback_field.setToolTip_(text)
            self._copy_feedback_field.setTextColor_(AppKit.NSColor.systemRedColor() if error else AppKit.NSColor.secondaryLabelColor())

    def save_entry(self):
        entry = {"term": self._term_field.stringValue().strip(),
                 "aliases": [line.strip() for line in self._aliases_view.string().splitlines() if line.strip()],
                 "enabled": bool(self._enabled_check.state()), "scope_app": self._app_field.stringValue().strip(),
                 "scope_scene": SCENES[self._scene_picker.indexOfSelectedItem()]}
        try:
            validate_hotword_import({"schema": EXPORT_SCHEMA, "version": 1, "entries": [entry]})
            merged = self._merged_entries()
            if self._selected_term is None and any(item["term"].casefold() == entry["term"].casefold() for item in merged):
                raise ValueError(_w("这个词语已经存在，请在左侧选择后编辑。", "This word exists. Select it in the list to edit."))
            if any(item["term"] != self._selected_term and item["term"].casefold() == entry["term"].casefold() for item in merged):
                raise ValueError(_w("这个词语已经存在，请在左侧选择后编辑。", "This word exists. Select it in the list to edit."))
            candidates = [item for item in merged if item["term"] != self._selected_term]
            candidates.append({**entry, "active": entry["enabled"]})
            conflicts = [conflict for conflict in hotword_alias_conflicts(candidates)
                         if entry["term"] in conflict["terms"]]
            if conflicts:
                raise ValueError(_conflict_message(conflicts))
            stored = self.hotwords.upsert_manual(entry["term"], entry["aliases"], original_term=self._selected_term,
                                                enabled=entry["enabled"], scope_app=entry["scope_app"], scope_scene=entry["scope_scene"],
                                                dictionary=self.dictionary_loader())
        except (ValueError, TypeError, KeyError, OSError) as error:
            self._editor_changed()
            self._set_status(str(error), error=True)
            return False
        self._selected_term = stored["term"]
        self._drafts.pop(self._form_baseline["term"] or None, None)
        self._form_ready = False
        self._notify_change()
        self.refresh()
        self.select_entry(stored["term"])
        self._set_status(_w(f"已保存 {stored['term']}，下次识别立即使用。", f"Saved {stored['term']}. Ready for your next dictation."))
        return True

    def toggle_entry(self):
        if self._selected_term is None:
            return False
        entry = next(entry for entry in self._last_entries if entry["term"] == self._selected_term)
        self._capture_draft()
        if not entry.get("active"):
            candidates = [{**item, "active": True} if item["term"] == self._selected_term else item
                          for item in self._merged_entries()]
            conflicts = [conflict for conflict in hotword_alias_conflicts(candidates)
                         if self._selected_term in conflict["terms"]]
            if conflicts:
                self._set_status(_conflict_message(conflicts), error=True)
                return False
        if not self.hotwords.set_active(self._selected_term, not entry.get("active"), dictionary=self.dictionary_loader()):
            raise KeyError(self._selected_term)
        if self._selected_term in self._drafts:
            self._drafts[self._selected_term]["enabled"] = not entry.get("active")
        self._form_ready = False
        self._notify_change()
        self.refresh()
        self.select_entry(self._selected_term)
        self._set_status(_w("词语状态已保存。", "Word status saved."))
        return True

    def delete_entry(self):
        if self._selected_term is None:
            return False
        term = self._selected_term
        if not self.hotwords.remove(term, dictionary=self.dictionary_loader()):
            raise KeyError(term)
        self._notify_change()
        self._drafts.pop(term, None)
        self._form_ready = False
        self._selected_term = None
        self.refresh()
        self.new_entry()
        self._set_status(_w(f"已删除 {term}。", f"Deleted {term}."))
        return True

    def test_text(self):
        app = self._test_app_field.stringValue().strip()
        app_info = {"name": app, "bundle_id": app}
        if app:
            application = next((application for application in _running_application_names()
                                if app.casefold() in (application["name"].casefold(), application["bundle_id"].casefold())), None)
            if application is not None:
                app_info = application
        scene = SCENES[self._test_scene_picker.indexOfSelectedItem()]
        text = str(self._test_input.string())
        if self.on_test is not None:
            result = self.on_test(text, app_info, scene)
        else:
            result = self.hotwords.apply(text, app_info=app_info, scene=scene, dictionary=self.dictionary_loader())
        self._test_status_field.setStringValue_(str(self.test_status()) if self.test_status is not None else "")
        self._test_status_field.setToolTip_(self._test_status_field.stringValue())
        self._test_output.setString_(result.text)
        changes = "; ".join(f"{change.original} → {change.replacement}" for change in result.changes)
        count = len(result.changes)
        feedback = _w(f"应用了 {count} 处替换：", f"{count} {'replacement' if count == 1 else 'replacements'}: ") + changes if changes else _w("没有匹配的替换规则。请检查词语状态、错误写法与应用范围。", "No matching rules. Check enabled words, misspellings and app scope.")
        conflicts = [conflict for conflict in hotword_alias_conflicts(self._merged_entries(), app_info=app_info, scene=scene)
                     if any(re.search(_replacement_pattern(alias, canonical=False), text, re.IGNORECASE)
                            for alias in conflict["aliases"])]
        if conflicts:
            feedback = _conflict_message(conflicts) + _w("；请修改词条后重新测试。", "; edit the entries and test again.")
            self._set_status(feedback, error=True)
        self._changes_field.setStringValue_(feedback)
        self._changes_field.setToolTip_(feedback)
        return result

    def import_file(self, path):
        if Path(path).stat().st_size > 3 * 1024 * 1024:
            raise ValueError(_w("词典文件超过 3 MB，请分成多个文件导入。", "Dictionary file exceeds 3 MB. Split it into smaller files."))
        with open(path, encoding="utf-8") as source:
            entries = validate_hotword_import(json.load(source))
        count = self.hotwords.import_manual(entries)
        if count:
            self._notify_change()
        self.refresh()
        self._set_status(_w(f"已导入 {len(entries)} 个词语；相同标准拼写的条目已更新。", f"Imported {len(entries)} words. Matching spellings were updated."))
        return count

    def export_file(self, path):
        with open(path, "w", encoding="utf-8") as destination:
            json.dump(hotword_export_payload(self._merged_entries()), destination, ensure_ascii=False, indent=2)
            destination.write("\n")
        self._set_status(_w("词典已导出为 JSON 文件。", "Vocabulary exported as JSON."))

    def choose_import(self):
        panel = AppKit.NSOpenPanel.openPanel()
        panel.setAllowedFileTypes_(["json"])
        panel.setAllowsMultipleSelection_(False)
        panel.setCanChooseDirectories_(False)
        panel.setMessage_(_w("选择 SpeakType 导出的 JSON 词典。相同标准拼写的条目会更新。", "Choose an exported SpeakType JSON dictionary. Matching spellings will be updated."))
        if panel.runModal() != AppKit.NSModalResponseOK:
            return
        try:
            self.import_file(Path(panel.URL().path()))
        except (ValueError, TypeError, KeyError, OSError) as error:
            self._set_status(_w("导入失败：", "Import failed: ") + str(error), error=True)

    def choose_export(self):
        panel = AppKit.NSSavePanel.savePanel()
        panel.setAllowedFileTypes_(["json"])
        panel.setNameFieldStringValue_("SpeakType-vocabulary.json")
        if panel.runModal() != AppKit.NSModalResponseOK:
            return
        try:
            self.export_file(Path(panel.URL().path()))
        except OSError as error:
            self._set_status(_w("导出失败：", "Export failed: ") + str(error), error=True)
