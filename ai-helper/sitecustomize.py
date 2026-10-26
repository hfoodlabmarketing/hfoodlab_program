# 배포판에서 「AI 작업 도우미.exe」(이름만 바꾼 pythonw.exe)를 더블클릭하면 스크립트 없이 파이썬이 뜬다.
# 동봉 파이썬은 시작할 때 이 파일을 읽으므로(python312._pth 의 import site), 여기서 프로그램을 띄운다.
# 같은 폴더의 python.exe 는 AI 가 엑셀을 고칠 때 쓴다 — 실행 파일 이름까지 봐서 그때는 띄우지 않는다.
import os
import sys
from pathlib import Path

if Path(sys.executable).name == "AI 작업 도우미.exe" and len(sys.orig_argv) == 1:
    import ai_helper
    ai_helper.main()
    os._exit(0)  # sys.exit() 는 시작 중이라 '시작 실패'(종료 코드 1)로 끝난다
