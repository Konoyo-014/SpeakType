"""Local readiness diagnostics for SpeakType."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess
import requests

from .i18n import t
from .permissions import get_permission_status
from .model_download import is_model_cached
from .polish import NO_PROXY_FOR_LOCAL_OLLAMA
from .inserter import inspect_focused_input
from .context import get_active_app


OLLAMA_PATHS = (
    "/opt/homebrew/bin/ollama",
    "/usr/local/bin/ollama",
)


@dataclass(frozen=True)
class DiagnosticItem:
    key: str
    status: str
    title: str
    detail: str
    action: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _item(key: str, status: str, title_key: str, detail_key: str, action_key: str = "", **kwargs) -> DiagnosticItem:
    return DiagnosticItem(
        key=key,
        status=status,
        title=t(title_key),
        detail=t(detail_key, **kwargs),
        action=t(action_key, **kwargs) if action_key else "",
    )


def find_ollama_binary() -> str:
    for path in (shutil.which("ollama"), *OLLAMA_PATHS):
        if path and os.path.isfile(path):
            return path

    cellar = Path("/opt/homebrew/Cellar/ollama")
    if cellar.is_dir():
        for version_dir in sorted(cellar.iterdir(), reverse=True):
            candidate = version_dir / "bin" / "ollama"
            if candidate.is_file():
                return str(candidate)
    return ""


def _ollama_tags(ollama_url: str):
    resp = requests.get(
        f"{ollama_url.rstrip('/')}/api/tags",
        timeout=1.5,
        proxies=NO_PROXY_FOR_LOCAL_OLLAMA,
    )
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}"
    return resp.json().get("models", []), ""


def _ollama_service_status() -> str:
    brew = shutil.which("brew") or "/opt/homebrew/bin/brew"
    if not os.path.isfile(brew):
        return ""
    try:
        result = subprocess.run(
            [brew, "services", "list"],
            capture_output=True,
            text=True,
            timeout=2,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    for line in result.stdout.splitlines():
        if line.strip().startswith("ollama"):
            return " ".join(line.split())
    return ""


def run_readiness_checks(config: dict, asr_engine=None) -> list[DiagnosticItem]:
    items: list[DiagnosticItem] = []
    items.append(check_permissions())
    items.append(check_microphone())
    items.append(check_asr(config, asr_engine=asr_engine))
    items.extend(check_ollama(config))
    items.append(check_target_input())
    return items


def check_permissions() -> DiagnosticItem:
    try:
        status = get_permission_status()
    except Exception as e:
        return _item(
            "permissions",
            "fail",
            "diag_permissions_title",
            "diag_permissions_error",
            "diag_permissions_action",
            error=str(e),
        )

    missing = []
    if not status.accessibility:
        missing.append(t("perm_name_accessibility"))
    if not status.listen_event:
        missing.append(t("perm_name_input_monitoring"))
    if not status.post_event:
        missing.append(t("perm_name_post_event"))
    if not missing:
        return _item("permissions", "ok", "diag_permissions_title", "diag_permissions_ok")
    return _item(
        "permissions",
        "fail",
        "diag_permissions_title",
        "diag_permissions_missing",
        "diag_permissions_action",
        missing=" / ".join(missing),
    )


def check_microphone() -> DiagnosticItem:
    try:
        from .devices import list_input_devices

        devices = list_input_devices()
    except Exception as e:
        return _item(
            "microphone",
            "fail",
            "diag_microphone_title",
            "diag_microphone_error",
            "diag_microphone_action",
            error=str(e),
        )
    if devices:
        return _item(
            "microphone",
            "ok",
            "diag_microphone_title",
            "diag_microphone_ok",
            count=len(devices),
        )
    return _item(
        "microphone",
        "fail",
        "diag_microphone_title",
        "diag_microphone_missing",
        "diag_microphone_action",
    )


def check_asr(config: dict, asr_engine=None) -> DiagnosticItem:
    model = config.get("asr_model", "")
    loaded = bool(getattr(asr_engine, "_loaded", False)) if asr_engine is not None else False
    if loaded:
        return _item("asr", "ok", "diag_asr_title", "diag_asr_loaded", model=model)
    try:
        cached = is_model_cached(model)
    except Exception as e:
        return _item(
            "asr",
            "warn",
            "diag_asr_title",
            "diag_asr_cache_error",
            "diag_asr_action",
            model=model,
            error=str(e),
        )
    if cached:
        return _item("asr", "ok", "diag_asr_title", "diag_asr_cached", model=model)
    return _item(
        "asr",
        "warn",
        "diag_asr_title",
        "diag_asr_not_cached",
        "diag_asr_action",
        model=model,
    )


def check_ollama(config: dict) -> list[DiagnosticItem]:
    model = config.get("llm_model", "")
    url = config.get("ollama_url", "http://localhost:11434")
    binary = find_ollama_binary()
    items: list[DiagnosticItem] = []

    if binary:
        items.append(
            _item(
                "ollama_install",
                "ok",
                "diag_ollama_install_title",
                "diag_ollama_install_ok",
                path=binary,
            )
        )
    else:
        items.append(
            _item(
                "ollama_install",
                "warn",
                "diag_ollama_install_title",
                "diag_ollama_install_missing",
                "diag_ollama_install_action",
            )
        )
        items.append(
            _item(
                "ollama_service",
                "warn",
                "diag_ollama_service_title",
                "diag_ollama_service_missing_without_install",
                "diag_ollama_install_action",
                url=url,
            )
        )
        items.append(
            _item(
                "ollama_model",
                "warn",
                "diag_ollama_model_title",
                "diag_ollama_model_skipped",
                "diag_ollama_install_action",
                model=model,
            )
        )
        return items

    try:
        models, error = _ollama_tags(url)
    except Exception:
        service = _ollama_service_status()
        detail_key = "diag_ollama_service_missing"
        kwargs = {"url": url}
        if service:
            detail_key = "diag_ollama_service_missing_with_brew"
            kwargs["service"] = service
        items.append(
            _item(
                "ollama_service",
                "fail",
                "diag_ollama_service_title",
                detail_key,
                "diag_ollama_service_action",
                **kwargs,
            )
        )
        items.append(
            _item(
                "ollama_model",
                "warn",
                "diag_ollama_model_title",
                "diag_ollama_model_skipped",
                "diag_ollama_service_action",
                model=model,
            )
        )
        return items

    if models is None:
        items.append(
            _item(
                "ollama_service",
                "fail",
                "diag_ollama_service_title",
                "diag_ollama_service_error",
                "diag_ollama_service_action",
                url=url,
                error=error,
            )
        )
        items.append(
            _item(
                "ollama_model",
                "warn",
                "diag_ollama_model_title",
                "diag_ollama_model_skipped",
                "diag_ollama_service_action",
                model=model,
            )
        )
        return items

    items.append(
        _item(
            "ollama_service",
            "ok",
            "diag_ollama_service_title",
            "diag_ollama_service_ok",
            url=url,
        )
    )

    names = [m.get("name", "") for m in models]
    base = model.split(":")[0]
    if any(base in name for name in names):
        items.append(
            _item(
                "ollama_model",
                "ok",
                "diag_ollama_model_title",
                "diag_ollama_model_ok",
                model=model,
            )
        )
    else:
        items.append(
            _item(
                "ollama_model",
                "fail",
                "diag_ollama_model_title",
                "diag_ollama_model_missing",
                "diag_ollama_model_action",
                model=model,
            )
        )
    return items


def check_target_input() -> DiagnosticItem:
    try:
        app_info = get_active_app()
    except Exception:
        app_info = {}
    app_name = app_info.get("name", "") or t("diag_unknown_app")
    bundle_id = app_info.get("bundle_id", "") or ""
    try:
        diagnostic = inspect_focused_input(app_name=app_name, bundle_id=bundle_id)
    except Exception as e:
        return _item(
            "target_input",
            "warn",
            "diag_target_title",
            "diag_target_error",
            "diag_target_action",
            app=app_name,
            error=str(e),
        )

    if diagnostic.reason == "post_event_denied":
        return _item(
            "target_input",
            "fail",
            "diag_target_title",
            "diag_target_post_event_denied",
            "diag_permissions_action",
            app=app_name,
        )
    if not diagnostic.has_focused_element:
        return _item(
            "target_input",
            "warn",
            "diag_target_title",
            "diag_target_no_focus",
            "diag_target_action",
            app=app_name,
        )
    if diagnostic.likely_writable:
        return _item(
            "target_input",
            "ok",
            "diag_target_title",
            "diag_target_ok",
            app=app_name,
            role=diagnostic.role,
        )
    return _item(
        "target_input",
        "warn",
        "diag_target_title",
        "diag_target_not_writable",
        "diag_target_action",
        app=app_name,
        role=diagnostic.role,
    )


def render_diagnostics_text(items: list[DiagnosticItem]) -> str:
    lines = [t("diag_report_header"), ""]
    for item in items:
        mark = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}.get(item.status, item.status.upper())
        lines.append(f"[{mark}] {item.title}")
        lines.append(item.detail)
        if item.action:
            lines.append(f"{t('diag_action_prefix')} {item.action}")
        lines.append("")
    return "\n".join(lines).strip()
