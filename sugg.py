# app.py
import re, time, datetime
import streamlit as st
import matplotlib.pyplot as plt
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ── 환경 파라미터 ──────────────────────────────────────
YEAR, SEM_NUM     = 2025, 3        # 1:1학기 2:여름 3:2학기 4:겨울
INTERVAL_SEC      = 3              # 새로고침 간격
TIMEOUT           = 10             # Selenium 대기
TITLE, QUOTA, CURR= 6, 13, 14      # 테이블 열(0-based)

SEM_VAL = {1:"U000200001U000300001", 2:"U000200001U000300002",
           3:"U000200002U000300001", 4:"U000200002U000300002"}

COURSE_RAW = [
    ("445.206",      "002"),   # 결정학개론
    ("E12.113",      "001"),   # 한국현대의 삶과 문화
    ("445.202",      "002"),   # 재료현대물리
    ("M1569.003300", "001"),   # 현대재료물리화학
    ("3348.203",     "001"),   # 기본물리수학
]

# ── 한글 글꼴 & Matplotlib ────────────────────────────
plt.rcParams.update({"font.family": "Malgun Gothic",
                     "axes.unicode_minus": False})

# ── 크롬 실행 파일·드라이버 경로 (apt 패키지) ──────────
CHROME_BIN     = "/usr/bin/chromium"
CHROMEDRIVER   = "/usr/bin/chromedriver"


def new_driver():
    opts = Options()
    opts.binary_location = CHROME_BIN
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--single-process")
    return webdriver.Chrome(service=Service(CHROMEDRIVER), options=opts)

def open_search(drv, code):
    drv.get("https://shine.snu.ac.kr/uni/sugang/cc/cc100.action")
    WebDriverWait(drv, TIMEOUT).until(
        EC.presence_of_element_located((By.ID, "srchOpenSchyy")))
    drv.execute_script("""
        document.getElementById('srchOpenSchyy').value = arguments[0];
        document.getElementById('srchOpenShtm').value  = arguments[1];
        document.getElementById('srchSbjtCd').value    = arguments[2];
        fnInquiry();""", str(YEAR), SEM_VAL[SEM_NUM], code)

to_int = lambda t: int(re.search(r"\d+", t.replace(",", "")).group()) if re.search(r"\d+", t) else 0

def fetch_row(drv, cls):
    WebDriverWait(drv, TIMEOUT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "table.tbl_basic tbody tr")))
    for tr in drv.find_elements(By.CSS_SELECTOR, "table.tbl_basic tbody tr"):
        tds = tr.find_elements(By.TAG_NAME, "td")
        if len(tds) <= CURR: continue
        if any(td.text.strip() == cls for td in tds):
            title  = tds[TITLE].text.strip()
            qmatch = re.search(r"\((\d+)\)", tds[QUOTA].text)
            quota  = int(qmatch.group(1)) if qmatch else to_int(tds[QUOTA].text)
            current= to_int(tds[CURR].text)
            return title, quota, current
    return "미확인", 0, 0

def fetch_current(drv, cls):
    WebDriverWait(drv, TIMEOUT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "table.tbl_basic tbody tr")))
    for tr in drv.find_elements(By.CSS_SELECTOR, "table.tbl_basic tbody tr"):
        tds = tr.find_elements(By.TAG_NAME, "td")
        if len(tds) <= CURR: continue
        if any(td.text.strip() == cls for td in tds):
            return to_int(tds[CURR].text)
    return 0

# ── Streamlit 초기화 ──────────────────────────────────
st.set_page_config("실시간 충원률", layout="wide")
st.title("실시간 충원률 모니터")

@st.cache_resource(hash_funcs={webdriver.Chrome: lambda _: None})
def init_courses(raw):
    cached=[]
    for subj, cls in raw:
        d=new_driver(); open_search(d, subj)
        title, quota, _ = fetch_row(d, cls)
        cached.append(dict(title=title, quota=quota, driver=d, cls=cls))
    return cached

courses = init_courses(COURSE_RAW)

fig, ax = plt.subplots(figsize=(9,4.5))
plot_area = st.pyplot(fig)

# ── 주기적 갱신 루프 ─────────────────────────────────
while True:
    ratios=titles=currents=quotas=colors=[]; ratios=[]; titles=[]; currents=[]; quotas=[]; colors=[]
    for c in courses:
        cur = fetch_current(c["driver"], c["cls"])
        ratio = cur / c["quota"] if c["quota"] else 0
        ratios.append(ratio); titles.append(c["title"])
        currents.append(cur); quotas.append(c["quota"])
        colors.append("red" if ratio>=1 else "steelblue")
        c["driver"].execute_script("fnInquiry();")

    order = sorted(range(len(ratios)), key=lambda i: ratios[i], reverse=True)
    ratios  = [ratios[i]   for i in order]
    titles  = [titles[i]   for i in order]
    currents= [currents[i] for i in order]
    quotas  = [quotas[i]   for i in order]
    colors  = [colors[i]   for i in order]

    ax.clear(); ax.set_xlim(0,1.15); ax.set_yticks([]); ax.set_xlabel("충원률")
    ax.set_title(f"[현황] {datetime.datetime.now():%H:%M:%S}")

    bars = ax.barh(range(len(titles)), ratios, color=colors)
    for bar,r,cur,q,t in zip(bars,ratios,currents,quotas,titles):
        y=bar.get_y()+bar.get_height()/2
        ax.text(r+0.01,y,f"{cur}/{q} ({r:.3f})",va="center",fontsize=9)
        ax.text(1.05 ,y,t,              va="center",fontsize=10)

    plot_area.pyplot(fig)
    time.sleep(INTERVAL_SEC)

