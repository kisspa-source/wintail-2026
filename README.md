# wintail-2026

[![CI](https://github.com/kisspa-source/wintail-2026/actions/workflows/ci.yml/badge.svg)](https://github.com/kisspa-source/wintail-2026/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Doug Edwards의 원조 **WinTail**을 레퍼런스로 한 차세대 경량 Windows 로그 뷰어.
원조의 정체성(설치 없음·단일 EXE·즉시 실행·실시간 Tail·경량)은 유지하면서,
한계(64KB 제한·ANSI 중심·단일 탭·하이라이트 없음)를 걷어내고 현대적 기능을 더했다.

핵심 원칙: **파일을 통째로 메모리/위젯에 올리지 않는다.** 파일을 청크로 스캔해
sparse 체크포인트 인덱스를 만들고, 화면에 보이는 영역만 읽어 렌더링한다.
그 결과 **5GB+ 파일도 즉시 열리고(끝부분 ms 단위 표시, 전체 인덱싱 ~1.3GB/s),
메모리는 수십 MB만** 쓴다.

## 기능

- **실시간 Tail** (`tail -f`): 자동 추적, 위로 스크롤하면 일시정지·바닥에서 재개
- **로그 로테이션/트렁케이션 감지**: 외부 의존성 없이 폴링으로 처리
- **대용량 가상 스크롤**: 5GB+ 파일도 가시 영역만 렌더링
- **멀티 탭**: 탭마다 독립 엔진/Tail/필터/인코딩
- **필터**: 부분문자열·정규식, 숨김(grep식)·하이라이트, 대소문자 옵션. highlight 모드에선 필터창에서 **Enter로 다음 일치, Shift+Enter로 이전 일치**로 이동(일치 줄을 가운데 두고 진한 색으로 강조, 끝에서 순환) — 툴바에 **현재/전체 개수(`3/12`)** 표시
- **레벨 색상**: ERROR/FATAL(빨강), WARN(주황), INFO(파랑), DEBUG(회색) — 편집 가능
- **JSON Pretty**: 줄 더블클릭 시 그 줄의 JSON을 들여쓰기 팝업으로
- **쿼리 클릭 복사**: `{ }`로 감싼 쿼리(예: `Query:{...}[END]`) 안을 더블클릭하면 **여러 줄에 걸친 쿼리라도** 블록 전체를 선택·클립보드 복사하고 **"복사됨" 토스트**를 잠깐 표시(괄호 밖 더블클릭은 JSON Pretty)
- **인코딩**: UTF-8/UTF-8-SIG 기본, CP949(EUC-KR)·UTF-16 LE/BE, BOM 감지, 수동 오버라이드
- **자동 줄바꿈**: 보기 메뉴에서 토글(전역). 켜면 가로 스크롤 대신 단어 단위로 접고, 빠른 스크롤을 위해 줄번호 거터는 숨긴다(현재 줄은 상태바에 표시)
- **글꼴 크기/선택**: `Ctrl++`/`Ctrl+-`/`Ctrl+0`·`Ctrl+휠`로 크기 조절, 고정폭 후보 또는 설치된 전체 글꼴 선택
- **테마 프리셋**: Light+(기본)/Dark+/Monokai/One Dark/Dracula/Solarized Dark — 툴바 콤보로 선택하면 **탭 본문(로그 내용·거터·매칭 색·스크롤바)** 만 바뀌고, 메뉴/툴바/버튼 등 크롬은 Light+로 고정해 깔끔함 유지. 활성 탭은 본문 색과 이어지고, 버튼은 클래식 윈도우처럼 볼록(raised)·누르면 들어가는 입체 베벨. 설정 영속화(`%APPDATA%/wintail-2026/config.json`)

## 실행 (개발)

```powershell
python wintail.py                 # 빈 상태로 실행
python wintail.py C:\logs\app.log # 파일 열고 시작
```

표준 라이브러리(Tkinter)만 사용하므로 런타임 의존성이 없다.

## 단일 EXE 빌드

```powershell
python -m pip install nuitka      # 빌드 도구 (MSVC 필요)
./build.ps1                       # -> dist/wintail.exe
```

## 테스트

```powershell
python -m pip install pytest
python -m pytest -q
```

## 성능 벤치 (개발용)

```powershell
python bench.py 500     # 500MB 합성 로그로 로드/인덱싱/필터/메모리 측정
```

## 구조

```
wintail.py            앱 진입점 (메뉴/툴바/상태바/펌프 와이어링)
engine/               Tk 비의존 코어 (headless 테스트 가능)
  encoding.py         인코딩 감지
  filereader.py       인코딩 인지 바이트 I/O + 라인 분할(UTF-16 2바이트 정렬)
  fileindex.py        sparse 체크포인트 인덱스
  linescan.py         공용 라인 이터레이터
  indexer.py          백그라운드 인덱싱 + 공유 스캔 루틴
  tailwatcher.py      실시간 Tail + 로테이션 감지
  filterscanner.py    Matcher + 백그라운드 hide 스캔(부분문자열 고속 경로)
  logengine.py        UI가 쓰는 유일 파사드
  events.py           엔진→UI 이벤트/라인 레코드
ui/                   Tkinter 레이어
  viewport.py         ViewportModel(가상 스크롤 순수 로직)
  lineview.py         거터+본문+커스텀 스크롤바 위젯
  tabs.py             LogTab(탭 컨트롤러) + TabManager
  bridge.py           이벤트 펌프(after 루프)
  highlight.py        레벨 분류/색상
  style.py            테마 dict → ttk 전체 위젯 스타일(clam)
  jsonpanel.py        JSON Pretty
  queryspan.py        { } 쿼리 범위 탐색(단일/멀티라인, 클릭 복사용, 순수 로직)
  toast.py            짧게 떴다 사라지는 알림(복사 피드백)
  fontdialog.py       '모든 글꼴' 선택 다이얼로그
  theme.py / config.py  테마 프리셋 / 설정 영속화
tools/launch_smoke.py GUI 런처 스모크(개발용)
```

## 라이선스

[MIT](LICENSE) © 2026 kisspa-source
