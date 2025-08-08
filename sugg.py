# Streamlit + Selenium (env 무시 강제판)
# - chromium/chromedriver 고정 경로만 사용
# - env에 chromedriver가 들어있어도 절대 binary_location에 넣지 않음
# - 진단 정보 출력 포함

import os, re, datetime, traceback, subprocess
import streamlit as st
from shutil import which
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

st.set_page_config(page_title="SNU 수강신청 모니터", layout="wide")

DEFAULT_YEAR = 2025
SEM_NAME = {1:"1학기",2:"여름학기",3:"2학기",4:"겨울학기"}
SEM_VALUE = {
    1: "U000200001U000300001",
    2: "U000200001U000300002",
    3: "U000200002U000300001",
    4: "U000200002U000300002",
}
TITLE_COL, CAP_COL, CURR_COL = 6, 13, 14
TIMEOUT = 12

# ------------------ 경로 강제 ------------------
# Streamlit Cloud의 apt 패키지 기준 고정
HARDCODED_BROWSER = "/usr/bin/chromium"
HARDCODED_DRIVER  = "/usr/bin/chromedriver"

def _exists_exec(p): 
    return bool(p) and os.path.exists(p) and os.access(p, os.X_OK)

def _diagnostics():
    out = {}
    def cmd(o, *args):
        try:
            out[o] = subprocess.check_output(args, text=True).strip()
        except Exception as e:
            out[o] = f"ERR: {e}"
    cmd("chromium --version", "bash", "-lc", "chromium --version || true")
    cmd("chromedriver --version", "bash", "-lc", "chromedriver --version || true")
    out["GOOGLE_CHROME_BIN"]   = os.environ.get("GOOGLE_CHROME_BIN", "")
    out["CHROMEDRIVER_PATH"]   = os.environ.get("CHROMEDRIVER_PATH", "")
    out["BROWSER exists?"]     = f"{HARDCODED_BROWSER} -> {_exists_exec(HARDCODED_BROWSER)}"
    out["DRIVER exists?"]      = f"{HARDCODED_DRIVER} -> {_exists_exec(HARDCODED_DRIVER)}"
    return out

@st.cache_resource(show_spinner=False)
def get_driver():
    # 어떤 환경변수도 보지 않음. 오직 고정 경로만 사용.
    opt = webdriver.ChromeOptions()
    opt.add_argument("--headless=new")
    opt.add_argument("--no-sandbox")
    opt.add_argument("--disable-dev-shm-usage")
    opt.add_argument("--window-size=1600,1000")
    opt.add_argument("--lang=ko-KR")

    # 브라우저 binary_location은 반드시 'chromium' 같은 브라우저 실행파일이어야 함
    if not _exists_exec(HARDCODED_BROWSER):
        # 마지막 시도로 which 탐색
        guess = which("chromium") or which("google-chrome") or which("google-chrome-stable")
        if guess and "chromedriver" not in (guess.lower()):
            opt.binary_location = guess
        else:
            opt.binary_location = HARDCODED_BROWSER  # 어차피 존재하지 않으면 아래에서 에러 터지고 로그로 확인됨
    else:
        opt.binary_location = HARDCODED_BROWSER

    # 드라이버는 Service로만 지정 (binary_location에 절대 넣지 않음)
    if not _exists_exec(HARDCODED_DRIVER):
        drv_guess = which("chromedriver") or "/usr/lib/chromium/chromedriver"
    else:
        drv_guess = HARDCODED_DRIVER

    # 방어: 혹시라도 chromedriver가 binary_location에 들어가면 즉시 막기
    if "chromedriver" in (opt.binary_location or "").lower():
        raise RuntimeError(f"binary_location is chromedriver! {opt.binary_location}")

    return webdriver.Chrome(service=Service(drv_guess), options=opt)

def parse_int(txt: str) -> int:
    m = re.search(r"\d+", (txt or "").replace(",", ""))
    return int(m.group()) if m else 0

def open_and_search(drv, year:int, sem_num:int, subject:str):
    drv.get("https://shine.snu.ac.kr/uni/sugang/cc/cc100.action")
    WebDriverWait(drv, TIMEOUT).until(EC.presence_of_element_located((By.ID, "srchOpenSchyy")))
    drv.execute_script(
        """
        document.getElementById('srchOpenSchyy').value = arguments[0];
        document.getElementById('srchOpenShtm').value  = arguments[1];
        document.getElementById('srchSbjtCd').value    = arguments[2];
        fnInquiry();
        """,
        str(year), SEM_VALUE[int(sem_num)], subject.strip()
    )

def read_info(drv, cls: str):
    WebDriverWait(drv, TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.tbl_basic tbody tr")))
    for tr in drv.find_elements(By.CSS_SELECTOR, "table.tbl_basic tbody tr"):
        tds = tr.find_elements(By.TAG_NAME, "td")
        if len(tds) <= CURR_COL:
            continue
        if any(td.text.strip() == cls.strip() for td in tds):
            cap_txt = tds[CAP_COL].text
            quota_m = re.search(r"\((\d+)\)", cap_txt)
            quota   = int(quota_m.group(1)) if quota_m else parse_int(cap_txt)
            current = parse_int(tds[CURR_COL].text)
            title   = tds[TITLE_COL].text.strip()
            return quota, current, title
    return None, None, None

def fetch_info(year:int, sem_num:int, subject:str, cls:str):
    drv = get_driver()
    open_and_search(drv, year, sem_num, subject)
    return read_info(drv, cls)

def render_bar(title: str, current: int, quota: int):
    color = "#e53935" if (current is not None and quota is not None and current >= quota) else "#1e88e5"
    if quota in (None, 0):
        pct = 0.0
        quota = 0 if quota is None else quota
    else:
        pct = min(max(current or 0, 0) / quota * 100.0, 100.0)
    label = f"{title} ({current}/{quota})" if title else f"({current}/{quota})"
    st.markdown(f"""
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
    """, unsafe_allow_html=True)

# ------------------ UI ------------------
st.title("SNU 수강신청 실시간 모니터 (Selenium, env 무시판)")
with st.expander("진단 정보 보기"):
    diag = _diagnostics()
    st.json(diag)

with st.sidebar:
    st.subheader("검색 설정")
    subject = st.text_input("과목코드", value="445.206")
    cls     = st.text_input("분반", value="002")
    year    = st.number_input("개설연도", value=DEFAULT_YEAR, step=1)
    sem_num = st.selectbox("학기", options=[1,2,3,4], index=2, format_func=lambda i: SEM_NAME[i])
    auto    = st.checkbox("자동 새로고침", value=True)
    interval = st.slider("새로고침(초)", 1, 30, value=2)

# 자동 새로고침
st_autorefresh = getattr(st, "autorefresh", None) or getattr(st, "st_autorefresh", None)
if auto and st_autorefresh:
    st_autorefresh(interval=int(interval) * 1000, key="auto_refresh_key_selenium_force")

placeholder = st.empty()

def render():
    try:
        if not subject.strip() or not cls.strip():
            st.info("왼쪽 사이드바에 과목코드와 분반을 입력하세요.")
            return
        with st.spinner("불러오는 중..."):
            quota, current, title = fetch_info(int(year), int(sem_num), subject.strip(), cls.strip())
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        if quota is None:
            st.error("행을 찾지 못했습니다. 과목코드/분반/학기를 확인하세요.")
            st.caption(f"마지막 갱신: {ts}")
            return
        st.subheader(f"{int(year)}-{SEM_NAME[int(sem_num)]}")
        render_bar(title, current, quota)
        status = "정원 초과/만석" if current >= quota else "여석 있음"
        st.write(f"**상태:** {status}  |  **마지막 갱신:** {ts}")
    except Exception:
        st.error("드라이버 실행 실패")
        st.code(traceback.format_exc())

with placeholder.container():
    render()
