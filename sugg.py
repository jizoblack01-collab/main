import re, time, datetime, streamlit as st, matplotlib.pyplot as plt
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# -------- 설정 --------
YEAR, SEM_NUM      = 2025, 3
INTERVAL_SEC, TIMEOUT = 3, 10
TITLE, QUOTA, CURR = 6, 13, 14

COURSE_RAW = [
    ("445.206","002"), ("E12.113","001"),
    ("445.202","002"), ("M1569.003300","001"),
    ("3348.203","001"),
]
SEM_VAL = {1:"U000200001U000300001",2:"U000200001U000300002",
           3:"U000200002U000300001",4:"U000200002U000300002"}

plt.rcParams.update({"font.family":"Malgun Gothic","axes.unicode_minus":False})

# -------- Selenium driver --------
CHROME_BIN="/usr/bin/chromium"
CHROMEDRIVER="/usr/bin/chromedriver"
def new_driver():
    opt=Options()
    opt.binary_location=CHROME_BIN
    opt.add_argument("--headless=new")
    opt.add_argument("--no-sandbox")
    opt.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(service=Service(CHROMEDRIVER),options=opt)

def open_search(d,code):
    d.get("https://shine.snu.ac.kr/uni/sugang/cc/cc100.action")
    WebDriverWait(d,TIMEOUT).until(EC.presence_of_element_located((By.ID,"srchOpenSchyy")))
    d.execute_script("""
        document.getElementById('srchOpenSchyy').value=arguments[0];
        document.getElementById('srchOpenShtm').value =arguments[1];
        document.getElementById('srchSbjtCd').value   =arguments[2];
        fnInquiry();""",str(YEAR),SEM_VAL[SEM_NUM],code)

toi=lambda s:int(re.search(r"\d+",s.replace(",","")).group()) if re.search(r"\d+",s) else 0
def fetch_row(d,cls):
    WebDriverWait(d,TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR,"table.tbl_basic tbody tr")))
    for tr in d.find_elements(By.CSS_SELECTOR,"table.tbl_basic tbody tr"):
        tds=tr.find_elements(By.TAG_NAME,"td")
        if len(tds)<=CURR: continue
        if any(td.text.strip()==cls for td in tds):
            title=tds[TITLE].text.strip()
            qm=re.search(r"\((\d+)\)",tds[QUOTA].text)
            quota=int(qm.group(1)) if qm else toi(tds[QUOTA].text)
            current=toi(tds[CURR].text)
            return title,quota,current
    return "미확인",0,0
def fetch_current(d,cls):
    WebDriverWait(d,TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR,"table.tbl_basic tbody tr")))
    for tr in d.find_elements(By.CSS_SELECTOR,"table.tbl_basic tbody tr"):
        tds=tr.find_elements(By.TAG_NAME,"td")
        if len(tds)<=CURR: continue
        if any(td.text.strip()==cls for td in tds):
            return toi(tds[CURR].text)
    return 0

# -------- Streamlit UI --------
st.set_page_config("실시간 충원률",layout="wide")
st.title("실시간 충원률 모니터")

@st.cache_resource(hash_funcs={webdriver.Chrome:lambda _:None})
def init(raw):
    cache=[]
    for subj,cls in raw:
        d=new_driver(); open_search(d,subj)
        title,quota,_=fetch_row(d,cls)
        cache.append({"title":title,"quota":quota,"driver":d,"cls":cls})
    return cache
courses=init(COURSE_RAW)

fig,ax=plt.subplots(figsize=(9,4.5)); canvas=st.pyplot(fig)

while True:
    ratios=titles=currents=quotas=colors=[]; ratios=[]; titles=[]; currents=[]; quotas=[]; colors=[]
    for c in courses:
        cur=fetch_current(c["driver"],c["cls"])
        r=cur/c["quota"] if c["quota"] else 0
        ratios.append(r); titles.append(c["title"])
        currents.append(cur); quotas.append(c["quota"])
        colors.append("red" if r>=1 else "steelblue")
        c["driver"].execute_script("fnInquiry();")

    order=sorted(range(len(ratios)),key=lambda i:ratios[i],reverse=True)
    ratios=[ratios[i] for i in order]; titles=[titles[i] for i in order]
    currents=[currents[i] for i in order]; quotas=[quotas[i] for i in order]; colors=[colors[i] for i in order]

    ax.clear(); ax.set_xlim(0,1.15); ax.set_yticks([]); ax.set_xlabel("충원률")
    ax.set_title(f"[현황] {datetime.datetime.now():%H:%M:%S}")
    bars=ax.barh(range(len(titles)),ratios,color=colors)
    for bar,r,cur,q,t in zip(bars,ratios,currents,quotas,titles):
        y=bar.get_y()+bar.get_height()/2
        ax.text(r+0.01,y,f"{cur}/{q} ({r:.3f})",va="center",fontsize=9)
        ax.text(1.05 ,y,t,           va="center",fontsize=10)
    canvas.pyplot(fig); time.sleep(INTERVAL_SEC)
