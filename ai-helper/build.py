"""배포판 만들기 — python.org 공식 휴대용 파이썬 + openpyxl 에 이 폴더의 프로그램을 얹어 dist/ai-helper.zip 을 만든다.
받은 사람은 파이썬을 깔 필요 없이 「AI 작업 도우미.exe」를 더블클릭한다.

왜 이렇게 나눠 주는지(스마트 앱 컨트롤 — 서명 없는 .exe·받은 .lnk 는 막힌다)는 meeting-memo/build.py 머리말과 같다.
회의 메모 정리와 다른 점:
- python.exe(콘솔)를 남긴다 — AI 가 엑셀을 고칠 때 `python` 으로 쓴다(ai_helper.agent_env 가 PATH 맨 앞에 둔다)
- openpyxl·et_xmlfile 을 lib/ 에 넣는다(순수 파이썬 패키지라 서명할 실행 파일이 없다)

다 만들면 GitHub Release `ai-helper` 의 ai-helper.zip 을 이 파일로 바꾼다 — 내려받기 주소가 그대로 유지된다.
"""
import hashlib
import io
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = ("https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip",
      "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3")
WHEELS = [  # PyPI 공식 해시
    ("https://files.pythonhosted.org/packages/c0/da/977ded879c29cbd04de313843e76868e6e13408a94ed6b987245dc7c8506/"
     "openpyxl-3.1.5-py2.py3-none-any.whl", "5282c12b107bffeef825f4617dc029afaf41d0ea60823bbb665ef3079dc79de2"),
    ("https://files.pythonhosted.org/packages/c1/8b/5fe2cc11fee489817272089c4203e679c63b570a5aaeb18d852ae3cbba6a/"
     "et_xmlfile-2.0.0-py3-none-any.whl", "7a91720bc756843502c3b7504c77b8fe44217c85c537d85037f0f536151b2caa"),
]
NAME = "AI 작업 도우미"  # 압축 안 폴더 이름이자 실행 파일 이름 — ai_helper.PACKAGED_EXE 와 같아야 한다
FILES = ["ai_helper.py", "sitecustomize.py", "index.html", "icon.png", "icon.ico"]


def download(url, sha256):
    data = urllib.request.urlopen(url).read()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise SystemExit(f"받은 파일이 예상과 다릅니다 — {url}")
    return zipfile.ZipFile(io.BytesIO(data))


def main():
    out = HERE / "dist" / "ai-helper.zip"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        py = download(*PY)
        for info in py.infolist():
            name, body = info.filename, py.read(info)
            if name == "pythonw.exe":
                name = f"{NAME}.exe"
            if name == "python312._pth":  # sitecustomize.py 를 읽고, lib/ 의 openpyxl 을 찾게 한다
                lines = ["import site" if line == "#import site" else line for line in body.decode().splitlines()]
                lines.insert(lines.index(".") + 1, "lib")
                body = "\r\n".join(lines).encode() + b"\r\n"
            z.writestr(f"{NAME}/{name}", body)
        for url, sha256 in WHEELS:
            wheel = download(url, sha256)
            for info in wheel.infolist():
                if ".dist-info/" not in info.filename:
                    z.writestr(f"{NAME}/lib/{info.filename}", wheel.read(info))
        for f in FILES:
            z.write(HERE / f, f"{NAME}/{f}")
    print(f"{out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
