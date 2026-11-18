"""Loopback HTTP bridge to the existing LCSC_Kicad_import converter.

Run without arguments to serve; ``--import C2040`` converts once and exits;
``--setup`` re-runs the first-run wizard. Configuration lives in
``%LOCALAPPDATA%\\LCSCKiCadBridge\\config.json`` (Windows) unless ``--config``
or ``LCSC_BRIDGE_CONFIG`` points elsewhere.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

VERSION = "1.3.0"
MAX_BODY_BYTES = 8192
FROZEN = bool(getattr(sys, "frozen", False))
APP_DIR_NAME = "LCSCKiCadBridge"
IMPORT_LOCK = threading.Lock()
DIALOG_LOCK = threading.Lock()
Importer = Callable[[str, str, list[str]], Any]
ORIGIN_RE = re.compile(r"(?:chrome|edge)-extension://[A-Za-z0-9_-]{1,64}")
ID_RE = re.compile(r"C[1-9][0-9]{0,30}")


SETTINGS_PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>LCSC → KiCad 设置</title>
<style>
body{max-width:640px;margin:40px auto;padding:0 20px;font:15px/1.6 system-ui,sans-serif;color:#1f2937}
h1{font-size:20px;margin:0 0 20px}
code{background:#eef2f7;padding:2px 6px;border-radius:4px}
.row{display:flex;gap:8px;align-items:center;margin:10px 0}
input{flex:1;padding:8px 10px;border:1px solid #94a3b8;border-radius:6px;font:inherit}
button{padding:8px 14px;border:0;border-radius:6px;background:#0759b5;color:#fff;font:inherit;cursor:pointer}
button.secondary{background:#e2e8f0;color:#1f2937}
#status{color:#475569}
.hint{color:#64748b;font-size:13px}
</style></head>
<body>
<h1>LCSC → KiCad</h1>
<p>当前工程：<code id="current">读取中…</code></p>
<p><label for="path">工程目录</label></p>
<div class="row">
  <input id="path" spellcheck="false" placeholder="D:/work/demo">
  <button id="pick" class="secondary" type="button">选择文件夹</button>
</div>
<div class="row">
  <button id="save" type="button">保存</button>
  <span id="status" role="status"></span>
</div>
<p class="hint">保存后立即生效，不需要重启服务。目录里要有 .kicad_pro；已经打开的 KiCad 编辑器要重开一次才能看到新库表。</p>
<script>
const $ = (id) => document.getElementById(id);
async function call(path, options) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) throw new Error(data.error || "HTTP " + response.status);
  return data;
}
async function refresh() {
  try {
    const data = await call("/health");
    $("current").textContent = data.project_dir;
    if (!$("path").value) $("path").value = data.project_dir;
  } catch (error) { $("status").textContent = error.message; }
}
$("pick").onclick = async () => {
  $("status").textContent = "等待选择…";
  try {
    const data = await call("/api/pick-folder", {method: "POST"});
    $("status").textContent = "";
    if (data.path) $("path").value = data.path;
  } catch (error) { $("status").textContent = error.message; }
};
$("save").onclick = async () => {
  try {
    const data = await call("/api/config", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({project_dir: $("path").value.trim()}),
    });
    $("current").textContent = data.project_dir;
    $("status").textContent = data.has_project ? "已保存" : "已保存，但该目录没有 .kicad_pro";
  } catch (error) { $("status").textContent = error.message; }
};
refresh();
</script>
</body></html>"""


class ConfigError(Exception):
    """A startup problem the user can fix by editing the config or picking a folder."""


def default_config_path() -> Path:
    override = os.environ.get("LCSC_BRIDGE_CONFIG")
    if override:
        return Path(override).expanduser()
    if not FROZEN:
        beside_script = Path(__file__).resolve().with_name("config.json")
        if beside_script.exists():
            return beside_script
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / APP_DIR_NAME / "config.json"


def _default_import_dir() -> str:
    """Find the pinned converter submodule, falling back to a sibling clone."""
    root = Path(__file__).resolve().parent.parent
    candidates = [root / "vendor" / "LCSC_Kicad_import", root.parent / "LCSC_Kicad_import"]
    for candidate in candidates:
        if (candidate / "plugins" / "lcsc_project_import.py").is_file():
            return candidate.as_posix()
    return ""


def _write_config(path: Path, project_dir: str, port: int, import_dir: str) -> dict[str, Any]:
    config = {
        "port": port,
        "project_dir": project_dir,
        # Empty by default: the /import gate is the caller Origin, so nothing to copy.
        "token": "",
        "kicad_import_dir": import_dir,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return config


def _interactive() -> bool:
    """True only on a real Windows console (a pipe or NUL handle is not enough)."""
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        mode = ctypes.c_uint()
        for handle in (-11, -12):  # STD_INPUT_HANDLE, STD_OUTPUT_HANDLE
            if kernel32.GetConsoleMode(kernel32.GetStdHandle(handle), ctypes.byref(mode)):
                return True
        return False
    return sys.stdin.isatty() and sys.stdout.isatty()


def _tkinter():
    try:
        import tkinter as tk
    except ImportError as exc:  # Linux without python3-tk, minimal macOS installs
        raise ConfigError(
            f"当前 Python 没有 tkinter，无法弹出选择窗口（{exc}）。"
            "请安装 python3-tk（Linux），或用 --project 指定工程目录。"
        ) from exc
    return tk


def _ask_folder(title: str) -> str:
    tk = _tkinter()
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        return filedialog.askdirectory(title=title, mustexist=True)
    finally:
        root.destroy()


def _ask_port(default: int) -> int:
    tk = _tkinter()
    from tkinter import simpledialog

    root = tk.Tk()
    root.withdraw()
    try:
        value = simpledialog.askinteger(
            "LCSC KiCad Bridge", f"本地服务端口（默认 {default}）", initialvalue=default,
            minvalue=1024, maxvalue=65535,
        )
    finally:
        root.destroy()
    return int(value or default)


def wizard(path: Path, port: int | None = None) -> dict[str, Any]:
    """Ask for the KiCad project folder and save a fresh config."""
    try:
        folder = _ask_folder("选择 KiCad 工程目录（含 .kicad_pro）")
    except Exception as exc:  # tkinter missing or headless session
        raise ConfigError(f"无法打开选择窗口（{exc}）；请用 --project 指定工程目录。") from exc
    if not folder:
        raise ConfigError("已取消：请用 --project 指定 KiCad 工程目录。")
    project = Path(folder)
    if not project.is_dir():
        raise ConfigError(f"目录不存在：{project}")
    if not any(project.glob("*.kicad_pro")):
        raise ConfigError(f"{project} 内没有 .kicad_pro；请选择 KiCad 工程目录。")
    chosen_port = _ask_port(port or 8737)
    config = _write_config(path, project.as_posix(), chosen_port, _default_import_dir())
    print(f"已保存配置：{path}", flush=True)
    return config


def load_config(path: Path, project_override: str | None = None) -> dict[str, Any]:
    if not path.exists():
        if project_override is not None:
            config = _write_config(path, project_override, 8737, _default_import_dir())
            print(f"已保存配置：{path}", flush=True)
            return config
        if not _interactive():
            raise ConfigError(
                f"没有配置文件：{path}。首次运行请在图形界面双击启动，或用 --project 指定工程目录。"
            )
        return wizard(path)
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"配置无法读取：{path}（{exc}）。用 --setup 重新生成。") from exc
    if not isinstance(config, dict):
        raise ConfigError(f"配置必须是 JSON 对象：{path}")
    if project_override:
        config["project_dir"] = project_override
    return config


def validate_config(config: Mapping[str, Any], *, require_converter: bool) -> dict[str, Any]:
    port = config.get("port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ConfigError("配置中的 port 必须是 1–65535 的整数。")
    project_value = config.get("project_dir")
    if not isinstance(project_value, str) or not project_value.strip():
        raise ConfigError("配置缺少 project_dir；用 --setup 选择 KiCad 工程目录。")
    project_dir = Path(project_value).expanduser().resolve()
    if not project_dir.is_dir():
        raise ConfigError(f"project_dir 不存在：{project_dir}；用 --setup 重新选择。")
    token = config.get("token")
    token = token.strip() if isinstance(token, str) else ""
    import_value = config.get("kicad_import_dir")
    import_value = import_value.strip() if isinstance(import_value, str) else ""
    if require_converter:
        if not import_value:
            import_value = _default_import_dir()
        if not import_value:
            raise ConfigError("配置缺少 kicad_import_dir；用 --setup 重新生成。")
        module_path = Path(import_value).expanduser().resolve() / "plugins" / "lcsc_project_import.py"
        if not module_path.is_file():
            raise ConfigError(f"转换器缺失：{module_path}；重新 clone LCSC_Kicad_import 或用 --setup。")
    return {
        **config,
        "port": port,
        "project_dir": str(project_dir),
        "kicad_import_dir": import_value,
        "token": token,
    }


class LazyImporter:
    """The sole adapter that loads and calls the external conversion core."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = config
        self._convert: Callable[..., Any] | None = None

    def resolve(self) -> Callable[..., Any]:
        if self._convert is None:
            if not FROZEN:
                plugins = str(Path(self.config["kicad_import_dir"]) / "plugins")
                if plugins not in sys.path:
                    sys.path.insert(0, plugins)
            module = importlib.import_module("lcsc_project_import")
            convert = getattr(module, "import_component_to_project")
            if not callable(convert):
                raise TypeError("lcsc_project_import.import_component_to_project is not callable")
            self._convert = convert
        return self._convert

    def __call__(self, lcsc_id: str, project_dir: str, log: list[str]) -> Any:
        def capture(*values: Any, sep: str = " ", end: str = "\n") -> None:
            text = sep.join(str(value) for value in values)
            log.extend(text.splitlines() or [""])

        return self.resolve()(lcsc_id, Path(project_dir), capture)


class BridgeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, config: Mapping[str, Any], importer: Importer,
                 config_path: Path | None = None) -> None:
        self.config = dict(config)
        self.importer = importer
        self.config_path = config_path
        super().__init__(("127.0.0.1", config["port"]), BridgeHandler)


class BridgeHandler(BaseHTTPRequestHandler):
    server: BridgeHTTPServer

    def handle_one_request(self) -> None:
        self._started_at = time.perf_counter()
        self._response_status: int | None = None
        try:
            super().handle_one_request()
        finally:
            if self._response_status is not None:
                duration = (time.perf_counter() - self._started_at) * 1000
                method = json.dumps(getattr(self, "command", ""), ensure_ascii=False)
                path = json.dumps(getattr(self, "path", ""), ensure_ascii=False)
                stamp = datetime.now().astimezone().isoformat(timespec="seconds")
                print(f"{stamp} {method} {path} {self._response_status} {duration:.1f} ms", flush=True)

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Request logging is handled above with timing.

    def send_response(self, code: int, message: str | None = None) -> None:
        self._response_status = code
        super().send_response(code, message)

    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if ORIGIN_RE.fullmatch(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "content-type, x-bridge-token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Vary", "Origin")

    def _json(self, status: int, payload: Mapping[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: int, message: str, log: list[str] | None = None) -> None:
        self._json(status, {"ok": False, "error": message, "log": log or []})

    def _authorized(self) -> bool:
        """A configured token wins; otherwise only extension/no-Origin callers pass."""
        token = self.server.config["token"]
        supplied = self.headers.get("X-Bridge-Token", "").strip()
        if token:
            return bool(supplied) and supplied == token
        origin = self.headers.get("Origin")
        return origin is None or bool(ORIGIN_RE.fullmatch(origin))

    def _body(self) -> dict[str, Any]:
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Use a JSON body with Content-Length; transfer encoding is not supported.")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not re.fullmatch(r"[0-9]+", lengths[0]):
            raise ValueError("A valid Content-Length is required.")
        length_text = lengths[0].lstrip("0") or "0"
        if len(length_text) > 4 or int(length_text) > MAX_BODY_BYTES:
            raise ValueError("Request body exceeds 8192 bytes.")
        raw = self.rfile.read(int(length_text))
        body = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(body, dict):
            raise ValueError("Body must be a JSON object.")
        return body

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _caller_is_local_page(self) -> bool:
        """Same-origin pages served by this service, extensions, or local tools."""
        origin = self.headers.get("Origin")
        if origin is None or ORIGIN_RE.fullmatch(origin):
            return True
        port = self.server.server_port
        return origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")

    def _project_info(self) -> dict[str, Any]:
        directory = Path(self.server.config["project_dir"])
        has_project = any(directory.glob("*.kicad_pro"))
        return {"project_dir": directory.as_posix(), "has_project": has_project}

    def _save_project_dir(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("请填写工程目录。")
        directory = Path(value.strip()).expanduser()
        if not directory.is_dir():
            raise ValueError(f"目录不存在：{directory}")
        directory = directory.resolve()
        self.server.config["project_dir"] = str(directory)
        config_path = self.server.config_path
        if config_path is not None:
            data: dict[str, Any] = {}
            try:
                loaded = json.loads(config_path.read_text(encoding="utf-8-sig"))
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, ValueError):
                pass
            data.update({
                "port": self.server.config["port"],
                "project_dir": directory.as_posix(),
                "token": self.server.config["token"],
                "kicad_import_dir": self.server.config["kicad_import_dir"],
            })
            temporary = config_path.with_name(config_path.name + ".tmp")
            temporary.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8", newline="\n",
            )
            os.replace(temporary, config_path)
        return self._project_info()

    def _pick_folder(self) -> str:
        if not DIALOG_LOCK.acquire(blocking=False):
            raise RuntimeError("另一个选择窗口还开着。")
        try:
            return _ask_folder("选择 KiCad 工程目录")
        finally:
            DIALOG_LOCK.release()

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in ("/", "/settings"):
            body = SETTINGS_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path != "/health":
            self._error(404, "Endpoint not found.")
            return
        self._json(200, {
            "ok": True,
            "version": VERSION,
            "project_dir": self.server.config["project_dir"],
            "token_required": bool(self.server.config["token"]),
        })

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path in ("/api/config", "/api/pick-folder"):
            if not self._caller_is_local_page():
                self._error(401, "Only the local settings page or the extension may change settings.")
                return
            try:
                if path == "/api/pick-folder":
                    folder = self._pick_folder()
                    if not folder:
                        self._error(400, "没有选择文件夹。")
                        return
                    self._json(200, {"ok": True, "path": Path(folder).as_posix()})
                    return
                body = self._body()
                self._json(200, {"ok": True, **self._save_project_dir(body.get("project_dir"))})
            except (ValueError, UnicodeError, OSError) as exc:
                self._error(400, str(exc) or type(exc).__name__)
            except Exception as exc:
                self._error(500, str(exc) or type(exc).__name__)
            return
        if path != "/import":
            self._error(404, "Endpoint not found.")
            return
        if not self._authorized():
            self._error(401, "Unauthorized: configure the token from config.json or call from the extension.")
            return
        if not IMPORT_LOCK.acquire(blocking=False):
            self._error(409, "Another import is in progress; please retry later.")
            return
        log: list[str] = []
        try:
            try:
                body = self._body()
            except (ValueError, UnicodeError) as exc:
                self._error(400, f"Invalid JSON body: {exc}")
                return
            lcsc_id = body.get("lcsc_id")
            if not isinstance(lcsc_id, str) or not ID_RE.fullmatch(lcsc_id.strip().upper()):
                self._error(400, "lcsc_id must look like C2040.")
                return
            lcsc_id = lcsc_id.strip().upper()
            try:
                result = self.server.importer(lcsc_id, self.server.config["project_dir"], log)
            except Exception as exc:
                self._error(500, str(exc) or type(exc).__name__, log)
                return
            self._json(200, {
                "ok": True,
                "lcsc_id": lcsc_id,
                "installed": True,
                "already_present": bool(result.already_present),
                "has_3d": bool(result.has_3d),
                "directory": str(Path(result.directory).resolve()),
                "log": log,
            })
        finally:
            IMPORT_LOCK.release()


def build_server(config: Mapping[str, Any], importer: Importer | None = None,
                 config_path: Path | None = None) -> BridgeHTTPServer:
    return BridgeHTTPServer(
        config, importer if importer is not None else LazyImporter(config), config_path
    )


def run_import(config: Mapping[str, Any], lcsc_id: str) -> int:
    log: list[str] = []
    result = LazyImporter(config)(lcsc_id.strip().upper(), config["project_dir"], log)
    for line in log:
        print(line, flush=True)
    print(f"已导入 {result.component_id} → {result.directory}（3D 模型：{'有' if result.has_3d else '无'}）",
          flush=True)
    return 0


def _utf8_pipes() -> None:
    """Keep logs readable when stdout/stderr are captured instead of a console."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if not stream.isatty():
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    _utf8_pipes()
    parser = argparse.ArgumentParser(description="LCSC KiCad Bridge loopback service")
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--project", help="KiCad project folder (overrides config)")
    parser.add_argument("--setup", action="store_true", help="re-run the first-run wizard")
    parser.add_argument("--check", action="store_true", help="validate config and converter, then exit")
    parser.add_argument("--import", dest="lcsc_id", metavar="C2040", help="convert one part and exit")
    args = parser.parse_args(argv)
    try:
        if args.setup:
            config = wizard(args.config, port=_peek_port(args.config))
        else:
            config = load_config(args.config, args.project)
        config = validate_config(config, require_converter=not FROZEN)
        if args.check:
            LazyImporter(config).resolve()
            print(f"配置与转换器正常：{args.config}；project_dir={config['project_dir']}", flush=True)
            return 0
        if args.lcsc_id:
            return run_import(config, args.lcsc_id)
        importer = LazyImporter(config)
        with build_server(config, importer=importer, config_path=args.config) as server:
            print(f"listening on http://127.0.0.1:{server.server_port}", flush=True)
            print(f"工程目录：{config['project_dir']}", flush=True)
            print(f"切换工程：http://127.0.0.1:{server.server_port}/settings", flush=True)
            print("保持此窗口开启；关闭窗口即停止服务。Ctrl-C 退出。", flush=True)
            try:
                server.serve_forever(poll_interval=0.25)
            except KeyboardInterrupt:
                print("\nBridge stopped.", flush=True)
        return 0
    except KeyboardInterrupt:
        return 0
    except ConfigError as exc:
        print(f"未启动：{exc}", file=sys.stderr, flush=True)
        return 2
    except Exception as exc:
        print(f"启动失败：{exc}", file=sys.stderr, flush=True)
        return 1


def _peek_port(path: Path) -> int:
    try:
        return int(json.loads(path.read_text(encoding="utf-8-sig")).get("port", 8737))
    except Exception:
        return 8737


if __name__ == "__main__":
    sys.exit(main())
