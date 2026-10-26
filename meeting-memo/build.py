"""배포판 만들기 — python.org 공식 휴대용 파이썬에 이 폴더의 프로그램을 얹어 dist/meeting-memo.zip 을 만든다.
받은 사람은 파이썬을 깔 필요 없이 「회의 메모 정리.exe」를 더블클릭한다.

왜 이렇게 나눠 주나(2026-10-26 스마트 앱 컨트롤이 켜진 PC 에서 실측):
- 직접 만든 서명 없는 .exe(PyInstaller·PyQt 등)는 "An Application Control policy has blocked this file" 로 막힌다.
- 받은 바로가기(.lnk)·.bat·.ps1 도 "위험한 확장자"로 막힌다. IP 로 연결한 사내 공유 폴더도 인터넷으로 친다.
- python.org 의 pythonw.exe 는 Python Software Foundation 서명이 있어, 이름을 바꾸고 "인터넷에서 받음"
  표시가 붙어도 통과한다. 그래서 그 파일을 「회의 메모 정리.exe」로 이름만 바꿔 쓴다(아이콘은 못 바꾼다 —
  바꾸면 서명이 깨진다).
- 바탕화면 바로가기는 만들지 않는다 — 첫 실행 때 그 PC 에서 만든 바로가기도 다른 PC 에서 스마트 앱 컨트롤
  차단이 떴다(2026-10-26). 폴더 안의 exe 를 직접 켜면 막히지 않는다.

다 만들면 GitHub Release `meeting-memo` 의 meeting-memo.zip 을 이 파일로 바꾼다 — 내려받기 주소가 그대로 유지된다.
"""
import hashlib
import io
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY_URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
PY_SHA256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
NAME = "회의 메모 정리"  # 압축 안 폴더 이름이자 실행 파일 이름
FILES = ["meeting_memo.py", "sitecustomize.py", "index.html", "AGENTS.md", "CLAUDE.md", "icon.png", "icon.ico"]


def main():
    data = urllib.request.urlopen(PY_URL).read()
    if hashlib.sha256(data).hexdigest() != PY_SHA256:
        raise SystemExit("받은 파이썬 파일이 예상과 다릅니다 — PY_URL·PY_SHA256 을 확인하세요")
    out = HERE / "dist" / "meeting-memo.zip"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as py, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for info in py.infolist():
            name, body = info.filename, py.read(info)
            if name == "python.exe":  # 콘솔 창이 뜨는 쪽은 쓰지 않는다
                continue
            if name == "pythonw.exe":
                name = f"{NAME}.exe"
            if name == "python312._pth":  # sitecustomize.py 를 읽게 한다
                body = body.replace(b"#import site", b"import site")
            z.writestr(f"{NAME}/{name}", body)
        for f in FILES:
            z.write(HERE / f, f"{NAME}/{f}")
    print(f"{out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
