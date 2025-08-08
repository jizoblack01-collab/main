#!/usr/bin/env python3
# -------------------------------------------------------------
# app.py — SNU 수강신청 실시간 모니터 (Streamlit + requests)
#   • 과목코드/분반 입력 → 과목명과 (현재/정원) 막대그래프
#   • 현재 ≥ 정원: 빨간색, 현재 < 정원: 파란색
#   • 자동 새로고침 1–10 초
#   • 브라우저/드라이버/Playwright 전혀 사용하지 않음
# -------------------------------------------------------------

import re, datetime, requests, streamlit as st
from bs4 import BeautifulSoup

# -------------------- 상수 --------------------
DEFAULT_YEAR = 2025
SEM_VALUE = {
    1: "U000200001U000300001",
    2: "U000200001U000300002",
    3: "U000200002U000300001",
    4: "U000200002U000300002",
}
SEM_NAME = {1: "1학기", 2: "여름학기", 3: "2학기", 4: "겨울학기"}

TITLE_COL, CAP_COL, CURR_COL = 6, 13, 14
TIMEOUT = 8  # 초

BASE_URL = "https://shine.snu.ac.kr/uni/sugang/cc/cc100.action"
HEADERS = {
    "User-Agent":
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": BASE_URL,
}

# -------------------- 유틸 --------------------
def _parse_int(txt: str) -> int:
    m = re.search(r"\d+", (txt or "").replace(",", ""))
    return int(m.group()) if m else 0

def _render_bar(title: str, current: int, quota: int):
    is_full = current is not None and quota is not None and current >= quota
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

# -------------------- 데이터 fetch --------------------
@st.cache_resource(show_spinner=False)
def get_session():
    """세션을 한 번만 생성해 쿠키 재사용 → 평균 응답 0.3 s."""
    s = requests.Session()
    s.headers.update(HEADERS)
    return s

def fetch_info(year: int, sem_num: int, subject: str, cls: str):
    sess = get_session()

    # 1) 첫 GET (hidden 필드 수집)
    r = sess.get(BASE_URL, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    # 2) 폼 필드 모으기
    payload = {inp.get("name"): inp.get("value", "")
               for inp in soup.select("form input") if inp.get("name")}
    payload.update({
        "srchOpenSchyy": str(year),
        "srchOpenShtm" : SEM_VALUE[int(sem_num)],
        "srchSbjtCd"   : subject.strip(),
    })

    # 3) POST 조회
    r2 = sess.post(BASE_URL, data=payload, timeout=TIMEOUT)
    r2.raise_for_status()
    soup2 = BeautifulSoup(r2.text, "lxml")

    # 4) 테이블 파싱
    rows = soup2.select("table.tbl_basic tbody tr")
    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) <= CURR_COL:
            continue
        if any(td.get_text(strip=True) == cls.strip() for td in tds):
            cap_txt = tds[CAP_COL].get_text(" ", strip=True)
            m = re.search(r"\((\d+)\)", cap_txt)
            quota   = int(m.group(1)) if m else _parse_int(cap_txt)
            current = _parse_int(tds[CURR_COL].get_text(" ", strip=True))
            title   = tds[TITLE_COL].get_text(" ", strip=True)
            return quota, current, title
    return None, None, None  # 매칭 실패

# -------------------- Streamlit UI --------------------
st.set_page_config(page_title="SNU 수강신청 모니터", layout="wide")
st.title("SNU 수강신청 실시간 모니터 (Requests 버전)")

with st.sidebar:
    st.subheader("검색 설정")
    subject = st.text_input("과목코드", value="445.206")
    cls     = st.text_input("분반", value="002")
    year    = st.number_input("개설연도", value=DEFAULT_YEAR, step=1)
    sem_num = st.selectbox("학기", [1,2,3,4], index=2, format_func=lambda i: SEM_NAME[i])
    auto    = st.checkbox("자동 새로고침", value=True)
    interval = st.slider("새로고침(초)", 1, 10, value=2)  # 최대 10 초

# 자동 새로고침
st_autorefresh = getattr(st, "autorefresh", None) or getattr(st, "st_autorefresh", None)
if auto and st_autorefresh:
    st_autorefresh(interval=int(interval) * 1000, key="auto_refresh_key_requests")

placeholder = st.empty()

def render():
    if not subject.strip() or not cls.strip():
        st.info("왼쪽 사이드바에 과목코드와 분반을 입력하세요.")
        return

    try:
        with st.spinner("조회 중..."):
            quota, current, title = fetch_info(int(year), int(sem_num), subject, cls)
    except Exception as e:
        st.error(f"요청 실패: {e}")
        return

    ts = datetime.datetime.now().strftime("%H:%M:%S")
    if quota is None:
        st.error("행을 찾지 못했습니다. 입력을 확인하세요.")
        st.caption(f"마지막 갱신: {ts}")
        return

    st.subheader(f"{year}-{SEM_NAME[sem_num]}")
    _render_bar(title, current, quota)
    status = "정원 초과/만석" if current >= quota else "여석 있음"
    st.write(f"**상태:** {status}  |  **마지막 갱신**
