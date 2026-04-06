import argparse
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlparse
import re

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


LOGIN_URL = "https://everytime.kr/login"
DEFAULT_BOARD_URL = "https://everytime.kr/377388"


def build_driver(driver_path: str | None = None) -> webdriver.Chrome:
    if driver_path:
        service = Service(driver_path)
        return webdriver.Chrome(service=service)

    local_driver = Path("chromedriver.exe")
    if local_driver.exists():
        service = Service(str(local_driver.resolve()))
        return webdriver.Chrome(service=service)

    return webdriver.Chrome()


def login(driver: webdriver.Chrome) -> None:
    driver.get(LOGIN_URL)
    input("에브리타임 로그인 완료 후 Enter를 누르세요: ")


def normalize_board_url(board_url: str) -> str:
    parsed = urlparse(board_url)
    cleaned_path = re.sub(r"/(all|p/\d+)$", "", parsed.path.rstrip("/"))
    return f"{parsed.scheme}://{parsed.netloc}{cleaned_path}"


def debug_log(enabled: bool, message: str) -> None:
    if enabled:
        print(f"[debug] {message}")


def search(
    driver: webdriver.Chrome,
    keyword: str,
    board_url: str,
    wait_seconds: float = 3.0,
    debug: bool = False,
) -> None:
    normalized_board_url = normalize_board_url(board_url)
    search_url = f"{normalized_board_url}/all/{quote(keyword)}"
    driver.get(search_url)
    time.sleep(wait_seconds)
    debug_log(debug, f"opened search url: {driver.current_url}")


def scroll(driver: webdriver.Chrome, scroll_count: int = 5, pause_seconds: float = 2.0) -> None:
    for _ in range(scroll_count):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause_seconds)


def extract_articles(driver: webdriver.Chrome):
    selectors = [
        ".article",
        "article",
        "a.article",
        "div.article",
    ]
    seen = []
    seen_ids = set()
    for selector in selectors:
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            element_id = getattr(element, "id", None) or element.id
            if element_id not in seen_ids:
                seen.append(element)
                seen_ids.add(element_id)
    return seen


def extract_article_signature(article) -> str:
    return " ".join(article.text.split())


def extract_date_text(article) -> str:
    selectors = [
        ".time",
        "time",
        "small.time",
        "p.info span.time",
        ".status .time",
    ]
    for selector in selectors:
        try:
            text = article.find_element(By.CSS_SELECTOR, selector).text.strip()
            if text:
                return text
        except NoSuchElementException:
            continue
    return ""


def build_page_url(base_url: str, page_number: int) -> str:
    cleaned_url = re.sub(r"/p/\d+$", "", base_url.rstrip("/"))
    if page_number <= 1:
        return cleaned_url
    return f"{cleaned_url}/p/{page_number}"


def collect_date_texts(
    driver: webdriver.Chrome,
    scroll_count: int,
    pause_seconds: float,
    max_pages: int,
    stop_prefixes: list[str] | None = None,
    debug: bool = False,
) -> list[str]:
    base_url = re.sub(r"/p/\d+$", "", driver.current_url.rstrip("/"))
    seen_page_signatures: set[tuple[str, ...]] = set()
    collected_dates: list[str] = []

    for page_number in range(1, max_pages + 1):
        page_url = build_page_url(base_url, page_number)
        if driver.current_url.rstrip("/") != page_url.rstrip("/"):
            driver.get(page_url)
            time.sleep(pause_seconds)
        debug_log(debug, f"page {page_number} url: {driver.current_url}")

        scroll(driver, scroll_count, pause_seconds)
        articles = extract_articles(driver)
        debug_log(debug, f"page {page_number} article count: {len(articles)}")
        if not articles:
            break

        page_signatures = tuple(
            extract_article_signature(article) for article in articles[:10]
        )
        if page_signatures in seen_page_signatures:
            break
        seen_page_signatures.add(page_signatures)

        for article in articles:
            article_date = extract_date_text(article)
            if article_date:
                collected_dates.append(article_date)

        sample_dates = [extract_date_text(article) for article in articles[:5]]
        debug_log(debug, f"page {page_number} sample dates: {sample_dates}")

        if stop_prefixes:
            page_dates = [extract_date_text(article) for article in articles]
            valid_page_dates = [date_text for date_text in page_dates if date_text]
            if valid_page_dates and any(
                not any(date_text.startswith(prefix) for prefix in stop_prefixes)
                for date_text in valid_page_dates
            ):
                debug_log(debug, f"stopping at page {page_number} because date prefix changed")
                break

    return collected_dates


def count_by_date(date_texts: list[str], dates: list[str]) -> dict[str, int]:
    result = {date_text: 0 for date_text in dates}

    for article_date in date_texts:
        for target_date in dates:
            if target_date in article_date:
                result[target_date] += 1

    return result


def save_csv(result: dict[str, int], output_path: str) -> None:
    df = pd.DataFrame(list(result.items()), columns=["date", "count"])
    df.to_csv(output_path, index=False, encoding="utf-8-sig")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="에브리타임 검색 결과에서 날짜별 게시글 개수를 집계합니다."
    )
    parser.add_argument("--keyword", required=True, help="검색할 키워드")
    parser.add_argument(
        "--dates",
        nargs="+",
        required=True,
        help='집계할 날짜 목록. 예: --dates 04/01 04/02 04/03',
    )
    parser.add_argument(
        "--board-url",
        default=DEFAULT_BOARD_URL,
        help="검색할 게시판 URL",
    )
    parser.add_argument(
        "--driver-path",
        default=None,
        help="ChromeDriver 실행 파일 경로. 지정하지 않으면 현재 폴더의 chromedriver.exe를 먼저 찾습니다.",
    )
    parser.add_argument(
        "--scrolls",
        type=int,
        default=5,
        help="추가 게시글 로딩을 위한 스크롤 횟수",
    )
    parser.add_argument(
        "--output",
        default="result.csv",
        help="CSV 저장 경로",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=3.0,
        help="검색 페이지 이동 후 대기 시간(초)",
    )
    parser.add_argument(
        "--scroll-pause",
        type=float,
        default=2.0,
        help="스크롤 사이 대기 시간(초)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=20,
        help="확인할 최대 페이지 수. /p/2, /p/3 형태 페이지까지 순회합니다.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="현재 URL, 페이지별 글 수, 샘플 날짜를 출력합니다.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stop_prefixes = sorted({date_text[:3] for date_text in args.dates if len(date_text) >= 3})

    driver = None
    try:
        driver = build_driver(args.driver_path)
        login(driver)
        search(driver, args.keyword, args.board_url, args.wait_seconds, args.debug)
        WebDriverWait(driver, max(3, int(args.wait_seconds) + 2)).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".article, article"))
        )
        date_texts = collect_date_texts(
            driver,
            args.scrolls,
            args.scroll_pause,
            args.max_pages,
            stop_prefixes,
            args.debug,
        )

        debug_log(args.debug, f"collected dates sample: {date_texts[:10]}")
        print(f"수집한 날짜 정보 수: {len(date_texts)}")

        result = count_by_date(date_texts, args.dates)
        print("날짜별 게시글 수:")
        for date_text, count in result.items():
            print(f"{date_text}: {count}")

        save_csv(result, args.output)
        print(f"CSV 저장 완료: {args.output}")
        return 0
    except WebDriverException as exc:
        print("ChromeDriver 실행에 실패했습니다.")
        print("드라이버 버전과 크롬 버전이 맞는지 확인하세요.")
        print(f"상세 오류: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\n사용자에 의해 중단되었습니다.")
        return 1
    finally:
        if driver is not None:
            driver.quit()


if __name__ == "__main__":
    sys.exit(main())
