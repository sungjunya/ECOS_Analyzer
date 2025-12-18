# app.py (MAPE 계산 수정 완료)
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
from sklearn.metrics import mean_squared_error, mean_absolute_error 
import joblib 

try:
    from dotenv import load_dotenv
    load_dotenv()
    print("SUCCESS: .env 파일 로드 완료.")
except ImportError:
    print("WARNING: python-dotenv 라이브러리가 설치되지 않았습니다. pip install python-dotenv 로 설치해 주세요.")
    
try:
    from lstm_model import train_lstm_model
    from predict import predict_next_month
    from data_loader import load_stock_data, get_english_name
    from news_scraper import scrape_investing_news_titles_selenium 
    HAS_MODEL_FILES = True
except ImportError as e:
    st.warning(f"경고: 필요한 모듈 중 일부를 찾을 수 없습니다. ({e})")
    st.warning("모델 학습 및 예측, 뉴스 기능이 비활성화됩니다. 파일을 확인해 주세요.")
    HAS_MODEL_FILES = False

# 🚨 [수정] RMSE, MAE 계산 함수 이름 변경 및 MAPE 로직 분리
def calculate_scaled_metrics(y_true_scaled, y_pred_scaled):
    """정규화된 값을 기반으로 RMSE와 MAE를 계산합니다."""
    y_true_scaled = np.array(y_true_scaled).flatten()
    y_pred_scaled = np.array(y_pred_scaled).flatten()

    rmse = np.sqrt(mean_squared_error(y_true_scaled, y_pred_scaled))
    mae = mean_absolute_error(y_true_scaled, y_pred_scaled)

    return rmse, mae

# 🚨 [추가] MAPE는 실제 값(역변환)을 기반으로 계산하는 함수
def calculate_mape_from_scaled(y_true_scaled, y_pred_scaled, scaler_path, features):
    """Scaled 값을 받아 스케일러를 로드하여 역변환 후 MAPE를 계산합니다."""
    try:
        scaler = joblib.load(scaler_path)
        
        # 실제 주가 역변환
        dummy_true = np.zeros((len(y_true_scaled), len(features)))
        dummy_true[:, 0] = y_true_scaled.flatten()
        y_true_inverse = scaler.inverse_transform(dummy_true)[:, 0]

        # 예측 주가 역변환
        dummy_pred = np.zeros((len(y_pred_scaled), len(features)))
        dummy_pred[:, 0] = y_pred_scaled.flatten()
        y_pred_inverse = scaler.inverse_transform(dummy_pred)[:, 0]
        
        # MAPE 계산
        epsilon = 1e-10
        mape = np.mean(np.abs((y_true_inverse - y_pred_inverse) / (y_true_inverse + epsilon))) * 100
        
        return mape
        
    except Exception as e:
        # 스케일러 로드 실패 시 None 반환
        return None

st.set_page_config(page_title="LSTM 예측기", layout="wide")
st.markdown("""
<h1 style='text-align: center; color: #1E90FF; font-weight: bold;'>주식 이름으로 LSTM 예측</h1>
<p style='text-align: center; color: #666;'>Volume 포함 다변량 LSTM + 30일 예측 + AI 리포트</p>
""", unsafe_allow_html=True)

MODEL_DIR = "models"
os.makedirs(MODEL_DIR, exist_ok=True)

@st.cache_data(show_spinner=False, ttl=3600)
def get_korean_fundamentals(code: str) -> dict:
    data = {"per": None, "pbr": None, "psr":None, "foreign_ownership": None, "dividend_yield": None, "market_cap": None}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9"
    }
    
    def parse_money(text: str) -> float:
        text = re.sub(r"[,\s]", "", text)
        val = 0.0

        trillion_match = re.search(r"([\d\.]+)조", text)
        if trillion_match:
            val += float(trillion_match.group(1))
            text = re.sub(r"[\d\.]*조", "", text)
        
        billion_match = re.search(r"([\d\.]+)", text)
        if billion_match:
            billion_value = float(billion_match.group(1))
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

    for pattern in [
        r"외국인[^\d]*([\d,]+\.\d+)%",
        r"외국인\s*지분율[^\d]*([\d,]+\.\d+)%",
        r"외국인\s*[\[\(][^%\d]*([\d,]+\.\d+)%[\]\)]"
    ]:
        m = re.search(pattern, soup.get_text())
        if m:
            data["foreign_ownership"] = float(m.group(1).replace(",", ""))
            break

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

    market_cap = None
    
    mcap_tag = soup.find("em", id="_market_sum")
    mcap_text = ""
    if mcap_tag:
        mcap_text = mcap_tag.get_text(strip=True)
        market_cap = parse_money(mcap_text)

    if market_cap is not None and market_cap > 0:
        data["market_cap"] = round(market_cap, 2)
    else:
        if not mcap_tag:
            st.warning(f"시가총액 조회 실패: Naver 페이지에서 '_market_sum' 태그를 찾을 수 없습니다. (코드: {code})")
        elif mcap_tag and market_cap == 0.0:
            st.warning(f"시가총액 조회 실패: 파싱 실패 또는 시가총액이 0입니다. (원문: '{mcap_text}', 코드: {code})")
        else:
            st.warning(f"시가총액 조회 실패: 기타 원인 (코드: {code})")
            
        return data

    try:
        annual_table = soup.find("table", summary="연간 실적")
        if annual_table:
            rows = annual_table.find_all("tr")
            for row in rows:
                th = row.find("th")
                if th and "매출액" in th.get_text():
                    tds = row.find_all("td")
                    if len(tds) > 0:
                        revenue_text = tds[0].get_text(strip=True)
                        revenue_in_trillion = parse_money(revenue_text)
                        if revenue_in_trillion > 0 and data["market_cap"]:
                            data["psr"] = round(data["market_cap"] / revenue_in_trillion, 2)
                            break

        if not data["psr"]:
            revenue_row = soup.find("th", string=re.compile("매출액"))
            if revenue_row:
                parent_tr = revenue_row.find_parent("tr")
                if parent_tr:
                    revenue_text = parent_tr.find_all("td")[0].get_text(strip=True)
                    revenue_in_trillion = parse_money(revenue_text)
                    if "억" in revenue_text:
                        revenue_in_trillion = revenue_in_trillion / 10000
                    if revenue_in_trillion > 0 and data["market_cap"]:
                        data["psr"] = round(data["market_cap"] / revenue_in_trillion, 2)

    except Exception as e:
        pass
    
    return data

def visualize_prediction(df_actual, df_prediction, symbol):
    df_actual_plot = df_actual.rename(columns={'Close': '종가'})
    df_prediction_plot = df_prediction.rename(columns={'Close': '종가'})
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_actual_plot.index, 
        y=df_actual_plot['종가'], 
        name='실제 주가', 
        line=dict(color='#1f77b4', width=3)
    ))

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

    final_price = df_prediction_plot['종가'].iloc[-1]
    final_prediction_date = df_prediction_plot.index[-1]
    
    fig.add_trace(go.Scatter(
        x=[final_prediction_date],
        y=[final_price],
        mode='markers+text',
        name='최종 예측 가격',
        text=[f"{final_price:,.0f}원"],
        textposition='top center',
        marker=dict(size=14, color='red', symbol='star')
    ))

    fig.update_layout(
        title=f"<b>{symbol}</b> 주가 예측",
        yaxis_title="가격 (KRW)",
        xaxis_title="날짜",
        height=550,
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        template="plotly_white"
    )
    st.plotly_chart(fig, width='stretch')

def get_top_stocks():
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
            top_stocks_list.append({"name": name, "ticker": ticker, "price": 0, "change_pct": 0.0})
            
    return top_stocks_list

def select_stock(name, ticker):
    st.session_state.input_temp = f"{name} [{ticker}]"
    st.session_state.company_name = name 
    
    for k in ['df', 'symbol', 'model_trained', 'pred_df', 'final_price', 'interpretation', 'test_y_true', 'test_y_pred', 'test_dates']:
        if k in st.session_state:
             st.session_state[k] = pd.DataFrame() if k in ['df','pred_df'] else False if k=='model_trained' else None

keys = ['company_name','df','symbol','model_trained','time_steps','input_temp',
        'pred_df','final_price','interpretation','model_symbol','model_time_steps',
        'test_y_true', 'test_y_pred', 'test_dates']
for k in keys:
    if k not in st.session_state:
        st.session_state[k] = "" if k in ['company_name','input_temp','interpretation'] else \
                              pd.DataFrame() if k in ['df','pred_df'] else \
                              False if k=='model_trained' else None

def submit():
    txt = st.session_state.input_temp.strip()
    name = txt.split('[')[0].strip() if '[' in txt else txt
    
    if name and name != st.session_state.company_name:
        st.session_state.company_name = name
        for k in ['df','symbol','model_trained','pred_df','final_price','interpretation', 'test_y_true', 'test_y_pred','test_dates']:
             st.session_state[k] = pd.DataFrame() if k in ['df','pred_df'] else False if k=='model_trained' else None

top_stocks = get_top_stocks()
col_top, col_main = st.columns([1, 2])

with col_top:
    st.subheader("실시간 인기 종목")
    st.caption("클릭하시면 종목이 검색됩니다.")
    
    for i, stock in enumerate(top_stocks):
        if stock['price'] > 0:
            price_display = f"{stock['price']:,.0f}원"
            change_pct = stock['change_pct']
            
            trend_text = "상승" if change_pct > 0 else "하락" if change_pct < 0 else "보합"
            label = f"**{i+1}. {stock['name']}**\n{price_display} | {trend_text} {abs(change_pct):.2f}%"

            st.button(
                label,
                key=f"stock_{i}",
                on_click=select_stock,
                args=(stock['name'], stock['ticker']),
                width='stretch'
            )
        else:
            st.caption(f"**{i+1}. {stock['name']}** (데이터 없음)")

with col_main:
    st.subheader("종목 검색")
    st.text_input(
        "주식 이름 입력 → **Enter**",
        key="input_temp",
        on_change=submit,
        placeholder="예: 셀트리온, 풍산, 카카오",
        label_visibility="collapsed"
    )

if st.session_state.company_name and st.session_state.df.empty and HAS_MODEL_FILES:
    with st.spinner(f"'{st.session_state.company_name}' 데이터 로딩 중..."):
        try:
            df, symbol = load_stock_data(st.session_state.company_name)
            
            if df.empty or len(df) < 60:
                st.error("데이터 부족 또는 종목을 찾을 수 없습니다. 다른 종목을 검색해 주세요.")
                st.session_state.company_name = ""
            else:
                st.session_state.df = df
                st.session_state.symbol = symbol
        except Exception as e:
            st.error(f"데이터 로딩 중 오류 발생: {e}")
            st.session_state.company_name = ""

if not st.session_state.df.empty:
    df = st.session_state.df
    symbol = st.session_state.symbol
    company = st.session_state.company_name

    st.markdown(f"# {company} ({symbol})")
    
    left_col, right_col = st.columns([0.7,2.2])

    with left_col:
        st.markdown("<h3 style='color:#1E90FF; font-weight:bold;'>기업 가치 지표</h3>", unsafe_allow_html=True)
        try:
            code = symbol.split(".")[0]
            fund = get_korean_fundamentals(code)
            def fmt(v, unit=""):
                return f"{v:,.2f}{unit}" if v is not None else "—"

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

            if rating_kr in ["매수", "강력매수"]:
                color = "#00E676"
                badge = "강력 매수 추천"
            elif rating_kr == "매도":
                color = "#FF3333"
                badge = "매도 의견 우세"
            else:
                color = "#FFB300"
                badge = "중립 의견"

            st.metric("평균 목표가", f"{mean:,.0f}원" if mean else "N/A")
            st.metric("목표가 범위", f"{low:,.0f} ~ {high:,.0f}원" if high and low else "N/A")
            st.metric("애널리스트 수", f"{analysts}개사" if analysts else "N/A")

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
            st.session_state.test_y_true = None
            st.session_state.test_y_pred = None
            st.success("기존 모델 삭제 완료")
            st.rerun()

        if HAS_MODEL_FILES:
            safe_symbol = symbol.replace(".", "_")
            model_path = os.path.join(MODEL_DIR, f"model_{safe_symbol}_{time_steps}.keras")
            scaler_path = os.path.join(MODEL_DIR, f"scaler_{safe_symbol}_{time_steps}.pkl")
            current_model_exists = os.path.exists(model_path) and os.path.exists(scaler_path)
            if st.button("LSTM 학습 및 30일 예측 시작", type="primary", use_container_width=True):
                if not current_model_exists:
                    with st.spinner("모델 학습 중 (새로운 모델 생성)..."):
                        try:
                            # 🚨 train_lstm_model 호출 (학습 + test_y_true/pred/dates 저장)
                            test_y_true, test_y_pred = train_lstm_model(df, symbol, time_steps)
                            st.session_state.test_y_true = test_y_true
                            st.session_state.test_y_pred = test_y_pred
                            st.session_state.model_trained = True
                            st.session_state.model_symbol = symbol
                            st.session_state.model_time_steps = time_steps
                            st.success("모델 학습 완료!")
                        except Exception as e:
                            st.error(f"학습 실패: {e}")
                            st.session_state.model_trained = False

                if current_model_exists or st.session_state.get('model_trained'):
                    with st.spinner("30일 예측 중..."):
                        try:
                            result = predict_next_month(df, symbol, time_steps, company)
                            if result and len(result) == 3 and result[0] is not None:
                                pred_df, final_price, interpretation = result
                                st.session_state.pred_df = pred_df
                                st.session_state.final_price = final_price
                                st.session_state.interpretation = interpretation
                                st.session_state.model_trained = True 
                                st.session_state.model_symbol = symbol
                                st.session_state.model_time_steps = time_steps

                                st.success("예측 완료!")
                                st.rerun() # 예측 후 화면 갱신
                            else:
                                # predict_next_month에서 모델 파일이 없다고 판단하면 result[0]은 None이 됨.
                                st.error("예측 실패: 모델을 찾거나 예측 결과를 생성할 수 없습니다.")

                        except Exception as e:
                            st.error(f"예측 중 오류 발생: {e}")
                else:
                    st.error("학습 및 예측을 시작할 수 없습니다. 데이터가 충분한지 확인하거나 Time Steps을 조정하세요.")
        else:
            st.error("모델 파일 없음")

    with right_col:
        st.markdown("### 실시간 주가 추이")
        st.line_chart(df['Close'], height=400, use_container_width=True)

        if (st.session_state.get('model_trained') and 
            st.session_state.get('model_symbol') == symbol and
            st.session_state.get('model_time_steps') == time_steps):

            test_y_true = st.session_state.get('test_y_true')
            test_y_pred = st.session_state.get('test_y_pred')
            test_dates = st.session_state.get('test_dates')
            pred_df = st.session_state.get('pred_df', pd.DataFrame())

            if test_y_true is not None and test_y_pred is not None and len(test_y_true) > 0:
                
                # ----------------------------------------------------------------------------------
                # 🚨 [수정된 호출] RMSE, MAE 계산 (Scaled 값 그대로 사용)
                rmse_val, mae_val = calculate_scaled_metrics(test_y_true, test_y_pred)

                # 🚨 [추가된 호출] MAPE 계산 (역변환 후 사용)
                features = ['Close', 'Volume', 'SMA_5', 'SMA_20', 'RSI', 'MACD', 'Volume_SMA', 
                            'BB_Upper', 'BB_Lower', 'OBV', 'Stoch_K', 'Stoch_D', 'ROC']
                safe_symbol = symbol.replace(".", "_")
                scaler_path = os.path.join(MODEL_DIR, f"scaler_{safe_symbol}_{time_steps}.pkl")
                
                mape_val = calculate_mape_from_scaled(test_y_true, test_y_pred, scaler_path, features)
                
                # MAPE 계산에 성공했을 때만 출력
                if mape_val is not None:
                    st.markdown("---")
                    st.markdown("<h3 style='color:#FF4B4B; font-weight:bold;'>모델 백테스트 성능 지표</h3>", unsafe_allow_html=True)
                    
                    col_met1, col_met2, col_met3 = st.columns(3)
                    with col_met1:
                        st.metric("RMSE (Scaled)", f"{rmse_val:.5f}")
                    with col_met2:
                        st.metric("MAE (Scaled)", f"{mae_val:.5f}")
                    with col_met3:
                        st.metric("MAPE", f"{mape_val:,.2f}%") # 🚨 [수정] MAPE 값 출력
                
                    st.markdown("---")
                # ----------------------------------------------------------------------------------
                
                st.markdown("### 백테스트 예측 vs. 실제 주가 (테스트 세트)")

                # ----------------------------------------------------------------------------------
                # 그래프 출력을 위해 scaled 값을 실제 가격으로 역변환 (변동 없음)
                # ----------------------------------------------------------------------------------
                features = ['Close', 'Volume', 'SMA_5', 'SMA_20', 'RSI', 'MACD', 'Volume_SMA', 
                            'BB_Upper', 'BB_Lower', 'OBV', 'Stoch_K', 'Stoch_D', 'ROC']
                
                safe_symbol = symbol.replace(".", "_")
                scaler_path = os.path.join(MODEL_DIR, f"scaler_{safe_symbol}_{time_steps}.pkl")
                
                try:
                    scaler = joblib.load(scaler_path)
                    
                    # 1. 실제 주가 역변환
                    dummy_true = np.zeros((len(test_y_true), len(features)))
                    dummy_true[:, 0] = test_y_true.flatten()
                    y_test_true_inverse = scaler.inverse_transform(dummy_true)[:, 0]

                    # 2. 예측 주가 역변환
                    dummy_pred = np.zeros((len(test_y_pred), len(features)))
                    dummy_pred[:, 0] = test_y_pred.flatten()
                    y_test_pred_inverse = scaler.inverse_transform(dummy_pred)[:, 0]

                    # 그래프 데이터프레임 생성 (역변환된 값 사용)
                    df_test_plot = pd.DataFrame({
                        '실제 주가': y_test_true_inverse,
                        '예측 주가': y_test_pred_inverse
                    }, index=test_dates[:len(y_test_true_inverse)]) 

                    st.line_chart(df_test_plot, height=300, use_container_width=True)

                except Exception as e:
                    st.warning(f"백테스트 그래프 출력 오류: 스케일러 로드/역변환 실패. 재학습을 시도하세요. ({e})")
                    # 에러 발생 시 scaled 값이라도 그래프에 표시 (시각적 의미는 적음)
                    df_test_plot_fallback = pd.DataFrame({
                        '실제 주가': test_y_true,
                        '예측 주가': test_y_pred
                    }, index=test_dates[:len(test_y_true)])
                    st.line_chart(df_test_plot_fallback, height=300, use_container_width=True)
                # ----------------------------------------------------------------------------------

                st.markdown("---")

            if not pred_df.empty:
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

    english_query_long = get_english_name(symbol)
    english_query_short = english_query_long.split()[0] if english_query_long else ''
    search_keywords = [company.lower()]
    if english_query_long and english_query_long not in search_keywords:
        search_keywords.append(english_query_long)
    if english_query_short and english_query_short not in search_keywords:
        search_keywords.append(english_query_short)
    
    filter_query = ' '.join(search_keywords)
    st.markdown("---") 
    st.markdown("### 📰 Investing.com 주식 시장 뉴스 (크롤링)")
    st.caption(f"검색 키워드: **{filter_query.upper()}**에 대한 주식 시장 뉴스") 

    try:
        news_results = scrape_investing_news_titles_selenium(filter_query, max_articles=10)
        
        if news_results:
            st.markdown(f"총 {len(news_results)}개의 관련 뉴스가 크롤링되었습니다.")
            
            for item in news_results:
                st.markdown(f"*{item['title']}* ([링크]({item['link']}))")
        else:
            st.info(f"'{company}' 키워드와 관련된 뉴스를 찾지 못했습니다. (Investing.com 크롤링)")

    except Exception as e:
        st.error(f"뉴스 크롤링 표시 중 오류 발생: {e}")