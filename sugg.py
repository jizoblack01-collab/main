# app.py — SNU 수강신청 실시간 모니터 (Streamlit + Playwright)
# - 과목코드/분반 입력 → 과목명과 (현재/정원) 막대그래프 표시
# - 현재 >= 정원: 빨간색, 현재 < 정원: 파란색
# - 자동 새로고침 (st_autorefresh)
# - Selenium/Chromedriver 불필요 (Playwright 사용)

import re
import datetime
import streamlit as st

# ---- UI/상수 ----
DEFAULT_YEAR = 2025
SEM_VALUE = {
    1: "U000200001U000300001",
    2: "U000200001U000300002",
    3: "U000200002U000300001",
    4: "U000200002U000300002",
}
SEM_NAME = {1: "1학기", 2: "여름학기", 3: "2학기", 4: "겨울학기"}

TITLE_COL, CAP_COL, CURR_COL = 6, 13, 14
TIMEOUT = 15000  # ms for Playwright waits

st.set_page_config(page_title="SNU 수강신청 모니터", layout="wide")


# ---- Playwright 설치/준비 (최초 1회) ----
@st.cache_resource(show_spinner=False)
def _ensure_playwright():
    """
    브라우저 미설치 시 자동 설치.
    Streamlit Cloud에서도 동작하도록 런타임에서 설치 시도.
    """
    import os, sys, subprocess
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # 브라우저가 없으면 여기서 예외 → 아래 install 수행
            b = p.chromium.launch(headless=True)
            b.close()
        return True
    except Exception:
        # 브라우저 다운로드
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium", "--no-shell"],
                check=True, capture_output=True, text=True
            )
            return True
        except Exception as e:
            return f"Playwright 브라우저 설치 실패: {e}"


def _parse_int(txt: str) -> int:
    m = re.search(r"\d+", (txt or "").replace(",", ""))
    return int(m.group()) if m else 0


def _render_bar(title: str, current: int, quota: int):
    # 색상 규칙: 현재 ≥ 정원 빨강, 그 외 파랑
    is_full = (current is not None and quota is not None and current >= quota)
    color = "#e53935" if is_full else "#1e88e5"

    if quota in (None, 0):
        pct = 0.0
        quota = 0 if quota is None else quota
    else:
        pct = min(max(current or 0, 0) / quota * 100.0, 100.0)

    label = f"{title} ({current}/{quota})" if title else f"({current}/{quota})"
    st.markdown(
        f"""
        <style>
        .bar-wrap {{ display:flex; align-items:center; gap:12px; }}
        .bar-box  {{ position:relative; flex:1; height:28px; background:#eee; border-radius:8px; overflow:hidden; }}
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


def fetch_info_playwright(year: int, sem_num: int, subject: str, cls: str):
    """
    Playwright로 페이지 열고, 검색 실행 후 테이블에서 (quota, current, title) 추출.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR"
        )
        page = context.new_page()

        BASE_URL = "https://shine.snu.ac.kr/uni/sugang/cc/cc100.action"
        page.goto(BASE_URL, wait_until="domcontentloaded")

        # 검색값 주입 및 조회 실행 (사이트가 사용하는 fnInquiry() 그대로 호출)
        page.wait_for_selector("#srchOpenSchyy", timeout=TIMEOUT)
        page.evaluate(
            """([year, sem, code]) => {
                document.getElementById('srchOpenSchyy').value = year;
                document.getElementById('srchOpenShtm').value  = sem;
                document.getElementById('srchSbjtCd').value    = code;
                if (typeof fnInquiry === 'function') fnInquiry();
            }""",
            [str(year), SEM_VALUE[int(sem_num)], subject.strip()],
        )

        # 조회 결과 테이블 로드 대기
        page.wait_for_selector("table.tbl_basic tbody tr", timeout=TIMEOUT)

        # 행들 순회하며 분반 매칭
        rows = page.locator("table.tbl_basic tbody tr")
        n = rows.count()
        quota = current = None
        title = None
        for i in range(n):
            tds = rows.nth(i).locator("td")
            td_count = tds.count()
            if td_count <= CURR_COL:
                continue

            # 분반 일치 여부 확인
            found = False
            for j in range(td_count):
                txt = tds.nth(j).inner_text().strip()
                if txt == cls.strip():
                    found = True
                    break
            if not found:
                continue

            cap_txt = tds.nth(CAP_COL).inner_text().strip()
            m = re.search(r"\((\d+)\)", cap_txt)
            quota = int(m.group(1)) if m else _parse_int(cap_txt)

            current = _parse_int(tds.nth(CURR_COL).inner_text().strip())
            title   = tds.nth(TITLE_COL).inner_text().strip()
            break

        context.close()
        browser.close()
        return quota, current, title


# ---- Streamlit UI ----
st.title("SNU 수강신청 실시간 모니터 (Playwright)")
st.caption("과목코드와 분반을 입력하면 현재/정원을 실시간 막대로 보여줘요. (Selenium 불필요)")

with st.sidebar:
    st.subheader("검색 설정")
    subject = st.text_input("과목코드", value="445.206", help="예) 445.206")
    cls     = st.text_input("분반", value="002", help="예) 001/002 ... 정확히 입력")
    year    = st.number_input("개설연도", value=DEFAULT_YEAR, step=1)
    sem_num = st.selectbox("학기", options=[1,2,3,4], index=2, format_func=lambda i: SEM_NAME[i])
    auto    = st.checkbox("자동 새로고침", value=True)
    interval = st.slider("새로고침(초)", 1, 30, value=2)

# 자동 새로고침
st_autorefresh = getattr(st, "autorefresh", None) or getattr(st, "st_autorefresh", None)
if auto and st_autorefresh:
    st_autorefresh(interval=int(interval) * 1000, key="auto_refresh_key_playwright")

# 최초 실행 시 브라우저 준비
ready = _ensure_playwright()
if ready is not True:
    st.error(ready if isinstance(ready, str) else "Playwright 준비 실패")
else:
    placeholder = st.empty()

    def render():
        if not subject.strip() or not cls.strip():
            st.info("왼쪽 사이드바에 과목코드와 분반을 입력하세요.")
            return

        with st.spinner("불러오는 중..."):
            quota, current, title = fetch_info_playwright(int(year), int(sem_num), subject.strip(), cls.strip())

        ts = datetime.datetime.now().strftime("%H:%M:%S")
        if quota is None:
            st.error("행을 찾지 못했습니다. 과목코드/분반/학기를 확인하세요.")
            st.caption(f"마지막 갱신: {ts}")
            return

        st.subheader(f"{int(year)}-{SEM_NAME[int(sem_num)]}")
        _render_bar(title, current, quota)
        status = "정원 초과/만석" if current >= quota else "여석 있음"
        st.write(f"**상태:** {status}  |  **마지막 갱신:** {ts}")

    with placeholder.container():
        render()
