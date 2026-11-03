import AppKit
from Foundation import NSMakeRect, NSMakeSize
from .design import apply_window, color


class HelpWindowController:
    def __init__(self, language="zh", hotkey="Right Command"):
        self.language = language
        self.hotkey = hotkey
        self.window = None

    def show(self):
        if self.window is None:
            self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(0, 0, 700, 590),
                AppKit.NSTitledWindowMask | AppKit.NSClosableWindowMask | AppKit.NSResizableWindowMask,
                AppKit.NSBackingStoreBuffered, False)
            self.window.setReleasedWhenClosed_(False)
            self.window.setTitle_("SpeakType 使用说明" if self.language == "zh" else "Using SpeakType")
            apply_window(self.window)
            self.window.center()
            scroll = AppKit.NSScrollView.alloc().initWithFrame_(NSMakeRect(24, 24, 652, 542))
            scroll.setHasVerticalScroller_(True)
            scroll.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
            text = AppKit.NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 630, 800))
            text.setEditable_(False)
            text.setSelectable_(True)
            text.setFont_(AppKit.NSFont.systemFontOfSize_(14))
            text.setTextColor_(color("text"))
            text.setBackgroundColor_(color("surface"))
            text.setTextContainerInset_(NSMakeSize(12, 14))
            text.setHorizontallyResizable_(False)
            text.setVerticallyResizable_(True)
            text.textContainer().setWidthTracksTextView_(True)
            if self.language == "zh":
                content = (
                    "准备好以后开始听写\n\n"
                    "打开“权限与模型准备”，允许麦克风、辅助功能和输入监控，然后下载语音模型。"
                    "润色与翻译使用可选的 Ollama 模型，可以在同一窗口下载、选择或关闭。\n\n"
                    "在其他应用中直接输入\n\n"
                    f"先点击需要输入文字的位置，再使用 {self.hotkey}。按住说话，松开后处理；"
                    "切换模式时，按一次开始，再按一次停止。应用会记住录音开始时的目标应用。\n\n"
                    "在 SpeakType 中录音和整理\n\n"
                    "点击主窗口的录音按钮，再次点击停止。原始转写和最终文本会出现在窗口中。"
                    "可以编辑最终文本、复制、重新润色，或选择翻译语言。选择目标应用后，点击插入按钮发送文字。\n\n"
                    "取消与恢复结果\n\n"
                    "录音、识别、润色和翻译期间可以取消。取消后，迟到的处理结果不会继续插入。"
                    "插入失败时，结果保留在主窗口和已开启的听写历史中，可以复制或重新选择目标。\n\n"
                    "撤销刚才的听写\n\n"
                    "说“撤销刚才”可以删除已验证的上一段听写。输入框、正文和光标必须保持插入后的状态。"
                    "移动光标或切换文档后，应用会保留当前文字。\n\n"
                    "让专名保持正确写法\n\n"
                    "打开“热词词典”，添加正确写法，并把常见误识别写法分别填写在独立行。"
                    "可以限制词条只用于某个应用，启用或停用词条，并用示例文本检查替换结果。"
                    "主窗口显示本次使用的热词提示和实际纠错；选中最终文本中的术语，可以直接保存词条。"
                    "词汇提示帮助识别专名，明确的错误写法会在识别后进行替换。"
                    "词条、错误写法和学习结果保存在本机。自动学习与历史保存分别由偏好设置控制。\n\n"
                    "历史与设置\n\n"
                    "最近记录位于主窗口，完整历史可以搜索、复制和导出。"
                    "偏好设置可以更改快捷键、录音模式、麦克风、语言和功能开关。"
                )
            else:
                content = (
                    "Get ready\n\nOpen Permissions and Models, allow microphone and input permissions, and download the speech model. "
                    "Ollama polishing and translation are optional; download, select, or disable them in the same window.\n\n"
                    f"Dictate into another app\n\nClick its input field and use {self.hotkey}. Hold to record and release to finish. "
                    "In toggle mode, press once to start and again to stop. SpeakType remembers the app selected when recording started.\n\n"
                    "Record and edit in SpeakType\n\nClick Record in the main window and click again to stop. "
                    "Read the original transcription, edit the final text, copy, polish again, or select a translation language. "
                    "Choose the target app and click Insert to deliver the text.\n\n"
                    "Cancel and recover\n\nCancel recording, transcription, polishing, or translation. Late results will not be inserted. "
                    "If insertion fails, text remains available in the main window and enabled history. Copy it or choose another target.\n\n"
                    "Undo a dictation\n\nSay undo that or scratch that to remove the last verified insertion while its field, text, and caret remain unchanged. "
                    "Moving the caret or switching documents preserves the current text.\n\n"
                    "Keep names spelled correctly\n\nOpen Vocabulary to add a preferred spelling and one common misspelling per line. "
                    "Limit an entry to an app, enable or pause it, and check replacement behavior with your own text. "
                    "The main window shows vocabulary hints and applied corrections. Select a term in the final text to save it. "
                    "Hints help recognition; explicit misspellings are replaced after recognition. "
                    "Entries and learning results stay on this Mac. Automatic learning and history have separate switches in Preferences.\n\n"
                    "History and settings\n\nRecent dictations appear in the main window. Full history supports search, copy, and export. "
                    "Preferences controls the shortcut, recording mode, microphone, languages, and optional features."
                )
            text.setString_(content)
            scroll.setDocumentView_(text)
            self.window.contentView().addSubview_(scroll)
        self.window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)

    def close(self):
        if self.window:
            self.window.orderOut_(None)
