import streamlit as st
import matplotlib.pyplot as plt
import datetime, re, time
from matplotlib.animation import FuncAnimation

# ---- (Selenium·fetch_row·fetch_current 등 기존 유틸 함수 그대로 들고옴) ----
#              YEAR, SEM_NUM, COURSES, new_driver(), open_search() ...

# ── Streamlit 페이지 설정 ──────────────────────────
st.set_page_config(page_title="실시간 충원률", layout="wide")
st.title("실시간 충원률 모니터")

# ── 그래프용 figure 지정 ───────────────────────────
fig, ax = plt.subplots(figsize=(8, 4))
plot_area = st.pyplot(fig)      # Streamlit에 빈 그래프 자리 확보

# ── 초기 Selenium 로딩 (캐시) ──────────────────────
@st.cache_resource
def init_courses():
    data = []
    for subj, cls in COURSES:
        d = new_driver(); open_search(d, subj)
        title, quota, _ = fetch_row(d, cls)
        data.append(dict(title=title, quota=quota, driver=d, cls=cls))
    return data
courses = init_courses()

# ── 실시간 루프 (Streamlit) ────────────────────────
INTERVAL = 1        # 초

while True:
    ratios, titles, currents, quotas, colors = [], [], [], [], []
    for c in courses:
        cur = fetch_current(c["driver"], c["cls"])
        ratio = cur / c["quota"] if c["quota"] else 0
        ratios.append(ratio);  titles.append(c["title"])
        currents.append(cur);  quotas.append(c["quota"])
        colors.append("red" if ratio >= 1 else "steelblue")
        c["driver"].execute_script("fnInquiry();")

    # 충원률 순 정렬
    order = sorted(range(len(ratios)), key=lambda i: ratios[i], reverse=True)
    ratios = [ratios[i]   for i in order]
    titles = [titles[i]   for i in order]
    currents= [currents[i] for i in order]
    quotas = [quotas[i]   for i in order]
    colors = [colors[i]   for i in order]

    # Matplotlib 그리기
    ax.clear(); ax.set_xlim(0, 1.15); ax.set_yticks([])
    ax.set_title(f"[현황] {datetime.datetime.now():%H:%M:%S}")
    bars = ax.barh(range(len(titles)), ratios, color=colors)
    for bar, r, cur, q, t in zip(bars, ratios, currents, quotas, titles):
        y = bar.get_y() + bar.get_height()/2
        ax.text(r+0.01, y, f"{cur}/{q} ({r:.3f})", va="center", fontsize=8)
        ax.text(1.05 , y, t,               va="center", fontsize=9)
    plot_area.pyplot(fig)   # Streamlit에 그림 갱신
    time.sleep(INTERVAL)
