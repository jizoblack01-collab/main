import os
from shutil import which
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

def _looks_like_browser(p: str) -> bool:
    return p and os.path.exists(p) and os.path.basename(p).lower() in {
        "chromium", "google-chrome", "google-chrome-stable", "chromium-browser"
    }

def _looks_like_driver(p: str) -> bool:
    return p and os.path.exists(p) and os.path.basename(p).lower() == "chromedriver"

def _autodetect_browser() -> str | None:
    cands = [
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        which("chromium"),
        which("chromium-browser"),
        which("google-chrome"),
        which("google-chrome-stable"),
    ]
    for p in cands:
        if _looks_like_browser(p):
            return p
    return None

def _autodetect_driver() -> str | None:
    cands = [
        "/usr/lib/chromium/chromedriver",
        "/usr/lib/chromium-browser/chromedriver",
        "/usr/bin/chromedriver",
        "/usr/local/bin/chromedriver",
        which("chromedriver"),
    ]
    for p in cands:
        if _looks_like_driver(p):
            return p
    return None

@st.cache_resource(show_spinner=False)
def get_driver():
    """Headless Chrome — env가 뒤집혀 있어도 자동으로 교정."""
    opt = webdriver.ChromeOptions()
    opt.add_argument("--headless=new")
    opt.add_argument("--no-sandbox")
    opt.add_argument("--disable-dev-shm-usage")
    opt.add_argument("--window-size=1600,1000")
    opt.add_argument("--lang=ko-KR")

    # 1) 환경변수 가져오기 (selenium.streamlit.app 스타일)
    env_bin = os.environ.get("GOOGLE_CHROME_BIN") or os.environ.get("CHROME_BIN") or ""
    env_drv = os.environ.get("CHROMEDRIVER_PATH") or os.environ.get("CHROMEDRIVER") or ""

    # 2) 잘못된 매핑 자동 교정 (chromedriver가 binary로 들어가 있거나 반대인 경우)
    if _looks_like_driver(env_bin) and _looks_like_browser(env_drv):
        # 완전히 뒤집혀 있으면 스왑
        env_bin, env_drv = env_drv, env_bin
    # binary로 chromedriver가 들어가 있으면 무시
    if _looks_like_driver(env_bin):
        env_bin = ""
    # driver에 chromium이 들어가 있으면 무시
    if _looks_like_browser(env_drv):
        env_drv = ""

    # 3) 최종 경로 확정 (env 우선, 없으면 자동탐색)
    browser_path = env_bin if _looks_like_browser(env_bin) else _autodetect_browser()
    driver_path  = env_drv if _looks_like_driver(env_drv) else _autodetect_driver()

    # 4) binary_location은 '브라우저'만! (chromedriver 넣으면 바로 unsupported file 에러)
    if browser_path:
        opt.binary_location = browser_path

    # 5) 먼저 시스템 드라이버로 시도
    if driver_path:
        try:
            return webdriver.Chrome(service=Service(driver_path), options=opt)
        except Exception:
            pass

    # 6) Selenium Manager 최종 시도 (네트워크 제한 시 실패 가능)
    return webdriver.Chrome(options=opt)
