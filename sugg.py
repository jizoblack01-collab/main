#!/usr/bin/env python3
# ---------------------------------------------------------------------
# app.py — SNU 수강신청 실시간 모니터 (Streamlit + Selenium, 오프라인 드라이버)
#   • 과목코드/분반 입력 → 과목명과 (현재/정원) 막대그래프
#   • 현재 ≥ 정원: 빨간색, 현재 < 정원: 파란색
#   • 자동 새로고침 1–10 초
#   • webdriver-manager 제거 → /usr/bin/chromedriver 직접 사용
# ---------------------------------------------------------------------

import re, datetime, streamlit as st, os, shutil
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ---------- 기본 설정 ----------
DEFAULT_YEAR = 2025
SEM_VALUE = {
    1: "U000200001U000300001",
    2: "U000200001U000300002",
    3: "U000200002U000300001",
    4: "U000200002U000300002",
}
SEM_NAME = {1: "1학기", 2: "여름학기", 3: "2학기", 4: "겨울학기"}

TITLE_COL, CAP_COL, CURR_COL = 6, 13, 14
TIMEOUT = 10  # Selenium 대기시간(s)

CHROMEDRIVER_CANDIDATES = [
    "/usr/bin/chromedriver",
    "/usr/local/bin/chromedriver",
    "/usr/lib/chromium/chromedriver",
    shutil.which("chromedriver"),
]

# ---------- 드라이버 생성 ----------
@st.cache_resource(show_spinner=False)
def get_driver(headless: bool = True):
    drv_path = next((p for p in CHROMEDRIVER_CANDIDATES if p and os.path.exists(p)), None)
    if not drv_path:
        raise RuntimeError("chromedriver 경로를 찾지 못했습니다. packages.txt에 chromium-driver가 설치돼 있는지 확인!")

    opts = webdriver.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1600,1000")

    return webdriver.Chrome(service=Service(drv_path), options=opts)

# ---------- 페이지 조작 ----------
def _parse_int(txt: str) -> int:
    m = re.search(r"\d+", txt.replace(",", ""))
    return int(m.group()) if m else 0

def open_and_search(drv, year: int, sem: int, subject: str):
    drv.get("https://shine.snu.ac.kr/uni/sugang/cc/cc100.action")
    WebDriverWait(drv, TIMEOUT).until(
        EC.presence_of_element_located((By.ID, "srchOpenSchyy"))
    )
    drv.execute_script(
        """
        document.getElementById('srchOpenSchyy').value = arguments[0];
        document.getElementById('srchOpenShtm').value  = arguments[1];
        document.getElementById('srchSbjtCd').value    = arguments[2];
        fnInquiry();
        """,
        str(year), SEM_VALUE[int(sem)], subject.strip()
    )

def read_info(drv, cls: str):
    WebDriverWait(drv, TIMEOUT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "table.tbl_basic tbody tr"))
    )
    for tr in drv.find_elements(By.CSS_SELECTOR, "table.tbl_basic tbody tr"):
        tds = tr.find_elements(By.TAG_NAME, "td")
        if len(tds) <= CURR_COL:
            continue
        if any(td.text.strip() == cls.strip() for td in tds):
            cap_txt = tds[CAP_COL].text
            m = re.search(r"\((\d+)\)", cap_txt)
            quota   = int(m.group(1)) if m else _parse_int(cap_txt)
            current = _parse_int(tds[CURR_COL].text)
            title   = tds[TITLE_COL].text.strip()
            return quota, current, title
    return None, None, None

# ---------- 막대그래프 ----------
def render_bar(title, current, quota):
    is_full = current >= quota
    pct = min(current / quota * 100, 100) if quota else 0
    color = "#e53935" if is_full else "#1e88e5"
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:12px">
          <div style="flex:1;position:relative;height:24px;background:#eee;border-radius:8px;overflow:hidden">
            <div style="position:absolute;top:0;left:0;bottom:0;width:{pct:.2f}%;background:{color}"></div>
          </div>
          <span style="font-weight:600;white-space:nowrap">{title} ({current}/{quota})</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ---------- Streamlit UI ----------
st.set_page_config(page_title="SNU 수강신청 모니터", layout="wide")
st.title("SNU 수강신청 실시간 모니터 (Selenium·로컬 드라이버)")

with st.sidebar:
    subject = st.text_input("과목코드", value="445.206")
    cls     = st.text_input("분반", value="002")
    year    = st.number_input("개설연도", value=DEFAULT_YEAR, step=1)
    sem_num = st.selectbox("학기", [1,2,3,4], index=2, format_func=lambda i: SEM_NAME[i])
    auto    = st.checkbox("자동 새로고침", True)
    interval = st.slider("새로고침(초)", 1, 10, value=2)
    headless = st.checkbox("Headless 모드", True)

st_autorefresh = getattr(st, "autorefresh", None) or getattr(st, "st_autorefresh", None)
if auto and st_autorefresh:
    st_autorefresh(interval=int(interval)*1000, key="auto_refresh_key")

placeholder = st.empty()

def render():
    if not subject.strip() or not cls.strip():
        st.info("과목코드·분반을 입력하세요.")
        return

    drv = get_driver(headless)
    try:
        with st.spinner("조회 중..."):
            open_and_search(drv, int(year), int(sem_num), subject)
            quota, current, title = read_info(drv, cls)
    except Exception as e:
        st.error(f"오류: {e}")
        drv.quit()
        return

    drv.quit()
    if quota is None:
        st.error("행을 찾지 못했습니다. 입력을 확인하세요.")
        return

    st.subheader(f"{year}-{SEM_NAME[int(sem_num)]}")
    render_bar(title, current, quota)
    status = "정원 초과/만석" if current >= quota else "여석 있음"
    st.write(f"**상태:** {status}  |  **현재** {current}/{quota}")

with placeholder.container():
    render()
