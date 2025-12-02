# app.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os, shutil, re, certifi, requests
from bs4 import BeautifulSoup
import datetime as dt
import yfinance as yf
from pykrx import stock

# 🚨 [수정된 부분]: VS Code 환경에서 .env 파일 로드를 위한 코드 추가
# load_dotenv는 os.getenv가 .env 파일의 변수를 읽을 수 있도록 해줍니다.
try:
    from dotenv import load_dotenv
    # 프로젝트의 루트 디렉토리에 있는 .env 파일을 로드
    load_dotenv()
    print("SUCCESS: .env 파일 로드 완료.")
except ImportError:
    print("WARNING: python-dotenv 라이브러리가 설치되지 않았습니다. pip install python-dotenv 로 설치해 주세요.")
    
# 💡 lstm_model.py, predict.py, data_loader.py, news_scraper.py 파일이 같은 폴더에 있어야 합니다.
try:
    # 모듈 임포트 시도
    from lstm_model import train_lstm_model
    from predict import predict_next_month
    
    # 🚨 get_english_name 임포트 제거 🚨
    from data_loader import load_stock_data, get_english_name
    
    # 🚨 뉴스 크롤러 함수 이름만 임포트합니다. 🚨
    from news_scraper import scrape_investing_news_titles_selenium 
    
    HAS_MODEL_FILES = True
except ImportError as e:
    st.warning(f"경고: 필요한 모듈(lstm_model, predict, data_loader, news_scraper) 중 일부를 찾을 수 없습니다. ({e})")
    st.warning("모델 학습 및 예측, 뉴스 기능이 비활성화됩니다. 파일을 확인해 주세요.")
    HAS_MODEL_FILES = False

# ── 설정 ──
st.set_page_config(page_title="LSTM 예측기", layout="wide")
st.markdown("""
<h1 style='text-align: center; color: #1E90FF; font-weight: bold;'>주식 이름으로 LSTM 예측</h1>
<p style='text-align: center; color: #666;'>Volume 포함 다변량 LSTM + 30일 예측 + AI 리포트</p>
""", unsafe_allow_html=True)

MODEL_DIR = "models"
os.makedirs(MODEL_DIR, exist_ok=True) # 모델 저장 디렉토리 생성

@st.cache_data(show_spinner=False, ttl=3600)
def get_korean_fundamentals(code: str) -> dict:
    # PER, PBR 항목을 포함하는 딕셔너리
    data = {"per": None, "pbr": None, "psr":None, "foreign_ownership": None, "dividend_yield": None, "market_cap": None}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9"
    }
    
    # ────────────────────────────────
    # 🚨 [버그 수정]: 시가총액 파싱 로직 개선
    # - '595조 5,156억' (대형주) 와 '784억' (중소형주) 케이스를 모두 조 단위(float)로 정확히 변환
    # ────────────────────────────────
    def parse_money(text: str) -> float:
        """
        텍스트에서 금액을 조/억 단위로 파싱하여 '조 원' 단위 float으로 반환합니다.
        (예: '595조 5,156억' -> 595.5156, '784억' -> 0.0784)
        """
        text = re.sub(r"[,\s]", "", text) # 쉼표와 공백 제거
        val = 0.0

        # 1. '조' 단위 파싱 (가장 먼저 처리)
        trillion_match = re.search(r"([\d\.]+)조", text)
        if trillion_match:
            val += float(trillion_match.group(1))
            # 파싱된 '조' 부분 제거. 남은 텍스트는 '억' 단위여야 함.
            text = re.sub(r"[\d\.]*조", "", text) # 예: "595조5156억" -> "5156억"
        
        # 2. '억' 단위 파싱 (남은 텍스트에서, '억' 단위 표시가 없어도 숫자는 억으로 간주)
        # 이 로직은 '784억' 케이스와 '5156억' 케이스를 모두 처리합니다.
        billion_match = re.search(r"([\d\.]+)", text)
        if billion_match:
            billion_value = float(billion_match.group(1))
            # 억을 조로 변환 (1조 = 10,000억)하여 val에 추가
            val += billion_value / 10_000 
            
        return val


    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        resp = requests.get(url, headers=headers, timeout=20, verify=certifi.where())
        resp.raise_for_status()
    except Exception as e:
        st.warning(f"네이버 접속 실패: {e}")
        return data

    soup = BeautifulSoup(resp.text, "lxml")

    # ────────────────────────────────
    # 1. PER & PBR & PSR
    # ────────────────────────────────
    per_tag = soup.find("em", id="_per")
    if per_tag:
        per_text = per_tag.get_text(strip=True).replace(",", "")
        try:
            data["per"] = round(float(per_text), 2)
        except:
            pass
            
    pbr_tag = soup.find("em", id="_pbr")
    if pbr_tag:
        pbr_text = pbr_tag.get_text(strip=True).replace(",", "")
        try:
            data["pbr"] = round(float(pbr_text), 2)
        except:
            pass

    psr_tag = soup.find("em", id="_psr")
    if psr_tag:
        psr_text = psr_tag.get_text(strip=True).replace(",", "")
        try:
            data["psr"] = round(float(psr_text), 2)
        except:
            pass
    # ────────────────────────────────
    # 2. 외국인 지분율
    # ────────────────────────────────
    for pattern in [
        r"외국인[^\d]*([\d,]+\.\d+)%",
        r"외국인\s*지분율[^\d]*([\d,]+\.\d+)%",
        r"외국인\s*[\[\(][^%\d]*([\d,]+\.\d+)%[\]\)]"
    ]:
        m = re.search(pattern, soup.get_text())
        if m:
            data["foreign_ownership"] = float(m.group(1).replace(",", ""))
            break

    # ────────────────────────────────
    # 3. 배당수익률
    # ────────────────────────────────
    div_text = soup.select_one("th:contains('배당수익률')")
    if div_text:
        row = div_text.find_parent("tr")
        if row:
            tds = row.find_all("td")
            for td in tds:
                txt = td.get_text(strip=True)
                m = re.search(r"([\d,]+\.\d+)%", txt)
                if m:
                    data["dividend_yield"] = float(m.group(1).replace(",", ""))
                    break

    # fallback
    if not data["dividend_yield"]:
        for p in [
            r"배당수익률[^\d]*([\d,]+\.\d+)%",
            r"배당수익률\s*\[?\s*TTM\s*\]?\s*[^\d]*([\d,]+\.\d+)%",
            r"배당수익률\s*[:\-]?\s*([\d,]+\.\d+)%"
        ]:
            m = re.search(p, soup.get_text())
            if m:
                data["dividend_yield"] = float(m.group(1).replace(",", ""))
                break

    # ────────────────────────────────
    # 4. 시가총액 (PSR 계산 로직은 완전히 삭제됨)
    # ────────────────────────────────
    market_cap = None
    # 🚨 annual_revenue = None # 연간 매출액 (조 원 단위) 제거

    # 4.1 시가총액: <em id="_market_sum">
    mcap_tag = soup.find("em", id="_market_sum")
    mcap_text = ""
    if mcap_tag:
        mcap_text = mcap_tag.get_text(strip=True)
        # 🚨 수정된 parse_money 함수 호출
        market_cap = parse_money(mcap_text) # 조 원 단위

    # data에 시가총액 저장 (조 원 단위, 소수점 2자리)
    if market_cap is not None and market_cap > 0:
        data["market_cap"] = round(market_cap, 2)
    else:
        if not mcap_tag:
            st.warning(f"시가총액 조회 실패: Naver 페이지에서 '_market_sum' 태그를 찾을 수 없습니다. (코드: {code})")
        elif mcap_tag and market_cap == 0.0:
            st.warning(f"시가총액 조회 실패: 파싱 실패 또는 시가총액이 0입니다. (원문: '{mcap_text}', 코드: {code})")
        else:
            st.warning(f"시가총액 조회 실패: 기타 원인 (코드: {code})")
            
        # 🚨 시가총액이 없으면 해당 함수 종료
        return data

            # 연간 매출액 + PSR 계산 (2025년 기준 최신 네이버 구조 100% 대응)
    try:
        # 방법 1: "연간" 탭 안에 있는 매출액 테이블 찾기 (가장 정확)
        annual_table = soup.find("table", summary="연간 실적")
        if annual_table:
            rows = annual_table.find_all("tr")
            for row in rows:
                th = row.find("th")
                if th and "매출액" in th.get_text():
                    tds = row.find_all("td")
                    if len(tds) > 0:
                        revenue_text = tds[0].get_text(strip=True)  # 첫 번째 연간 매출액
                        revenue_in_trillion = parse_money(revenue_text)
                        if revenue_in_trillion > 0 and data["market_cap"]:
                            data["psr"] = round(data["market_cap"] / revenue_in_trillion, 2)
                            break

        # 방법 2: 만약 연간 테이블이 없으면 기존 방식 시도 (백업)
        if not data["psr"]:
            revenue_row = soup.find("th", string=re.compile("매출액"))
            if revenue_row:
                parent_tr = revenue_row.find_parent("tr")
                if parent_tr:
                    revenue_text = parent_tr.find_all("td")[0].get_text(strip=True)
                    revenue_in_trillion = parse_money(revenue_text)
                    if "억" in revenue_text:  # 억 단위면 조로 변환
                        revenue_in_trillion = revenue_in_trillion / 10000
                    if revenue_in_trillion > 0 and data["market_cap"]:
                        data["psr"] = round(data["market_cap"] / revenue_in_trillion, 2)

    except Exception as e:
        # 디버깅용 (필요 없으면 지워도 됨)
        pass
    # 🚨 4.2 연간 총 매출액 (재무정보 탭에서 가져오기) 로직 삭제
    # 🚨 4.3 PSR 계산 로직 삭제
    
    return data

# =========================================================================
# 💡 Plotly 시각화 함수 (30일 예측 차트)
# - 내부적으로 'Close'를 사용하지만, 사용자 표시에는 '종가'를 사용합니다.
# =========================================================================
def visualize_prediction(df_actual, df_prediction, symbol):
    """실제 주가와 30일 예측 추이를 Plotly로 시각화합니다."""
    
    # Plotly 시각화를 위해 'Close' 컬럼명을 '종가'로 변경하여 사용
    df_actual_plot = df_actual.rename(columns={'Close': '종가'})
    df_prediction_plot = df_prediction.rename(columns={'Close': '종가'})
    
    # 1. 실제 주가 데이터
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_actual_plot.index, 
        y=df_actual_plot['종가'], 
        name='실제 주가', 
        line=dict(color='#1f77b4', width=3) # 친구 코드의 색상 및 두께 적용
    ))

    # 2. 예측 추이 데이터 (점선)
    # 예측 시작점(실제 마지막 날)과 예측 첫날을 연결
    last_actual_point = pd.DataFrame(
        {'종가': df_actual_plot['종가'].iloc[-1]}, 
        index=[df_actual_plot.index[-1]]
    )
    combined_df = pd.concat([last_actual_point, df_prediction_plot])
    
    fig.add_trace(go.Scatter(
        x=combined_df.index,
        y=combined_df['종가'],
        name='30일 예측 추이',
        line=dict(dash='dot', color='red', width=3)
    ))

    # 3. 30일 후 최종 예측 가격 (마커)
    final_price = df_prediction_plot['종가'].iloc[-1]
    final_prediction_date = df_prediction_plot.index[-1]
    
    fig.add_trace(go.Scatter(
        x=[final_prediction_date],
        y=[final_price],
        mode='markers+text',
        name='최종 예측 가격',
        text=[f"{final_price:,.0f}원"],
        textposition='top center',
        marker=dict(size=14, color='red', symbol='star') # 친구 코드의 마커 스타일 적용
    ))

    # 레이아웃 설정
    fig.update_layout(
        title=f"<b>{symbol}</b> 주가 예측",
        yaxis_title="가격 (KRW)",
        xaxis_title="날짜",
        height=550, # 친구 코드의 높이 적용
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        template="plotly_white" # 친구 코드의 템플릿 적용
    )
    # 🚨 use_container_width=True -> width='stretch'로 변경
    st.plotly_chart(fig, width='stretch') # 반응형 설정


# =========================================================================
# 💡 인기 검색 종목 데이터 및 함수 (yfinance 기반)
# =========================================================================
def get_top_stocks():
    """인기 종목의 실시간 주가와 등락률을 yfinance로 가져옵니다."""
    TOP_TICKERS = {
        "005930.KS": "삼성전자",
        "373220.KS": "LG에너지솔루션",
        "000660.KS": "SK하이닉스",
        "005490.KS": "POSCO홀딩스",
        "035420.KS": "네이버",
    }
    top_stocks_list = []
    
    for ticker, name in TOP_TICKERS.items():
        try:
            stock_info = yf.Ticker(ticker).history(period="2d")
            
            current_price = stock_info['Close'].iloc[-1] if not stock_info.empty else 0
            if len(stock_info) >= 2:
                previous_close = stock_info['Close'].iloc[-2]
                change_pct = ((current_price - previous_close) / previous_close) * 100
            else:
                change_pct = 0.0

            top_stocks_list.append({
                "name": name,
                "ticker": ticker,
                "price": current_price,
                "change_pct": change_pct,
            })
        except Exception:
            # 데이터 로드 실패 시 0으로 설정
            top_stocks_list.append({"name": name, "ticker": ticker, "price": 0, "change_pct": 0.0})
            
    return top_stocks_list

def select_stock(name, ticker):
    """인기 종목 클릭 시 세션 상태를 업데이트하고 초기화합니다."""
    # 종목명과 티커를 함께 저장하여 검색 기능을 강화
    st.session_state.input_temp = f"{name} [{ticker}]"
    st.session_state.company_name = name 
    
    # 새 검색 시 예측 관련 세션 상태 초기화
    for k in ['df', 'symbol', 'model_trained', 'pred_df', 'final_price', 'interpretation']:
        if k in st.session_state:
             st.session_state[k] = pd.DataFrame() if k in ['df','pred_df'] else False if k=='model_trained' else None


# =========================================================================
# 💡 세션 초기화 및 입력 처리
# =========================================================================

# 세션 상태에 필요한 모든 키 초기화
keys = ['company_name','df','symbol','model_trained','time_steps','input_temp',
        'pred_df','final_price','interpretation','model_symbol','model_time_steps']
for k in keys:
    if k not in st.session_state:
        st.session_state[k] = "" if k in ['company_name','input_temp','interpretation'] else \
                             pd.DataFrame() if k in ['df','pred_df'] else \
                             False if k=='model_trained' else None

def submit():
    """검색창 입력 시 실행되는 함수 (Enter 키 또는 클릭)"""
    txt = st.session_state.input_temp.strip()
    # 입력된 값에서 티커가 포함되어 있을 경우 종목명만 추출
    name = txt.split('[')[0].strip() if '[' in txt else txt
    
    if name and name != st.session_state.company_name:
        st.session_state.company_name = name
        # 상태 초기화
        for k in ['df','symbol','model_trained','pred_df','final_price','interpretation']:
             st.session_state[k] = pd.DataFrame() if k in ['df','pred_df'] else False if k=='model_trained' else None


# -------------------------------------------------------------------------
# [UI] 2개의 컬럼으로 분할: 인기 종목 (1) | 검색 + 결과 (2)
# -------------------------------------------------------------------------
top_stocks = get_top_stocks()
col_top, col_main = st.columns([1, 2])

# 1. 인기 검색 종목 순위표 (col_top)
with col_top:
    st.subheader("실시간 인기 종목")
    st.caption("클릭하시면 종목이 검색됩니다.")
    
    for i, stock in enumerate(top_stocks):
        if stock['price'] > 0:
            price_display = f"{stock['price']:,.0f}원"
            change_pct = stock['change_pct']
            
            # 친구 코드의 스타일 적용
            trend_text = "상승" if change_pct > 0 else "하락" if change_pct < 0 else "보합"
            label = f"**{i+1}. {stock['name']}**\n{price_display} | {trend_text} {abs(change_pct):.2f}%"

            st.button(
                label,
                key=f"stock_{i}",
                on_click=select_stock,
                args=(stock['name'], stock['ticker']),
                width='stretch' # 🚨 use_container_width=True -> width='stretch'로 변경
            )
        else:
            st.caption(f"**{i+1}. {stock['name']}** (데이터 없음)")

# 2. 검색창 및 결과 표시 (col_main)
with col_main:
    st.subheader("종목 검색")
    st.text_input(
        "주식 이름 입력 → **Enter**",
        key="input_temp",
        on_change=submit,
        placeholder="예: 셀트리온, 풍산, 카카오",
        label_visibility="collapsed"
    )

# =========================================================================
# 💡 데이터 로딩 및 결과 표시 로직
# =========================================================================

# 데이터 로딩
if st.session_state.company_name and st.session_state.df.empty and HAS_MODEL_FILES:
    with st.spinner(f"'{st.session_state.company_name}' 데이터 로딩 중..."):
        try:
            # data_loader.py의 load_stock_data 함수 호출
            df, symbol = load_stock_data(st.session_state.company_name)
            
            # 데이터 유효성 검사 (최소 60일 필요)
            if df.empty or len(df) < 60:
                st.error("데이터 부족 또는 종목을 찾을 수 없습니다. 다른 종목을 검색해 주세요.")
                st.session_state.company_name = ""
                # 🚨 수정: st.session_state.input_temp = "" 제거
            else:
                st.session_state.df = df
                st.session_state.symbol = symbol
        except Exception as e:
            st.error(f"데이터 로딩 중 오류 발생: {e}")
            st.session_state.company_name = ""
            # 🚨 수정: st.session_state.input_temp = "" 제거

# UI (주가 추이 및 예측 결과 표시)
if not st.session_state.df.empty:
    df = st.session_state.df
    symbol = st.session_state.symbol
    company = st.session_state.company_name # company 변수가 여기서 정의됨!

        # =========================================================================
    # 완전히 새로 짠 레이아웃 (보기 좋고, 글자 크고, 그래프 큼!)
    # =========================================================================

    # 1. 종목명 크게 상단에 표시
    st.markdown(f"# {company} ({symbol})")
    
    # 2. 3단 레이아웃: 왼쪽(지표), 오른쪽(차트)
    left_col, right_col = st.columns([0.7,2.2])

    with left_col:
        st.markdown("<h3 style='color:#1E90FF; font-weight:bold;'>기업 가치 지표</h3>", unsafe_allow_html=True)
        try:
            code = symbol.split(".")[0]
            fund = get_korean_fundamentals(code)
            def fmt(v, unit=""):
                return f"{v:,.2f}{unit}" if v is not None else "—"

            # 큰 메트릭으로 보기 좋게!
            c1, c2 = st.columns(2)
            c3, c4 = st.columns(2)
            c5, c6 = st.columns(2)

            with c1: st.metric("PER", fmt(fund.get("per"), "배"))
            with c2: st.metric("PBR", fmt(fund.get("pbr"), "배"))
            with c3: st.metric("PSR", fmt(fund.get("psr"), "배"))
            with c4: st.metric("외국인 비율", fmt(fund.get("foreign_ownership"), "%"))
            with c5: st.metric("배당수익률", fmt(fund.get("dividend_yield"), "%"))
            with c6: st.metric("시가총액", fmt(fund.get("market_cap"), "조"))

        except: pass

        st.markdown("<h3 style='color:#1E90FF; font-weight:bold; text-shadow: 1px 1px 3px rgba(0,0,0,0.2);'>애널리스트 컨센서스</h3>", unsafe_allow_html=True)

        try:
            info = yf.Ticker(f"{code}.KS").info

            mean = info.get("targetMeanPrice")
            high = info.get("targetHighPrice")
            low = info.get("targetLowPrice")
            analysts = info.get("numberOfAnalystOpinions")
            rating = info.get("recommendationKey", "").upper()
            rating_kr = {
                "BUY": "매수", "STRONG_BUY": "강력매수", 
                "HOLD": "중립", "SELL": "매도", "UNDERPERFORM": "매도"
            }.get(rating, "데이터 없음")

            # 색상 설정 (이모지 없이도 확 띄게!)
            if rating_kr in ["매수", "강력매수"]:
                color = "#00E676"   # 강한 초록
                badge = "강력 매수 추천"
            elif rating_kr == "매도":
                color = "#FF3333"   # 강한 빨강
                badge = "매도 의견 우세"
            else:
                color = "#FFB300"   # 진한 주황
                badge = "중립 의견"

            st.metric("평균 목표가", f"{mean:,.0f}원" if mean else "N/A")
            st.metric("목표가 범위", f"{low:,.0f} ~ {high:,.0f}원" if high and low else "N/A")
            st.metric("애널리스트 수", f"{analysts}개사" if analysts else "N/A")

            # 완전 눈에 띄는 컨센서스 박스 (이모지 없이도 미쳤음!)
            st.markdown(f"""
            <div style='text-align: center; padding: 20px; background: linear-gradient(135deg, #0f0f0f, #1a1a1a); 
                        border-radius: 16px; border: 3px solid {color}; box-shadow: 0 8px 20px rgba(0,0,0,0.5);'>
                <h2 style='margin:0; color:{color}; font-size:2.2em; font-weight:900; text-shadow: 2px 2px 8px rgba(0,0,0,0.7);'>
                    {rating_kr}
                </h2>
                <p style='margin:8px 0 0; color:#eee; font-size:1.1em; font-weight:bold;'>
                    {badge} • {analysts or 0}개 증권사
                </p>
            </div>
            """, unsafe_allow_html=True)

        except Exception as e:
            st.info("애널리스트 컨센서스 로드 중...")

    with left_col:
        st.markdown("<h3 style='color:#1E90FF; font-weight:bold;'>딥러닝 예측 설정</h3>", unsafe_allow_html=True)
        time_steps = st.selectbox("Time Steps", [30, 60, 90], index=1, key="ts_select")
        st.session_state.time_steps = time_steps

        if st.button("모델 재학습 (기존 삭제)", type="secondary", use_container_width=True):
            if os.path.exists(MODEL_DIR):
                shutil.rmtree(MODEL_DIR)
                os.makedirs(MODEL_DIR, exist_ok=True)
            st.session_state.model_trained = False
            st.success("기존 모델 삭제 완료")
            st.rerun()

        if HAS_MODEL_FILES:
            if st.button("LSTM 학습 및 30일 예측 시작", type="primary", use_container_width=True):
                safe_symbol = symbol.replace(".", "_")
                model_path = os.path.join(MODEL_DIR, f"model_{safe_symbol}_{time_steps}.keras")
                scaler_path = os.path.join(MODEL_DIR, f"scaler_{safe_symbol}_{time_steps}.pkl")

                if not (os.path.exists(model_path) and os.path.exists(scaler_path)):
                    with st.spinner("모델 학습 중..."):
                        try:
                            train_lstm_model(df, symbol, time_steps)
                        except Exception as e:
                            st.error(f"학습 실패: {e}")

                with st.spinner("30일 예측 중..."):
                    try:
                        result = predict_next_month(df, symbol, time_steps, company)
                        if result and len(result) == 3:
                            pred_df, final_price, interpretation = result
                            if pred_df is not None:
                                st.session_state.pred_df = pred_df
                                st.session_state.final_price = final_price
                                st.session_state.interpretation = interpretation
                                st.session_state.model_trained = True
                                st.session_state.model_symbol = symbol
                                st.session_state.model_time_steps = time_steps
                                st.success("예측 완료!")
                                st.rerun()
                    except Exception as e:
                        st.error(f"예측 오류: {e}")
        else:
            st.error("모델 파일 없음")

    with right_col:
        st.markdown("### 실시간 주가 추이")
        st.line_chart(df['Close'], height=400, use_container_width=True)

        # 예측 결과 있으면 크게 표시
        if (st.session_state.get('model_trained') and 
            not st.session_state.get('pred_df', pd.DataFrame()).empty and
            st.session_state.get('model_symbol') == symbol and
            st.session_state.get('model_time_steps') == time_steps):

            pred_df = st.session_state.pred_df
            final_price = st.session_state.final_price
            interpretation = st.session_state.interpretation
            current_price = df['Close'].iloc[-1]
            change_pct = ((final_price - current_price) / current_price) * 100

            st.markdown("### 30일 후 예측 결과")
            m1, m2 = st.columns(2)
            with m1:
                st.metric("현재 가격", f"{current_price:,.0f}원")
            with m2:
                st.metric("30일 후 예측", f"{final_price:,.0f}원", f"{change_pct:+.2f}%")

            visualize_prediction(df, pred_df, symbol)

            st.markdown("### AI 분석 리포트")
            st.info(interpretation)


    # =========================================================================
    # 🚨 [수정된 위치] Investing.com 뉴스 제목 크롤링 및 표시 🚨
    #    한국어 쿼리(company)를 그대로 전달합니다.
    # =========================================================================
    english_query_long = get_english_name(symbol) # 예: 'sk hynix'
    english_query_short = english_query_long.split()[0] if english_query_long else '' # 예: 'sk'
    # 2. 필터링 키워드 리스트 생성 (모든 경우의 수 포함)
    search_keywords = [company.lower()] # 예: 'sk하이닉스' (한글)
    if english_query_long and english_query_long not in search_keywords:
        search_keywords.append(english_query_long)
    if english_query_short and english_query_short not in search_keywords:
        search_keywords.append(english_query_short)
    
    filter_query = ' '.join(search_keywords)
    st.markdown("---") 
    st.markdown("### 📰 Investing.com 주식 시장 뉴스 (크롤링)")
    # 🚨 한국어 쿼리 그대로 사용 🚨
    st.caption(f"검색 키워드: **{filter_query.upper()}**에 대한 주식 시장 뉴스") 

    try:
        # 🚨 company (한국어)를 그대로 query로 전달 🚨
        news_results = scrape_investing_news_titles_selenium(filter_query, max_articles=10)
        
        if news_results:
            st.markdown(f"총 {len(news_results)}개의 관련 뉴스가 크롤링되었습니다.")
            
            for item in news_results:
                st.markdown(f"*{item['title']}* ([링크]({item['link']}))")
        else:
            st.info(f"'{company}' 키워드와 관련된 뉴스를 찾지 못했습니다. (Investing.com 크롤링)")

    except Exception as e:
        st.error(f"뉴스 크롤링 표시 중 오류 발생: {e}")
        
# 🚨 if not st.session_state.df.empty: 블록 끝