# app.py — SNU 수강신청 실시간 모니터 (Streamlit, no Selenium)
# - 과목코드/분반 → 과목명과 (현재/정원) 막대그래프
# - 현재 >= 정원: 빨간색, 현재 < 정원: 파란색
# - 자동 새로고침 지원 (st_autorefresh)
# - 서버에 직접 요청 (requests + BeautifulSoup), 크롬/드라이버 불필요

import datetime
import re
import requests
import streamlit as st
from bs4 import BeautifulSoup

# 기본 설정
DEFAULT_YEAR = 2025
DEFAULT_SEM  = 3  # 1:1학기, 2:여름, 3:2학기, 4:겨울
TIMEOUT = 15  # HTTP 타임아웃(s)

SEM_VALUE = {
    1: "U000200001U000300001",
    2: "U000200001U000300002",
    3: "U000200002U000300001",
    4: "U000200002U000300002",
}
SEM_NAME = {1: "1학기", 2: "여름학기", 3: "2학기", 4: "겨울학기"}

TITLE_COL = 6
CAP_COL   = 13
CURR_COL  = 14

BASE_URL = "https://shine.snu.ac.kr/uni/sugang/cc/cc100.action"

st.set_page_config(page_title="SNU 수강신청 모니터", layout="wide")

def parse_int(txt: str) -> int:
    m = re.search(r"\d+", (txt or "").replace(",", ""))
    return int(m.group()) if m else 0

def _collect_form_inputs(soup: BeautifulSoup) -> dict:
    """검색 폼의 hidden/input 값들을 수집해서 그대로 전송에 활용 (안전빵)."""
    payload = {}
    for inp in soup.select("form input"):
        name = inp.get("name")
        if not name:
            continue
        # checkbox/radio 미선택은 건너뜀
        typ = (inp.get("type") or "").lower()
        if typ in ("checkbox", "radio") and not inp.has_attr("checked"):
            continue
        payload[name] = inp.get("value", "")
    return payload

def fetch_info_http(year: int, sem_num: int, subject: str, cls: str):
    """HTTP로 직접 조회해서 (quota, current, title) 반환."""
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36",
        "Referer": BASE_URL,
    }
    with requests.Session() as s:
        # 초기 페이지 접근 (세션/쿠키 획득 및 hidden 필드 수집)
        r = s.get(BASE_URL, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        payload = _collect_form_inputs(soup)
        # 검색 조건 주입
        payload["srchOpenSchyy"] = str(year)
        payload["srchOpenShtm"]  = SEM_VALUE[int(sem_num)]
        payload["srchSbjtCd"]    = subject.strip()

        # 조회 (보통 동일 endpoint POST)
        r2 = s.post(BASE_URL, data=payload, headers=headers, timeout=TIMEOUT)
        r2.raise_for_status()
        soup2 = BeautifulSoup(r2.text, "lxml")

        # 테이블 파싱
        rows = soup2.select("table.tbl_basic tbody tr")
        if not rows:
            return None, None, None

        for tr in rows:
            tds = tr.find_all("td")
            if len(tds) <= CURR_COL:
                continue
            # 분반 매칭
            if any((td.get_text(strip=True) == cls.strip()) for td in tds):
                # 정원: "(80)" 형태와 숫자 혼재 처리
                cap_txt = tds[CAP_COL].get_text(" ", strip=True)
                quota_m = re.search(r"\((\d+)\)", cap_txt)
                quota   = int(quota_m.group(1)) if quota_m else parse_int(cap_txt)

                current = parse_int(tds[CURR_COL].get_text(" ", strip=True))
                title   = tds[TITLE_COL].get_text(" ", strip=True)
                return quota, current, title

        return None, None, None

def render_bar(title: str, current: int, quota: int):
    # 색상 규칙: 현재 ≥ 정원 빨강, 그 외 파랑
    is_full = (current is not None and quota is not None and current >= quota)
    color = "#e53935" if is_full else "#1e88e5"

    if quota in (None, 0):
        pct = 0.0
        quota = 0 if quota is None else quota
    else:
        pct = min(max(current or 0, 0) / quota * 100.0, 100.0)

    label = f"{title} ({current}/{quota})" if title else f"({current}/{quota})"
    bar_html = f"""\
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
    """
    st.markdown(bar_html, unsafe_allow_html=True)

# ---- UI ----
st.title("SNU 수강신청 실시간 모니터")
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
    st_autorefresh(interval=int(interval) * 1000, key="auto_refresh_key_http")

placeholder = st.empty()

def render():
    if not subject.strip() or not cls.strip():
        st.info("왼쪽 사이드바에 과목코드와 분반을 입력하세요.")
        return

    with st.spinner("불러오는 중..."):
        quota, current, title = fetch_info_http(int(year), int(sem_num), subject.strip(), cls.strip())

    ts = datetime.datetime.now().strftime("%H:%M:%S")
    if quota is None:
        st.error("행을 찾지 못했습니다. 과목코드/분반/학기를 확인하세요.")
        st.caption(f"마지막 갱신: {ts}")
        return

    st.subheader(f"{int(year)}-{SEM_NAME[int(sem_num)]}")
    render_bar(title, current, quota)
    status = "정원 초과/만석" if current >= quota else "여석 있음"
    st.write(f"**상태:** {status}  |  **마지막 갱신:** {ts}")

with placeholder.container():
    render()
