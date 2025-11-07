import pandas as pd
import requests
import time
from io import StringIO
from bs4 import BeautifulSoup
import streamlit as st
from datetime import datetime, timedelta

def search_stock_code(query):
    """
    네이버 검색을 통해 종목 이름(한글) 또는 종목 코드(숫자)로 
    6자리 종목 코드와 .KS(코스피/코스닥) 형태의 심볼을 추출합니다.
    """
    query = query.strip()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    # 네이버 주식 검색 URL
    url = f"https://search.naver.com/search.naver?where=stock&query={query}"
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 주식 상세 페이지 링크에서 종목 코드를 추출
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'finance.naver.com/item' in href:
                code = href.split('code=')[1].split('&')[0]
                
                # 6자리 숫자인지 확인
                if code.isdigit() and len(code) == 6:
                    # 한국 주식 (KS) 심볼 형식으로 반환
                    full_symbol = f"{code}.KS" 
                    st.success(f"검색 성공: '{query}' → {full_symbol}")
                    return full_symbol
        
        st.warning(f"검색 실패: '{query}'에 해당하는 6자리 종목 코드를 찾을 수 없습니다.")
        return None
    except Exception as e:
        st.error(f"주식 코드 검색 중 에러 발생: {e}")
        return None

@st.cache_data
def load_stock_data(input_text):
    """
    주식 이름이나 코드를 입력받아 네이버 금융에서 
    시가, 고가, 저가, 종가, 거래량 데이터를 로드하여 DataFrame으로 반환합니다.
    """
    symbol = search_stock_code(input_text)
    if not symbol:
        return pd.DataFrame(), None

    code = symbol.replace('.KS', '')
    headers = {'User-Agent': 'Mozilla/5.0'}
    all_data = []
    page = 1
    max_pages = 30  # 300일 이상의 데이터를 확보하기 위해 최대 30페이지 (약 420일)

    with st.spinner(f"[{symbol}] 네이버 금융에서 데이터 수집 중..."):
        session = requests.Session()
        while page <= max_pages:
            url = f"https://finance.naver.com/item/sise_day.naver?code={code}&page={page}"
            try:
                # 1. 크롤링 요청
                resp = session.get(url, headers=headers, timeout=10)
                
                # 2. HTML 테이블 파싱
                tables = pd.read_html(StringIO(resp.text), flavor='lxml')[0]
                df_page = tables.dropna()
                
                # 3. 데이터 종료 조건
                if df_page.empty or len(df_page) < 7:
                    break
                
                all_data.append(df_page)
                page += 1
                time.sleep(0.05) # 서버 부하를 줄이기 위한 지연
                
            except Exception as e:
                st.warning(f"데이터 수집 중 페이지 {page} 오류 발생: {e}")
                break

    if not all_data:
        st.error("데이터 로딩 실패: 수집된 데이터가 없습니다.")
        return pd.DataFrame(), symbol

    # 4. 데이터 통합 및 정리
    df = pd.concat(all_data, ignore_index=True)
    df['날짜'] = pd.to_datetime(df['날짜'], format='%Y.%m.%d', errors='coerce')
    df = df.dropna(subset=['날짜'])

    # 5. 숫자형 컬럼 변환 및 이름 변경
    for col_kr, col_en in zip(
        ['종가', '시가', '고가', '저가', '거래량'], 
        ['Close', 'Open', 'High', 'Low', 'Volume']
    ):
        # 쉼표(,) 제거 후 숫자형으로 변환
        df[col_en] = pd.to_numeric(df[col_kr].astype(str).str.replace(',', ''), errors='coerce')

    # 6. 최종 DataFrame 정리
    df = df[['날짜', 'Open', 'High', 'Low', 'Close', 'Volume']].dropna()
    df = df.set_index('날짜').sort_index()

    # 7. LSTM 모델 학습을 위한 최소 데이터 검증 (최소 90일 권장)
    if len(df) < 90:
        st.error(f"데이터 부족: 총 {len(df)}일 데이터 로드. (최소 90일 이상 필요)")
        return pd.DataFrame(), symbol

    st.success(f"성공: [{symbol}] 총 {len(df)}일 데이터 로드 완료! (시가, 고가, 저가, 종가, 거래량)")
    return df, symbol