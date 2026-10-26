"""회의 메모 정리 — 회의 메모를 쓰고 [정리 파일 생성] 을 누르면 GPT(Codex) 나 Claude(Claude Code)가
회의록으로 정리해 바탕화면에 .md 로 저장한다.

- 화면은 index.html(노션 모양 · 반응형)이다. 이 파일이 내 PC 안에서만 열리는 서버(127.0.0.1)를 띄우고
  Edge 를 주소창 없는 앱 창으로 연다. 창을 닫으면 서버도 몇 초 안에 내려간다.
- 정리 방식은 이 폴더의 AGENTS.md 에 있다. Codex 는 AGENTS.md 를, Claude Code 는 CLAUDE.md(→ AGENTS.md)를
  작업 폴더에서 저절로 읽는다 — 그래서 두 도구 모두 이 폴더를 작업 폴더로 돌린다.
- 로그인은 이 프로그램 전용 폴더(%LOCALAPPDATA%\\meeting_memo)에 따로 둔다 — [연결 해제]·다른 계정 연결을
  해도 VS Code 의 Codex·Claude Code 로그인은 그대로다.
- 배포판은 build.py 가 만든다(파이썬 동봉 · 「회의 메모 정리.exe」 더블클릭). 왜 그렇게 나눠 주는지는 build.py 머리말.
"""
import ctypes
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent                       # AGENTS.md·CLAUDE.md·index.html 이 있는 작업 폴더
APPDIR = Path(os.environ["LOCALAPPDATA"]) / "meeting_memo"   # 이 프로그램 전용 로그인
PACKAGED_EXE = "회의 메모 정리.exe"                            # 배포판의 실행 파일(이름만 바꾼 pythonw.exe)
KNOWN = {"codex": Path(os.environ["LOCALAPPDATA"]) / "Programs/OpenAI/Codex/bin/codex.exe",
         "claude": Path.home() / ".local/bin/claude.exe"}     # 공식 설치 스크립트가 까는 곳
INSTALL = {"codex": "irm https://chatgpt.com/codex/install.ps1 | iex",
           "claude": "irm https://claude.ai/install.ps1 | iex"}  # 두 회사의 공식 설치 명령
MODELS = {"codex": "gpt-6.1-sol", "claude": "claude-opus-5-5"}
ENGINES = {"codex": "GPT-6.1-Sol (Codex)", "claude": "Claude Opus 5.5 (Claude Code)"}
HOME_VAR = {"codex": "CODEX_HOME", "claude": "CLAUDE_CONFIG_DIR"}
LOGIN = {"codex": ["login"], "claude": ["auth", "login", "--claudeai"]}
LOGOUT = {"codex": ["logout"], "claude": ["auth", "logout"]}
NO_WINDOW = subprocess.CREATE_NO_WINDOW
NEW_CONSOLE = subprocess.CREATE_NEW_CONSOLE
EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]

PROMPT = """아래 회의 메모를 회의록으로 정리해라. 정리 방식은 지침(AGENTS.md)에 적힌 대로 따른다.
셸 명령 실행·파일 읽기/쓰기를 하지 말고, 정리한 마크다운만 답으로 출력한다.

회의 제목: {title}
회의 일정: {when}

회의 메모:
<<<
{memo}
>>>
"""


def desktop_dir():
    # OneDrive 로 옮겨진 바탕화면도 찾는다(CSIDL_DESKTOPDIRECTORY)
    buf = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0:
        return Path(buf.value)
    return Path.home() / "Desktop"


DESKTOP = desktop_dir()


def env_for(engine):
    home = APPDIR / engine
    home.mkdir(parents=True, exist_ok=True)
    return {**os.environ, HOME_VAR[engine]: str(home)}


def find_exe(engine):
    # 방금 [설치] 로 깔았으면 이 프로세스의 PATH 에는 아직 없다 — 설치 위치를 직접 본다
    found = shutil.which(engine)
    return found or (str(KNOWN[engine]) if KNOWN[engine].exists() else None)


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


def summarize(engine, title, when, memo):
    prompt = PROMPT.format(title=title or "(없음)", when=when or "(없음)", memo=memo)
    out = APPDIR / "last.md"
    if engine == "codex":
        out.unlink(missing_ok=True)
        args = ["exec", "-m", MODELS["codex"], "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only",
                "--color", "never", "-C", str(HERE), "-o", str(out), "-"]
    else:  # 도구를 모두 끄고 답만 받는다
        args = ["-p", "--model", MODELS["claude"], "--tools", "", "--no-session-persistence",
                "--system-prompt", "너는 회의록 정리 담당이다. 정리한 마크다운만 출력한다."]
    r = cli(engine, args, input=prompt.encode("utf-8"), capture_output=True, timeout=300,
            cwd=HERE, creationflags=NO_WINDOW)
    if r.returncode != 0:
        lines = (r.stderr + r.stdout).decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(lines[-1] if lines else f"종료 코드 {r.returncode}")
    if engine == "codex":
        return out.read_text(encoding="utf-8").strip()
    return r.stdout.decode("utf-8", "replace").strip()


# ── 화면이 부르는 일들 ──
PENDING = set()     # 로그인 창이 떠 있는 도구
INSTALLING = set()  # 설치 창이 떠 있는 도구
PATHS = {}          # 회의(mid)마다 저장한 파일 — 다시 생성하면 같은 파일을 덮고, 제목·날짜가 바뀌면 이름을 바꾼다


def status(_=None):
    out = {}
    for engine in ENGINES:
        if not find_exe(engine):
            out[engine] = {"installed": False, "installing": engine in INSTALLING}
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


def install(data):
    engine = data["engine"]
    if engine not in INSTALLING and not find_exe(engine):
        INSTALLING.add(engine)

        def run():
            try:  # 설치 과정이 보이게 창을 띄우고, 끝나면 Enter 로 닫게 한다
                subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                                INSTALL[engine] + "; Read-Host '설치가 끝났습니다. Enter 를 누르면 창이 닫힙니다'"],
                               creationflags=NEW_CONSOLE)
            finally:
                INSTALLING.discard(engine)
        threading.Thread(target=run, daemon=True).start()
    return status()


def generate(data):
    engine, title, when, memo = data["engine"], data["title"].strip(), data["when"].strip(), data["memo"].strip()
    summary = summarize(engine, title, when, memo)
    m = re.search(r"\d{4}-\d{1,2}-\d{1,2}", when)
    date = m.group() if m else f"{datetime.now():%Y-%m-%d}"
    path, key = PATHS.get(data["mid"], (None, None))
    if (title, date) != key:  # 처음 저장하거나 제목·날짜가 바뀌었다
        name = re.sub(r'[\\/:*?"<>|]', "_", title).strip() or "회의"
        new, n = DESKTOP / f"{date}_{name}.md", 2
        while new.exists():
            new, n = DESKTOP / f"{date}_{name}({n}).md", n + 1
        if path and path.exists():
            path.rename(new)
        path = new
        PATHS[data["mid"]] = (path, (title, date))
    path.write_text(
        f"# {title or '회의'}\n\n- 일정: {when}\n- 저장: {datetime.now():%Y-%m-%d %H:%M}\n"
        f"- 정리: {ENGINES[engine]}\n\n{summary}\n\n---\n\n## 원본 메모\n\n```text\n{memo}\n```\n",
        encoding="utf-8")
    return {"name": path.name, "at": f"{datetime.now():%H:%M}"}


def open_file(data):
    path = PATHS.get(data["mid"], (None,))[0]
    if path and path.exists():
        subprocess.run(["explorer", "/select,", str(path)])
    return {}


# ── 창이 살아 있는지 — 화면이 20초마다 ping, 닫힐 때 bye ──
seen = {"ping": None, "closing": None}


def ping(_):
    seen["ping"], seen["closing"] = time.time(), None
    return {}


def bye(_):
    seen["closing"] = time.time() + 5  # 새로고침이면 5초 안에 ping 이 다시 온다
    return {}


ROUTES = {"/api/connect": connect, "/api/disconnect": disconnect, "/api/install": install,
          "/api/generate": generate, "/api/open": open_file, "/api/ping": ping, "/api/bye": bye}


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
        if self.path == "/" and self.allowed(need_token=False):
            html = (HERE / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", self.token)
            self.send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/icon.png" and self.allowed(need_token=False):
            self.send(200, (HERE / "icon.png").read_bytes(), "image/png")
        elif self.path == "/api/status" and self.allowed():
            self.send(200, status())
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


def make_shortcut(exe):
    # 배포판을 처음 켜면 바탕화면 바로가기를 이 PC 에서 만든다 — 받은 .lnk 는 스마트 앱 컨트롤에 막히지만
    # 이 PC 에서 만든 것은 막히지 않는다. 이미 있으면 건드리지 않는다.
    lnk = DESKTOP / "회의 메모 정리.lnk"
    if lnk.exists():
        return
    script = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:MM_LNK); $s.TargetPath = $env:MM_EXE; "
              "$s.WorkingDirectory = $env:MM_DIR; $s.IconLocation = $env:MM_ICON; $s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", script], creationflags=NO_WINDOW,
                   env={**os.environ, "MM_LNK": str(lnk), "MM_EXE": str(exe), "MM_DIR": str(HERE),
                        "MM_ICON": str(HERE / "icon.ico")})


def open_window(url):
    edge = next((p for p in EDGE if Path(p).exists()), None)
    if edge:
        subprocess.Popen([edge, f"--app={url}", "--window-size=1040,880"])
    else:
        webbrowser.open(url)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Handler.host = f"127.0.0.1:{server.server_port}"
    Handler.token = secrets.token_urlsafe(16)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    open_window(f"http://{Handler.host}/")
    if Path(sys.executable).name == PACKAGED_EXE:
        make_shortcut(Path(sys.executable))
    started = time.time()
    while True:  # 창이 닫히면(bye 뒤 ping 없음) 끝낸다 · 1분 안에 창이 안 뜨거나 12시간 소식이 없어도 끝낸다
        time.sleep(1)
        now = time.time()
        if seen["closing"] and now > seen["closing"]:
            break
        if now - (seen["ping"] or started) > (12 * 3600 if seen["ping"] else 60):
            break


if __name__ == "__main__":
    main()
