"""Helpers for running AppleScript reliably under Finder-launched apps."""

from dataclasses import dataclass
import subprocess


@dataclass
class AppleScriptResult:
    returncode: int
    stdout: str
    stderr: str


def _decode_output(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def run_osascript(script: str, timeout: int = 2) -> AppleScriptResult:
    """Run AppleScript and decode output with a stable UTF-8 policy."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        timeout=timeout,
    )
    return AppleScriptResult(
        returncode=result.returncode,
        stdout=_decode_output(result.stdout),
        stderr=_decode_output(result.stderr),
    )
