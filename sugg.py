#!/usr/bin/env python3
# -------------------------------------------------------------
# app.py — SNU 수강신청 실시간 모니터 (Streamlit + Playwright)
#   • 과목코드/분반 입력 → 과목명과 (현재/정원) 막대그래프
#   • 현재 ≥ 정원: 빨간색, 현재 < 정원: 파란색
#   • 자동 새로고침 (최대 10 초)
#   • Playwright 브라우저는 한 번만 띄우고 캐싱 → 훨씬 빠름
#   • 외부 브라우저 다운로드 없음: 시스템 /usr/bin/chromium 사용
# -------------------------------------------------------------

import os
os.environ["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] = "1"  # 브라우저 다운로드 방지

import re
import datetime
import streamlit as st
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

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
PW_TIMEOUT = 8000  # ms (8 초)

CHROMIUM_PATH = "/usr/bin/chromium"  # Streamlit Cloud apt 패키지

st.set_page_config(page_title="SNU 수강신청 모니터", layout="wide")

# ---------- 유틸 ----------
def _parse_int(txt: str) -> int:
    m = re.search(r"\d+", (txt or "").replace(",", ""))
    return int(m.group()) if m else 0

def _render_bar(title: str, current: int, quota: int):
    is_full = (current is not None and quota is not None and current >= quota)
    color   = "#e53935" if is_full else "#1e88e5"
    pct     = 0.0 if quota in (None, 0) else min(max(current or 0, 0) / quota * 100.0, 100.0)
    label   = f"{title} ({current}/{quota})" if title else f"({current}/{quota})"

    st.markdown(
        f"""
        <style>
        .bar-wrap {{ display:flex; align-items:center; gap:12px; }}
        .bar-box  {{ position:relative; flex:1; height:24px; background:#eee; border-radius:8px; overflow:hidden; }}
        .bar-fill {{ position:absolute; top:0; left:0; bottom:0; width:{pct:.2f}%; background:{color}; }}
        .bar-lab  {{ white-space:nowrap; font-weight:600; }}
        </style>
        <div class="bar-wrap">
          <div class="bar-box"><div class="bar-fill"></div></div>
          <div class="bar-lab">{label}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ---------- Playwright 캐싱 ----------
@st.cache_resource(show_spinner=False)
def get_browser():
    """한 번만 Chromium을 띄워서 재사용."""
    if not Path(CHROMIUM_PATH).is_file():
        raise RuntimeError("/usr/bin/chromium 이 설치되어 있지 않습니다. packages.txt 확인!")

    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        executable_path=CHROMIUM_PATH,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    return browser, pw  # Streamlit이 세션 종료 시 자동으로 정리

def fetch_info(year: int, sem_num: int, subject: str, cls: str):
    browser, _ = get_browser()
    context = browser.new_context(locale="ko-KR")
    page    = context.new_page()

    BASE_URL = "https://shine.snu.ac.kr/uni/sugang/cc/cc100.action"
    page.goto(BASE_URL, wait_until="domcontentloaded")

    page.wait_for_selector("#srchOpenSchyy", timeout=PW_TIMEOUT)
    page.evaluate(
        """([year, sem, code]) => {
            document.getElementById('srchOpenSchyy').value = year;
            document.getElementById('srchOpenShtm').value  = sem;
            document.getElementById('srchSbjtCd').value    = code;
            if (typeof fnInquiry === 'function') fnInquiry();
        }""",
        [str(year), SEM_VALUE[int(sem_num)], subject.strip()],
    )

    page.wait_for_selector("table.tbl_basic tbody tr", timeout=PW_TIMEOUT)

    rows = page.locator("table.tbl_basic tbody tr")
    for i in range(rows.count()):
        tds = rows.nth(i).locator("td")
        if tds.count() <= CURR_COL:
            continue
        if any(tds.nth(j).inner_text().strip() == cls.strip() for j in range(tds.count())):
            cap_txt = tds.nth(CAP_COL).inner_text().strip()
            m = re.search(r"\((\d+)\)", cap_txt)
            quota   = int(m.group(1)) if m else _parse_int(cap_txt)
            current = _parse_int(tds.nth(CURR_COL).inner_text().strip())
            title   = tds.nth(TITLE_COL).inner_text().strip()
            context.close()
            return quota, current, title

    context.close()
    return None, None, None

# ---------- Streamlit UI ----------
st.title("SNU 수강신청 실시간 모니터")
st.caption("과목코드/분반을 입력하면 현재/정원을 실시간 막대로 보여줘요.")

with st.sidebar:
    st.subheader("검색 설정")
    subject = st.text_input("과목코드", value="445.206")
    cls     = st.text_input("분반", value="002")
    year    = st.number_input("개설연도", value=DEFAULT_YEAR, step=1)
    sem_num = st.selectbox("학기", [1,2,3,4], index=2, format_func=lambda i: SEM_NAME[i])
    auto    = st.checkbox("자동 새로고침", value=True)
    interval = st.slider("새로고침(초)", 1, 10, value=2)  # ← 최대 10 초로 제한

# 자동 새로고침
st_autorefresh = getattr(st, "autorefresh", None) or getattr(st, "st_autorefresh", None)
if auto and st_autorefresh:
    st_autorefresh(interval=int(interval) * 1000, key="auto_refresh_key_playwright")

placeholder = st.empty()

def render():
    if not subject.strip() or not cls.strip():
        st.info("왼쪽 사이드바에 과목코드와 분반을 입력하세요.")
        return
    try:
        with st.spinner("조회 중..."):
            quota, current, title = fetch_info(int(year), int(sem_num), subject, cls)
    except PWTimeout:
        st.error("페이지 로딩이 8 초 안에 완료되지 않았습니다. 다시 시도해보세요.")
        return
    except Exception as e:
        st.error(f"조회 오류: {e}")
        return

    ts = datetime.datetime.now().strftime("%H:%M:%S")
    if quota is None:
        st.error("행을 찾지 못했습니다. 입력을 확인하세요.")
        st.caption(f"마지막 갱신: {ts}")
        return

    st.subheader(f"{year}-{SEM_NAME[sem_num]}")
    _render_bar(title, current, quota)
    status = "정원 초과/만석" if current >= quota else "여석 있음"
    st.write(f"**상태:** {status}  |  **마지막 갱신:** {ts}")

with placeholder.container():
    render()
