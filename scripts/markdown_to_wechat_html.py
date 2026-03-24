#!/usr/bin/env python3
"""Convert Markdown to WeChat-ready HTML with local md2wechat and remote fallbacks."""
import os
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail

DEFAULT_DOOCS_URL = "https://md.doocs.org/#/"
DEFAULT_EDITOR_URL = "https://markdown.com.cn/editor/"
DEFAULT_TIMEOUT_MS = 15000
DEFAULT_POLL_INTERVAL_MS = 250
DEFAULT_STABLE_ROUNDS = 3
DEFAULT_CONVERSION_MODE = "auto"
DEFAULT_TYPESETTING_MODE = "default"
DEFAULT_CODE_THEME = "atom-one-dark"
DEFAULT_MD2WECHAT_BIN = "md2wechat"


@dataclass
class ConversionError(Exception):
    code: str
    message: str
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class RemoteProvider:
    name: str
    editor_url: str


DOOCS_MD_PROVIDER = RemoteProvider(name="doocs_md", editor_url=DEFAULT_DOOCS_URL)
MARKDOWN_EDITOR_PROVIDER = RemoteProvider(name="markdown.com.cn/editor", editor_url=DEFAULT_EDITOR_URL)
MD2WECHAT_AI_PROVIDER_NAME = "md2wechat_ai_mode"


class BrowserSession:
    def __init__(self, playwright, browser):
        self.playwright = playwright
        self.browser = browser

    def close(self):
        browser_error = None
        try:
            if self.browser is not None:
                self.browser.close()
        except Exception as exc:  # pragma: no cover - cleanup best effort
            browser_error = exc
        finally:
            if self.playwright is not None:
                try:
                    self.playwright.stop()
                except Exception:
                    pass
        if browser_error:
            raise browser_error


def default_browser_factory():
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.launch(headless=True)
    except Exception:
        playwright.stop()
        raise
    return BrowserSession(playwright, browser)


def set_markdown_markdown_editor(page, markdown: str) -> None:
    result = page.evaluate(
        """
        () => {
          const codeMirrorRoot = document.querySelector('.CodeMirror');
          if (!codeMirrorRoot || !codeMirrorRoot.CodeMirror) {
            return { status: 'input_not_found' };
          }
          return { status: 'ok' };
        }
        """
    )

    status = (result or {}).get("status")
    if status == "input_not_found":
        raise ConversionError("input_not_found", "Markdown input editor not found")
    if status != "ok":
        raise ConversionError("site_structure_changed", "Unexpected editor structure", {"result": result})

    page.click('.CodeMirror')
    page.keyboard.press('Meta+A')
    page.keyboard.press('Backspace')
    page.keyboard.type(markdown)


def set_markdown_doocs(page, markdown: str) -> None:
    result = page.evaluate(
        """
        () => {
          const editor = document.querySelector('div[role="textbox"].cm-content[contenteditable="true"]');
          if (!editor) {
            return { status: 'input_not_found' };
          }
          return { status: 'ok' };
        }
        """
    )

    status = (result or {}).get("status")
    if status == "input_not_found":
        raise ConversionError("input_not_found", "Doocs markdown input editor not found")
    if status != "ok":
        raise ConversionError("site_structure_changed", "Unexpected doocs editor structure", {"result": result})

    page.click('div[role="textbox"].cm-content[contenteditable="true"]')
    page.keyboard.press('Meta+A')
    page.keyboard.press('Backspace')
    page.keyboard.type(markdown)


def read_preview_state_markdown_editor(page) -> dict:
    result = page.evaluate(
        """
        () => {
          const preview = document.querySelector('#nice-rich-text-box') || document.querySelector('#nice');
          if (!preview) {
            return { status: 'preview_not_found' };
          }
          const html = preview.innerHTML || '';
          if (!html.trim()) {
            return { status: 'ok', html: '' };
          }
          return { status: 'ok', html };
        }
        """
    )

    if not isinstance(result, dict):
        raise ConversionError("site_structure_changed", "Unexpected preview response", {"result": result})
    return result


def read_preview_state_doocs(page) -> dict:
    result = page.evaluate(
        """
        () => {
          const preview = document.querySelector('#output');
          if (!preview) {
            return { status: 'preview_not_found' };
          }
          const html = preview.innerHTML || '';
          if (!html.trim()) {
            return { status: 'ok', html: '' };
          }
          return { status: 'ok', html };
        }
        """
    )

    if not isinstance(result, dict):
        raise ConversionError("site_structure_changed", "Unexpected doocs preview response", {"result": result})
    return result


def wait_for_stable_preview(page, timeout_ms=DEFAULT_TIMEOUT_MS, poll_interval_ms=DEFAULT_POLL_INTERVAL_MS, stable_rounds=DEFAULT_STABLE_ROUNDS, preview_reader: Optional[Callable] = None):
    if preview_reader is None:
        preview_reader = read_preview_state_markdown_editor

    deadline = time.monotonic() + timeout_ms / 1000
    last_html = None
    stable_count = 0

    while time.monotonic() < deadline:
        state = preview_reader(page)
        status = state.get("status")

        if status == "preview_not_found":
            raise ConversionError("preview_not_found", "Preview container not found")
        if status != "ok":
            raise ConversionError("site_structure_changed", "Unexpected preview state", {"state": state})

        html = (state.get("html") or "").strip()
        if html:
            if html == last_html:
                stable_count += 1
            else:
                last_html = html
                stable_count = 1

            if stable_count >= stable_rounds:
                return html

        time.sleep(poll_interval_ms / 1000)

    raise ConversionError("preview_timeout", "Preview did not stabilize before timeout", {"timeout_ms": timeout_ms})


def normalize_command(command) -> list[str]:
    if isinstance(command, str):
        return shlex.split(command)
    if isinstance(command, (list, tuple)):
        return [str(part) for part in command if str(part).strip()]
    raise ConversionError("invalid_param", "md2wechat_command must be a string or list", {"value": command})


def choose_typesetting_options(typesetting_mode: Optional[str], theme: Optional[str], code_theme: Optional[str], typesetting_spec: Optional[dict]) -> tuple[str, str]:
    spec = typesetting_spec or {}
    selected_theme = theme or spec.get("theme") or spec.get("typesetting_theme") or DEFAULT_TYPESETTING_MODE
    selected_code_theme = code_theme or spec.get("code_theme") or DEFAULT_CODE_THEME
    mode = (typesetting_mode or spec.get("mode") or spec.get("typesetting_mode") or selected_theme or DEFAULT_TYPESETTING_MODE).strip()

    if mode in {"default", "ai", "ai_default", "md2wechat_ai"}:
        selected_theme = "default"
    elif not selected_theme:
        selected_theme = DEFAULT_TYPESETTING_MODE

    return selected_theme, selected_code_theme


def resolve_md2wechat_command(md2wechat_command=None) -> list[str]:
    if md2wechat_command:
        return normalize_command(md2wechat_command)

    env_command = os.environ.get("MD2WECHAT_BIN")
    if env_command:
        return normalize_command(env_command)

    return [DEFAULT_MD2WECHAT_BIN]


def run_md2wechat_ai_mode(markdown: str, *, md2wechat_command=None, typesetting_mode: Optional[str] = None, theme: Optional[str] = None, code_theme: Optional[str] = None, typesetting_spec: Optional[dict] = None, command_runner: Callable = subprocess.run, **_unused_kwargs):
    command_prefix = resolve_md2wechat_command(md2wechat_command)
    selected_theme, selected_code_theme = choose_typesetting_options(typesetting_mode, theme, code_theme, typesetting_spec)

    with tempfile.TemporaryDirectory(prefix="md2wechat-") as temp_dir:
        input_path = Path(temp_dir) / "article.md"
        output_path = Path(temp_dir) / "article.html"
        input_path.write_text(markdown, encoding="utf-8")

        command = [
            *command_prefix,
            "convert",
            str(input_path),
            str(output_path),
            "--theme",
            selected_theme,
            "--code-theme",
            selected_code_theme,
        ]

        try:
            result = command_runner(command, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            raise ConversionError(
                "md2wechat_not_installed",
                "md2wechat command is not available",
                {"command": command_prefix, "error": str(exc)},
            )
        except Exception as exc:
            raise ConversionError(
                "md2wechat_launch_failed",
                "Failed to start md2wechat conversion",
                {"command": command_prefix, "error": str(exc)},
            )

        if result.returncode != 0:
            raise ConversionError(
                "md2wechat_convert_failed",
                "md2wechat conversion failed",
                {
                    "command": command,
                    "returncode": result.returncode,
                    "stdout": (result.stdout or "")[-1000:],
                    "stderr": (result.stderr or "")[-1000:],
                },
            )

        if not output_path.exists():
            raise ConversionError(
                "md2wechat_output_missing",
                "md2wechat did not produce an HTML file",
                {"command": command, "output_path": str(output_path)},
            )

        html = output_path.read_text(encoding="utf-8").strip()
        if not html:
            raise ConversionError(
                "md2wechat_empty_output",
                "md2wechat produced empty HTML",
                {"command": command, "output_path": str(output_path)},
            )

        return html


def run_remote_conversion(markdown: str, *, provider: RemoteProvider, browser_factory: Callable[[], object] = default_browser_factory, timeout_ms: int = DEFAULT_TIMEOUT_MS, poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS, stable_rounds: int = DEFAULT_STABLE_ROUNDS):
    session = None
    context = None
    try:
        try:
            session = browser_factory()
        except ConversionError:
            raise
        except Exception as exc:
            raise ConversionError("browser_launch_failed", "Failed to launch isolated browser", {"error": str(exc), "provider": provider.name})

        browser = getattr(session, "browser", session)
        context = browser.new_context()
        page = context.new_page()

        try:
            page.goto(provider.editor_url, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception as exc:
            raise ConversionError("page_unreachable", "Editor page could not be reached", {"url": provider.editor_url, "error": str(exc), "provider": provider.name})

        if provider.name == DOOCS_MD_PROVIDER.name:
            set_markdown_doocs(page, markdown)
            preview_reader = read_preview_state_doocs
        elif provider.name == MARKDOWN_EDITOR_PROVIDER.name:
            set_markdown_markdown_editor(page, markdown)
            preview_reader = read_preview_state_markdown_editor
        else:
            raise ConversionError("provider_not_supported", "Unsupported conversion provider", {"provider": provider.name})

        return wait_for_stable_preview(
            page,
            timeout_ms=timeout_ms,
            poll_interval_ms=poll_interval_ms,
            stable_rounds=stable_rounds,
            preview_reader=preview_reader,
        )
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if session is not None:
            try:
                close = getattr(session, "close")
                close()
            except Exception:
                pass


def run_primary_conversion(markdown: str, **kwargs):
    return run_remote_conversion(markdown, provider=MARKDOWN_EDITOR_PROVIDER, **kwargs)


def run_doocs_conversion(markdown: str, **kwargs):
    return run_remote_conversion(markdown, provider=DOOCS_MD_PROVIDER, **kwargs)


def build_conversion_routes(*, conversion_mode: str, local_converters: Optional[list], remote_converters: Optional[list], converter: Optional[Callable[..., str]]):
    normalized_mode = (conversion_mode or DEFAULT_CONVERSION_MODE).strip().lower()

    effective_local_converters = list(local_converters or [])
    effective_remote_converters = list(remote_converters or [])

    if not effective_remote_converters:
        if converter is not None:
            effective_remote_converters = [(MARKDOWN_EDITOR_PROVIDER.name, converter)]
        else:
            effective_remote_converters = [
                (DOOCS_MD_PROVIDER.name, run_doocs_conversion),
                (MARKDOWN_EDITOR_PROVIDER.name, run_primary_conversion),
            ]

    if normalized_mode in {"auto", "md2wechat", "md2wechat_ai", "local_only"} and local_converters is None and not effective_remote_converters and converter is None:
        effective_local_converters = [(MD2WECHAT_AI_PROVIDER_NAME, run_md2wechat_ai_mode)]

    if normalized_mode == "browser_remote":
        return effective_remote_converters
    if normalized_mode == "local_only":
        return effective_local_converters
    return [*effective_local_converters, *effective_remote_converters]


def convert_markdown_to_wechat_html(markdown: str, fallback_html: Optional[str] = None, *, converter: Optional[Callable[..., str]] = None, local_converters: Optional[list] = None, remote_converters: Optional[list] = None, conversion_mode: str = DEFAULT_CONVERSION_MODE, **converter_kwargs):
    conversion_routes = build_conversion_routes(
        conversion_mode=conversion_mode,
        local_converters=local_converters,
        remote_converters=remote_converters,
        converter=converter,
    )

    last_error = None
    for provider_name, provider_converter in conversion_routes:
        try:
            html = provider_converter(markdown, **converter_kwargs)
            return {
                "wechat_html": html,
                "conversion_path": provider_name,
                "fallback_reason": None,
            }
        except ConversionError as exc:
            details = dict(exc.details or {})
            details.setdefault("provider", provider_name)
            last_error = ConversionError(exc.code, exc.message, details)

    if fallback_html and last_error is not None:
        return {
            "wechat_html": fallback_html,
            "conversion_path": "fallback_local_html",
            "fallback_reason": {
                "code": last_error.code,
                "message": last_error.message,
                "details": last_error.details,
                "provider": last_error.details.get("provider"),
            },
        }

    if last_error is not None:
        raise last_error

    raise ConversionError("no_converter_configured", "No markdown conversion route configured")


def main():
    inp = read_stdin()
    markdown = inp.get("markdown", "")
    fallback_html = inp.get("fallback_html")
    doocs_url = inp.get("doocs_url", DEFAULT_DOOCS_URL)
    editor_url = inp.get("editor_url", DEFAULT_EDITOR_URL)
    timeout_ms = int(inp.get("timeout_ms", DEFAULT_TIMEOUT_MS))
    poll_interval_ms = int(inp.get("poll_interval_ms", DEFAULT_POLL_INTERVAL_MS))
    stable_rounds = int(inp.get("stable_rounds", DEFAULT_STABLE_ROUNDS))
    conversion_mode = inp.get("conversion_mode", DEFAULT_CONVERSION_MODE)
    typesetting_mode = inp.get("typesetting_mode") or inp.get("typesetting_style") or DEFAULT_TYPESETTING_MODE
    theme = inp.get("theme")
    code_theme = inp.get("code_theme")
    typesetting_spec = inp.get("typesetting_spec") or {}
    md2wechat_command = inp.get("md2wechat_command")

    if not markdown.strip():
        fail("invalid_param", "markdown is required")

    doocs_provider = RemoteProvider(name=DOOCS_MD_PROVIDER.name, editor_url=doocs_url)
    editor_provider = RemoteProvider(name=MARKDOWN_EDITOR_PROVIDER.name, editor_url=editor_url)

    remote_converters = [
        (
            doocs_provider.name,
            lambda content, **kwargs: run_remote_conversion(content, provider=doocs_provider, **kwargs),
        ),
        (
            editor_provider.name,
            lambda content, **kwargs: run_remote_conversion(content, provider=editor_provider, **kwargs),
        ),
    ]

    local_converters = [
        (
            MD2WECHAT_AI_PROVIDER_NAME,
            lambda content, **kwargs: run_md2wechat_ai_mode(content, **kwargs),
        )
    ]

    try:
        result = convert_markdown_to_wechat_html(
            markdown,
            fallback_html=fallback_html,
            local_converters=local_converters,
            remote_converters=remote_converters,
            conversion_mode=conversion_mode,
            timeout_ms=timeout_ms,
            poll_interval_ms=poll_interval_ms,
            stable_rounds=stable_rounds,
            typesetting_mode=typesetting_mode,
            theme=theme,
            code_theme=code_theme,
            typesetting_spec=typesetting_spec,
            md2wechat_command=md2wechat_command,
        )
    except ConversionError as exc:
        fail(exc.code, exc.message, exc.details)

    ok(result)


if __name__ == "__main__":
    main()
