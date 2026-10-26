# 회의 메모 정리

회의 중에 메모를 적고 **[회의 정리 파일 생성]** 을 누르면, GPT(Codex) 나 Claude(Claude Code)가
**요약 + 주제별 체크리스트**로 정리해 바탕화면에 `.md` 파일로 저장합니다.

## 내려받기

### [회의 메모 정리 내려받기 (meeting-memo.zip)](https://github.com/hfoodlabmarketing/hfoodlab_program/releases/download/meeting-memo/meeting-memo.zip)

파이썬 같은 프로그램을 따로 깔 필요가 없습니다.

## 처음 쓸 때

1. 받은 `meeting-memo.zip` 을 **압축 풀기** 합니다. 압축 파일 안에서 바로 실행하면 켜지지 않습니다.
2. 풀린 `회의 메모 정리` 폴더에서 **`회의 메모 정리.exe`** 를 더블클릭합니다. 다음부터도 이 파일로 켭니다.
3. 화면의 **계정** 줄을 봅니다.
   - `이 PC에 없습니다 [설치]` — [설치] 를 누르면 그 자리에 받는 진행률이 나오고, 끝나면 `[연결]` 로 바뀝니다.
   - `연결 안 됨 [연결]` — [연결] 을 누르면 브라우저에서 ChatGPT 또는 Claude 계정으로 로그인합니다.
4. 회의 제목·일정·메모를 적고 **[회의 정리 파일 생성]** 을 누릅니다.

- Codex 를 쓸 수 있는 ChatGPT 요금제나, Claude Code 를 쓸 수 있는 Claude 요금제 계정이 필요합니다.
- 정리 방식은 폴더의 `AGENTS.md` 를 메모장으로 열어 고치면 바뀝니다.

## 고치는 사람에게

- 파이썬이 있는 PC 에서는 `pythonw meeting_memo.py` 로 바로 켭니다.
- 배포판은 `python build.py` 로 만들고(`dist/meeting-memo.zip`), Release `meeting-memo` 의 파일을 이것으로 바꿉니다.
  왜 이런 방식으로 나눠 주는지는 `build.py` 머리말에 있습니다.
