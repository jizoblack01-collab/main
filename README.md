# SNU 수강신청 모니터 (Streamlit, no Selenium)

과목코드/분반을 입력하면 현재 수강인원/정원을 막대그래프로 표시합니다.
- 현재 ≥ 정원: 빨간색
- 현재 < 정원: 파란색
- 자동 새로고침 (기본 2초)
- **Selenium/Chrome 드라이버 불필요** (requests + BeautifulSoup 사용)

## 설치
```bash
pip install -r requirements.txt
