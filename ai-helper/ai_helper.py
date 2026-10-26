"""AI 작업 도우미 — 비개발자가 작업 폴더를 고르고, GPT(Codex) 나 Claude(Claude Code)에게 말로 일을 시키는 프로그램.

- 화면은 index.html(노션 모양 · 반응형). 내 PC 안에서만 열리는 서버(127.0.0.1)를 띄우고 Edge 앱 창으로 연다.
- AI 는 고른 폴더 안의 파일(엑셀 포함)을 읽고 고친다. 폴더마다 [권한 승인]("바뀔 수 있다 · 백업 권장")을 받아야
  입력 칸이 열린다.
  · Codex: 윈도우 샌드박스(workspace-write)로 폴더 밖 쓰기가 막힌다(2026-10-26 실측)
  · Claude Code: 윈도우엔 샌드박스가 없다 — 파일 고치기는 폴더 안만 자동 허용, 명령은 `python` 만 허용한다
  · 엑셀은 python + openpyxl 로 고친다. 배포판엔 둘 다 들어 있다(build.py)
- 이어서 대화한다: 첫 답에서 받은 대화 번호로 이어 묻는다(Codex `exec resume`, Claude `--resume`).
- 로그인·Codex 설치는 「회의 메모 정리」와 같은 곳을 쓴다 — 둘 중 하나에서 한 번만 하면 된다.
- 프롬프트·확인한 폴더는 이 PC 에만 저장한다(%LOCALAPPDATA%\\ai_helper\\data.json).
"""
import ctypes
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import tarfile
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARED = Path(os.environ["LOCALAPPDATA"]) / "meeting_memo"            # 로그인·Codex 설치(회의 메모 정리와 같이 쓴다)
DATA = Path(os.environ["LOCALAPPDATA"]) / "ai_helper" / "data.json"   # 프롬프트·확인한 폴더
KNOWN = {"codex": [Path(os.environ["LOCALAPPDATA"]) / "Programs/OpenAI/Codex/bin/codex.exe",  # 공식 설치 스크립트
                   SHARED / "codex-cli/bin/codex.exe"],                                     # [설치]
         "claude": [Path.home() / ".local/bin/claude.exe"]}
MODELS = {"codex": "gpt-6.1-sol", "claude": "claude-opus-5-5"}
ENGINES = {"codex": "GPT-6.1-Sol (Codex)", "claude": "Claude Opus 5.5 (Claude Code)"}
HOME_VAR = {"codex": "CODEX_HOME", "claude": "CLAUDE_CONFIG_DIR"}
LOGIN = {"codex": ["login"], "claude": ["auth", "login", "--claudeai"]}
LOGOUT = {"codex": ["logout"], "claude": ["auth", "logout"]}
NO_WINDOW = subprocess.CREATE_NO_WINDOW
NEW_CONSOLE = subprocess.CREATE_NEW_CONSOLE
EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]

RULES = """너는 비개발자 직원의 파일 작업을 돕는다. 한국어로, 쉬운 말로 답한다.
- 작업 폴더({folder}) 안의 파일만 읽고 고친다. 폴더 밖은 건드리지 않는다.
- 엑셀(.xlsx)은 `python` 명령과 openpyxl 로 다룬다. 다른 프로그램은 설치하지 않는다.
- 파일을 바꿀 때는 무엇을 바꿀지 먼저 짧게 말하고, 다 바꾼 뒤 바꾼 파일과 내용을 목록으로 알려 준다.
- 파일 지우기는 꼭 필요할 때만 하고, 지운 파일을 알려 준다."""

SEED_PROMPTS = [
    {"title": "폴더 내용 요약", "body": "이 폴더에 있는 파일들을 훑어보고, 파일마다 무엇인지 한두 줄로 정리해 줘."},
    {"title": "엑셀 정리", "body": "(파일명).xlsx 의 (시트 이름) 시트에서 (할 일)을 해 줘. 바꾼 칸을 목록으로 알려 줘."},
    {"title": "문서 맞춤법 검사", "body": "(파일명) 문서의 맞춤법과 띄어쓰기를 고쳐 줘. 고친 곳을 목록으로 알려 줘."},
]

# 폴더 선택 창은 이 프로그램 창(AH_OWNER)에 딸린 창으로 띄운다 — 그냥 띄우면 뒤에서 도는 서버가 띄운 창이라
# 맨 앞으로 못 나오고 프로그램 창 뒤에 숨는다(2026-10-26 실측). 딸린 창은 언제나 주인 창 위에 뜬다.
# ★ 끝나기 전에 ReleaseHandle() 로 놓는다 — 붙잡은 채로 PowerShell 이 끝나면 .NET 이 그 창에 닫기를 보내
#   프로그램 창이 통째로 닫힌다(실측: 폴더를 고르고 [확인]을 누르면 앱이 꺼졌다).
PICK_FOLDER = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; Add-Type -AssemblyName System.Windows.Forms; "
               "$o = New-Object System.Windows.Forms.NativeWindow; "
               "if ($env:AH_OWNER) { $o.AssignHandle([IntPtr][long]$env:AH_OWNER) }; "
               "$d = New-Object System.Windows.Forms.FolderBrowserDialog -Property @{"
               "Description = 'AI 가 작업할 폴더를 고르세요'; ShowNewFolderButton = $true; SelectedPath = $env:AH_START}; "
               "$r = $d.ShowDialog($o); $o.ReleaseHandle(); if ($r -eq 'OK') { $d.SelectedPath }")
TITLE = "AI 작업 도우미"  # index.html 의 <title> — Edge 앱 창 제목이 된다


def app_window():
    """이 프로그램의 Edge 앱 창 핸들(없으면 0)."""
    user32, found = ctypes.windll.user32, []

    def check(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value == TITLE and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True
    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(check), 0)
    return found[0] if found else 0


# ── 도구 찾기·로그인 ──
def env_for(engine):
    home = SHARED / engine
    home.mkdir(parents=True, exist_ok=True)
    return {**os.environ, HOME_VAR[engine]: str(home)}


def find_exe(engine):
    # 방금 [설치] 로 깔았으면 이 프로세스의 PATH 에는 아직 없다 — 설치 위치를 직접 본다
    return shutil.which(engine) or next((str(p) for p in KNOWN[engine] if p.exists()), None)


def cli(engine, args, **kw):
    return subprocess.run([find_exe(engine), *args], env=env_for(engine), **kw)


def login_info(engine):
    """로그인돼 있으면 계정 표시(Claude 는 이메일, Codex 는 빈 문자열), 아니면 None."""
    if engine == "codex":
        r = cli(engine, ["login", "status"], capture_output=True, creationflags=NO_WINDOW)
        return "" if r.returncode == 0 and b"Logged in" in r.stdout + r.stderr else None
    try:
        info = json.loads(cli(engine, ["auth", "status"], capture_output=True, creationflags=NO_WINDOW).stdout)
    except ValueError:
        return None
    return info.get("email", "") if info.get("loggedIn") else None


PENDING = set()     # 로그인 창이 떠 있는 도구
INSTALLING = set()  # 설치하고 있는 도구
PROGRESS = {}       # 도구마다 설치 진행 {"step", "done", "total", "secs"} · 실패하면 {"error"}


def status(_=None):
    out = {}
    for engine in ENGINES:
        if not find_exe(engine):
            out[engine] = {"installed": False, "installing": engine in INSTALLING, "progress": PROGRESS.get(engine)}
            continue
        acct = login_info(engine)
        out[engine] = {"installed": True, "connected": acct is not None, "account": acct or "",
                       "pending": engine in PENDING}
    return out


def connect(data):
    engine = data["engine"]
    if engine not in PENDING and login_info(engine) is None:
        PENDING.add(engine)

        def run():
            try:
                cli(engine, LOGIN[engine], creationflags=NEW_CONSOLE)  # 브라우저가 열리고, 주소는 이 창에도 뜬다
            finally:
                PENDING.discard(engine)
        threading.Thread(target=run, daemon=True).start()
    return status()


def disconnect(data):
    cli(data["engine"], LOGOUT[data["engine"]], capture_output=True, creationflags=NO_WINDOW)
    return status()


# [설치]는 공식 PowerShell 설치 스크립트 대신 직접 받는다 — 그 스크립트는 1분 넘게 빈 창이고 어떤 PC 에서는
# 6분 넘게 받았다(회의 메모 정리 2026-10-26). 받는 곳·체크섬·마무리는 공식 스크립트와 같다.
def get(url, timeout=30):
    # releases.openai.com 은 파이썬 기본 User-Agent(Python-urllib)를 403 으로 막는다
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ai-helper"}), timeout=timeout)


def fetch(url, dest, engine):
    """받으면서 진행률을 PROGRESS 에 적고, 받은 파일의 sha256 을 돌려준다."""
    digest, done, started = hashlib.sha256(), 0, time.time()
    with get(url, timeout=60) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        while chunk := r.read(1 << 20):
            f.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            PROGRESS[engine] = {"step": "받는 중", "done": done, "total": total, "secs": time.time() - started}
    return digest.hexdigest()


def install_codex():
    arch = "aarch64" if platform.machine() == "ARM64" else "x86_64"
    meta = json.load(get("https://releases.openai.com/codex/channels/latest"))
    asset = next(a for a in meta["assets"] if a["name"] == f"codex-package-{arch}-pc-windows-msvc.tar.gz")
    archive = SHARED / asset["name"]
    if "sha256:" + fetch(asset["browser_download_url"], archive, "codex") != asset["digest"]:
        raise RuntimeError("받은 파일이 공식 체크섬과 다릅니다. 다시 눌러 주세요.")
    PROGRESS["codex"] = {"step": "푸는 중"}
    dest = KNOWN["codex"][1].parent.parent
    shutil.rmtree(dest, ignore_errors=True)
    with tarfile.open(archive) as t:
        t.extractall(dest, filter="data")
    archive.unlink()


def install_claude():
    base = "https://downloads.claude.ai/claude-code-releases"
    plat = "win32-arm64" if platform.machine() == "ARM64" else "win32-x64"
    version = get(f"{base}/latest").read().decode().strip()
    manifest = json.load(get(f"{base}/{version}/manifest.json"))
    exe = SHARED / "claude-download.exe"
    if fetch(f"{base}/{version}/{plat}/claude.exe", exe, "claude") != manifest["platforms"][plat]["checksum"]:
        raise RuntimeError("받은 파일이 공식 체크섬과 다릅니다. 다시 눌러 주세요.")
    PROGRESS["claude"] = {"step": "설치하는 중"}
    r = subprocess.run([str(exe), "install"], capture_output=True, timeout=300, creationflags=NO_WINDOW)
    time.sleep(1)  # 공식 스크립트처럼 파일이 놓일 때까지 잠깐 기다렸다 지운다
    exe.unlink(missing_ok=True)
    if r.returncode != 0:
        lines = (r.stderr + r.stdout).decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(lines[-1] if lines else f"종료 코드 {r.returncode}")


INSTALLERS = {"codex": install_codex, "claude": install_claude}


def install(data):
    engine = data["engine"]
    if engine not in INSTALLING and not find_exe(engine):
        INSTALLING.add(engine)
        PROGRESS[engine] = {"step": "준비 중"}

        def run():
            try:
                SHARED.mkdir(parents=True, exist_ok=True)
                INSTALLERS[engine]()
                PROGRESS.pop(engine, None)
            except Exception as e:
                PROGRESS[engine] = {"error": f"설치하지 못했습니다. {e}"}
            finally:
                INSTALLING.discard(engine)
        threading.Thread(target=run, daemon=True).start()
    return status()


# ── 프롬프트·폴더 ──
def load():
    try:
        return json.loads(DATA.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"prompts": SEED_PROMPTS, "confirmed": [], "folder": ""}


def store(d):
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def save_prompts(data):
    d = load()
    d["prompts"] = [{"title": p["title"].strip(), "body": p["body"]} for p in data["prompts"] if p["title"].strip()]
    return store(d)


def check_folder(raw):
    path = Path(raw.strip().strip('"')).expanduser()
    if not path.is_dir():
        raise RuntimeError("폴더를 찾을 수 없습니다. 경로를 확인해 주세요.")
    path = path.resolve()
    if path.parent == path or path == Path.home():  # AI 가 고칠 수 있는 범위가 너무 넓다
        raise RuntimeError("드라이브 전체나 사용자 폴더 전체는 고를 수 없습니다. 작업할 폴더를 골라 주세요.")
    return path


def set_folder(data):
    path, d = str(check_folder(data["path"])), load()
    d["folder"] = path
    if data.get("confirm") and path not in d["confirmed"]:
        d["confirmed"].append(path)
    store(d)
    return {"folder": path, "confirmed": path in d["confirmed"]}


def pick_folder(_):
    r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", PICK_FOLDER], capture_output=True,
                       env={**os.environ, "AH_START": load()["folder"], "AH_OWNER": str(app_window())},
                       creationflags=NO_WINDOW)
    return {"path": r.stdout.decode("utf-8", "replace").strip()}


# ── 대화 ──
CHATS = {}  # 대화 id → {"engine", "folder", "session", "messages", "running", "stopped", "started", "proc"}


def short(path, folder):
    try:
        return str(Path(path).resolve().relative_to(folder))
    except ValueError:
        return str(path)


def agent_env(engine):
    env = {**env_for(engine), "PYTHONUTF8": "1"}
    if (HERE / "python.exe").exists():  # 배포판: 동봉 파이썬(openpyxl 포함)을 `python` 으로 쓰게 한다
        env["PATH"] = f"{HERE};{env['PATH']}"
    return env


def codex_args(chat, out):
    # windows.sandbox 가 없으면 윈도우에선 workspace-write 를 줘도 read-only 로 돈다(2026-10-26 실측 — 사용자가
    # "읽기 전용이라 못 만든다"는 답을 받았다). unelevated = 관리자 권한 없이 도는 제한 토큰 샌드박스.
    common = ["--json", "-m", MODELS["codex"], "--skip-git-repo-check", "-o", str(out),
              "-c", 'sandbox_mode="workspace-write"', "-c", 'windows.sandbox="unelevated"',
              "-c", 'approval_policy="never"']
    if chat["session"]:
        return ["exec", "resume", *common, chat["session"], "-"]
    return ["exec", *common, "-C", chat["folder"], "-"]


def claude_args(chat):
    args = ["-p", "--model", MODELS["claude"], "--permission-mode", "acceptEdits",
            "--allowedTools", "Bash(python:*)", "PowerShell(python:*)",
            "--output-format", "stream-json", "--verbose",
            "--append-system-prompt", RULES.format(folder=chat["folder"])]
    return args + ["--resume", chat["session"]] if chat["session"] else args


FILE_TOOLS = {"Read": "읽음", "Edit": "고침", "MultiEdit": "고침", "Write": "만듦", "NotebookEdit": "고침"}


def claude_event(ev, msg, chat):
    chat["session"] = ev.get("session_id") or chat["session"]
    if ev.get("type") == "assistant":
        for b in ev["message"].get("content", []):
            if b.get("type") == "text" and b["text"].strip():
                msg["text"] = b["text"]  # 중간 글은 진행 중에 보이고, 끝나면 최종 답으로 바뀐다
            elif b.get("type") == "tool_use":
                name, inp = b["name"], b.get("input", {})
                if name in FILE_TOOLS:
                    act = (FILE_TOOLS[name], short(inp.get("file_path", ""), chat["folder"]))
                elif name in ("Glob", "Grep"):
                    act = ("찾음", inp.get("pattern", ""))
                elif name in ("Bash", "PowerShell"):
                    act = ("실행", inp.get("description") or inp.get("command", "")[:120])
                else:
                    act = ("도구", name)
                msg["activity"].append({"kind": act[0], "text": act[1]})
    elif ev.get("type") == "result":
        if ev.get("result"):
            msg["text"] = ev["result"]
        for denied in ev.get("permission_denials", []):
            msg["activity"].append({"kind": "막힘", "text": denied.get("tool_name", "")})
        if ev.get("is_error"):
            msg["error"] = ev.get("result") or "답을 받지 못했습니다."


def command_label(cmd):
    # Codex 는 명령을 "…powershell.exe" -Command '…' 로 감싸서 준다 — 껍데기를 벗겨 쉬운 말로 보여 준다
    inner = re.sub(r'^"?[^"]*powershell\.exe"?\s+-Command\s+', "", cmd, flags=re.IGNORECASE).strip("'\" ")
    if "openpyxl" in inner:
        return "엑셀 다루기(python)"
    if "python" in inner or "from pathlib" in inner:
        return "파일 다루기(python)"
    if re.match(r"(Get-ChildItem|dir|ls)\b", inner, re.IGNORECASE):
        return "파일 목록 보기"
    if re.match(r"(Set-Content|Add-Content|Out-File|New-Item)\b", inner, re.IGNORECASE):
        return "파일 쓰기"
    if re.match(r"(Get-Content|type|cat)\b", inner, re.IGNORECASE):
        return "파일 읽기"
    return " ".join(inner.split())[:100]


def codex_event(ev, msg, chat):
    kind, item = ev.get("type"), ev.get("item") or {}
    if kind == "thread.started":
        chat["session"] = ev.get("thread_id")
    elif kind == "item.completed":
        it = item.get("type")
        if it == "agent_message":
            msg["text"] = item.get("text", "")
        elif it == "command_execution":
            msg["activity"].append({"kind": "실행", "text": command_label(item.get("command", ""))})
        elif it == "file_change":
            for c in item.get("changes", []):
                label = {"add": "만듦", "delete": "지움"}.get(c.get("kind"), "고침")
                msg["activity"].append({"kind": label, "text": short(c.get("path", ""), chat["folder"])})
        elif it == "error":
            msg["activity"].append({"kind": "오류", "text": item.get("message", "")})
    elif kind in ("turn.failed", "error"):
        msg["error"] = (ev.get("error") or {}).get("message") or ev.get("message") or "답을 받지 못했습니다."


def run_turn(cid, text):
    chat = CHATS[cid]
    msg = {"role": "ai", "engine": chat["engine"], "text": "", "activity": [], "error": None}
    chat["messages"].append(msg)
    engine, first = chat["engine"], chat["session"] is None
    out, err = SHARED / f"answer-{cid}.md", SHARED / f"error-{cid}.txt"
    if engine == "codex":  # Codex 는 대화 첫 메시지에 규칙을 붙인다(이어 묻기는 기록에 남아 있다)
        args, prompt = codex_args(chat, out), (RULES.format(folder=chat["folder"]) + "\n\n" + text if first else text)
    else:
        args, prompt = claude_args(chat), text
    handle = codex_event if engine == "codex" else claude_event
    try:
        with open(err, "wb") as ef:
            p = subprocess.Popen([find_exe(engine), *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=ef,
                                 cwd=chat["folder"], env=agent_env(engine), creationflags=NO_WINDOW)
            chat["proc"] = p
            p.stdin.write(prompt.encode("utf-8"))
            p.stdin.close()
            for line in p.stdout:
                try:
                    handle(json.loads(line), msg, chat)
                except ValueError:
                    continue
            p.wait()
        if out.exists():
            msg["text"] = out.read_text(encoding="utf-8").strip() or msg["text"]
            out.unlink()
        if chat["stopped"]:
            msg["error"] = "중지했습니다."
        elif p.returncode != 0 and not msg["text"] and not msg["error"]:
            lines = err.read_text(encoding="utf-8", errors="replace").strip().splitlines()
            msg["error"] = lines[-1] if lines else f"종료 코드 {p.returncode}"
    except Exception as e:
        msg["error"] = str(e)
    finally:
        err.unlink(missing_ok=True)
        chat["running"], chat["proc"] = False, None


def chat_view(cid):
    chat = CHATS.get(cid)
    if not chat:
        return {"messages": [], "running": False}
    return {"messages": chat["messages"], "running": chat["running"], "engine": chat["engine"],
            "folder": chat["folder"], "secs": time.time() - chat["started"]}


def send(data):
    cid, text = data["chat"], data["text"].strip()
    if cid not in CHATS:  # 대화를 시작할 때 폴더·AI 가 정해지고, 대화 중에는 바뀌지 않는다
        CHATS[cid] = {"engine": data["engine"], "folder": str(check_folder(data["folder"])), "session": None,
                      "messages": [], "running": False, "stopped": False, "proc": None}
    chat = CHATS[cid]
    if chat["running"]:
        raise RuntimeError("아직 답을 기다리는 중입니다.")
    chat["messages"].append({"role": "user", "text": text})
    chat["running"], chat["stopped"], chat["started"] = True, False, time.time()
    threading.Thread(target=run_turn, args=(cid, text), daemon=True).start()
    return chat_view(cid)


def stop(data):
    chat = CHATS.get(data["chat"])
    if chat and chat["proc"]:
        chat["stopped"] = True  # AI 가 띄운 python 등도 같이 끈다
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(chat["proc"].pid)], capture_output=True,
                       creationflags=NO_WINDOW)
    return chat_view(data["chat"])


# ── 창이 살아 있는지 — 화면이 20초마다 ping, 닫힐 때 bye ──
seen = {"ping": None, "closing": None}


def ping(_):
    seen["ping"], seen["closing"] = time.time(), None
    return {}


def bye(_):
    seen["closing"] = time.time() + 5  # 새로고침이면 5초 안에 ping 이 다시 온다
    return {}


ROUTES = {"/api/connect": connect, "/api/disconnect": disconnect, "/api/install": install,
          "/api/prompts": save_prompts, "/api/folder": set_folder, "/api/pick-folder": pick_folder,
          "/api/send": send, "/api/stop": stop, "/api/ping": ping, "/api/bye": bye}


class Handler(BaseHTTPRequestHandler):
    host = token = ""

    def log_message(self, *args):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def allowed(self, need_token=True):
        # 다른 사이트가 이 서버를 부르지 못하게 — 주소(Host)와 켤 때마다 바뀌는 토큰을 같이 본다
        return self.headers.get("Host") == self.host and (not need_token or self.headers.get("X-Token") == self.token)

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path == "/" and self.allowed(need_token=False):
            html = (HERE / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", self.token)
            self.send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/icon.png" and self.allowed(need_token=False):
            self.send(200, (HERE / "icon.png").read_bytes(), "image/png")
        elif path == "/api/status" and self.allowed():
            self.send(200, status())
        elif path == "/api/data" and self.allowed():
            self.send(200, load())
        elif path == "/api/chat" and self.allowed():
            self.send(200, chat_view(query.removeprefix("id=")))
        else:
            self.send(404, {"error": "없는 주소입니다"})

    def do_POST(self):
        route = ROUTES.get(self.path)
        if not route or not self.allowed():
            return self.send(404, {"error": "없는 주소입니다"})
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        try:
            self.send(200, route(data))
        except Exception as e:
            self.send(500, {"error": str(e)})


def open_window(url):
    edge = next((p for p in EDGE if Path(p).exists()), None)
    if edge:
        subprocess.Popen([edge, f"--app={url}", "--window-size=1180,900"])
    else:
        webbrowser.open(url)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Handler.host = f"127.0.0.1:{server.server_port}"
    Handler.token = secrets.token_urlsafe(16)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    open_window(f"http://{Handler.host}/")
    started = time.time()
    while True:  # 창이 닫히면(bye 뒤 ping 없음) 끝낸다 · 1분 안에 창이 안 뜨거나 12시간 소식이 없어도 끝낸다
        time.sleep(1)
        now = time.time()
        if seen["closing"] and now > seen["closing"]:
            break
        if now - (seen["ping"] or started) > (12 * 3600 if seen["ping"] else 60):
            break
    for chat in CHATS.values():  # 창을 닫았는데 AI 가 일하고 있으면 같이 끈다
        if chat["proc"]:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(chat["proc"].pid)], capture_output=True,
                           creationflags=NO_WINDOW)


if __name__ == "__main__":
    main()
