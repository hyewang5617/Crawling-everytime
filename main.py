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
from selenium.webdriver.common.keys import Keys


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


def extract_board_id(board_url: str) -> str | None:
    path = urlparse(board_url).path.rstrip("/")
    match = re.search(r"/(\d+)$", path)
    if match:
        return match.group(1)
    return None


def find_search_input(driver: webdriver.Chrome):
    selectors = [
        "input[type='search']",
        "input[name='keyword']",
        "form.search input",
        "div.search input",
        "input.text",
    ]
    for selector in selectors:
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        for element in elements:
            if element.is_displayed() and element.is_enabled():
                return element
    return None


def try_open_search_ui(driver: webdriver.Chrome) -> None:
    selectors = [
        "a.search",
        "button.search",
        "[class*='search']",
        "[href*='search']",
    ]
    for selector in selectors:
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        for element in elements:
            if element.is_displayed() and element.is_enabled():
                try:
                    element.click()
                    time.sleep(1)
                    return
                except WebDriverException:
                    continue


def search(driver: webdriver.Chrome, keyword: str, board_url: str, wait_seconds: float = 3.0) -> None:
    driver.get(board_url)
    time.sleep(wait_seconds)

    search_input = find_search_input(driver)
    if search_input is None:
        try_open_search_ui(driver)
        search_input = find_search_input(driver)

    if search_input is not None:
        search_input.clear()
        search_input.send_keys(keyword)
        search_input.send_keys(Keys.ENTER)
        time.sleep(wait_seconds)
        return

    board_id = extract_board_id(board_url)
    direct_urls = []
    if board_id:
        encoded_keyword = quote(keyword)
        direct_urls.extend(
            [
                f"https://everytime.kr/search/{board_id}/{encoded_keyword}",
                f"https://everytime.kr/search/board/{board_id}/{encoded_keyword}",
            ]
        )

    for direct_url in direct_urls:
        driver.get(direct_url)
        time.sleep(wait_seconds)
        if extract_articles(driver):
            return

    raise RuntimeError(
        "자유게시판 검색창을 찾지 못했습니다. 에브리타임 화면 구조가 바뀌었을 수 있습니다."
    )


def scroll(driver: webdriver.Chrome, scroll_count: int = 5, pause_seconds: float = 2.0) -> None:
    for _ in range(scroll_count):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause_seconds)


def extract_articles(driver: webdriver.Chrome):
    return driver.find_elements(By.CLASS_NAME, "article")


def extract_date_text(article) -> str:
    try:
        return article.find_element(By.CLASS_NAME, "time").text.strip()
    except NoSuchElementException:
        return ""


def count_by_date(driver: webdriver.Chrome, dates: list[str]) -> dict[str, int]:
    articles = extract_articles(driver)
    result = {date_text: 0 for date_text in dates}

    for article in articles:
        article_date = extract_date_text(article)
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    driver = None
    try:
        driver = build_driver(args.driver_path)
        login(driver)
        search(driver, args.keyword, args.board_url, args.wait_seconds)
        scroll(driver, args.scrolls, args.scroll_pause)

        articles = extract_articles(driver)
        print(f"전체 게시글 수: {len(articles)}")

        result = count_by_date(driver, args.dates)
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
