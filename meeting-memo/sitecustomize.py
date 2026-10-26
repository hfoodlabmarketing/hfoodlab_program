# 배포판에서 「회의 메모 정리.exe」(이름만 바꾼 pythonw.exe)를 더블클릭하면 스크립트 없이 파이썬이 뜬다.
# 동봉 파이썬은 시작할 때 이 파일을 읽으므로(python312._pth 의 import site), 여기서 프로그램을 띄운다.
import os
import sys

if len(sys.orig_argv) == 1:
    import meeting_memo
    meeting_memo.main()
    os._exit(0)  # sys.exit() 는 시작 중이라 '시작 실패'(종료 코드 1)로 끝난다
