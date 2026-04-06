# Crawling-everytime

Selenium으로 에브리타임 검색 결과를 열고, 게시글 날짜를 읽어서 날짜별 글 개수를 집계하는 간단한 크롤링 프로젝트입니다.

## 구조

- `main.py`
  - `login()`
  - `search()`
  - `scroll()`
  - `count_by_date()`
  - `save_csv()`

## 설치

```bash
pip install selenium pandas
```

크롬 브라우저 버전에 맞는 ChromeDriver를 준비한 뒤, 아래 둘 중 하나로 사용하세요.

1. `chromedriver.exe`를 프로젝트 폴더에 둡니다.
2. 직접 경로를 인자로 넘깁니다.

## 실행 예시

```bash
python main.py --keyword 과제 --dates 04/01 04/02 04/03
```

드라이버 경로를 직접 줄 때:

```bash
python main.py --keyword 과제 --dates 04/01 04/02 04/03 --driver-path C:\path\to\chromedriver.exe
```

스크롤 횟수와 저장 파일명도 바꿀 수 있습니다.

```bash
python main.py --keyword 과제 --dates 04/01 04/02 04/03 --scrolls 8 --output result.csv
```

## 동작 방식

1. Selenium으로 크롬 실행
2. 에브리타임 로그인 페이지 접속
3. 사용자가 직접 로그인
4. 검색 결과 페이지 이동
5. 스크롤 반복으로 게시글 추가 로딩
6. 게시글 날짜 문자열을 읽어서 원하는 날짜별 개수 집계
7. CSV 저장

## 주의

- 사이트 구조가 바뀌면 선택자(`article`, `time`)를 수정해야 할 수 있습니다.
- 너무 빠르게 반복 요청하지 않도록 `sleep`을 넣어두었습니다.
- 에브리타임은 공식 날짜 필터 API가 없다고 가정하고, 화면에 보이는 게시글의 날짜를 읽는 방식으로 처리합니다.
