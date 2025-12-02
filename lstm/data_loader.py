# data_loader.py (get_english_name 추가 버전)

import pandas as pd
import requests
import time
from io import StringIO
from bs4 import BeautifulSoup
import streamlit as st
from datetime import datetime, timedelta
import re
import certifi
import numpy as np
import yfinance as yf # 🚨 yfinance 임포트 추가 (상단에 이미 있었으나 재확인)


def search_stock_code(query):
    query = query.strip()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    url = f"https://search.naver.com/search.naver?where=stock&query={query}"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            if 'finance.naver.com/item' in a['href']:
                code = a['href'].split('code=')[1].split('&')[0]
                if len(code) == 6 and code.isdigit():
                    symbol = f"{code}.KS"
                    st.success(f"검색 성공: '{query}' → {symbol}")
                    return symbol
        st.warning(f"종목 없음: {query}")
        return None
    except Exception as e:
        st.error(f"검색 오류: {e}")
        return None


def parse_money(text: str) -> float:
    """모든 케이스 완벽 처리: '595조 5,156억', '784억', '3,578조' 등"""
    if not text or not text.strip():
        return 0.0
    text = re.sub(r"[,\s]", "", text.strip())
    val = 0.0

    # 1. 조 단위
    if "조" in text:
        match = re.search(r"([\d\.]+)조", text)
        if match:
            val += float(match.group(1))
        text = re.sub(r"[\d\.]*조", "", text)

    # 2. 억 단위 (조가 없으면 남은 숫자는 무조건 억으로 간주)
    match = re.search(r"([\d\.]+)", text)
    if match:
        billions = float(match.group(1))
        val += billions / 10_000  # 억 → 조

    return round(val, 4)

@st.cache_data(show_spinner=False, ttl=3600)
def get_korean_fundamentals(code: str) -> dict:
    data = {
        "per": None, "pbr": None, "psr": None,
        "foreign_ownership": None, "dividend_yield": None, "market_cap": None
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9"
    }

    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        resp = requests.get(url, headers=headers, timeout=20, verify=certifi.where())
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
    except Exception as e:
        st.warning(f"접속 실패: {e}")
        return data

    # 1. PER, PBR, PSR → 네이버가 이미 계산해준 값 그대로 가져오기 (100% 정확)
    for tid, key in [("_per", "per"), ("_pbr", "pbr"), ("_psr", "psr")]:
        tag = soup.find("em", id=tid)
        if tag:
            try:
                val = tag.get_text(strip=True).replace(",", "")
                data[key] = round(float(val), 2)
            except:
                pass

    # 2. 시가총액
    mcap_tag = soup.find("em", id="_market_sum")
    if mcap_tag:
        text = mcap_tag.get_text(strip=True)
        text = re.sub(r"[,\s]", "", text)
        val = 0.0
        if "조" in text:
            t = re.search(r"([\d\.]+)조", text)
            if t: val += float(t.group(1))
            text = re.sub(r"[\d\.]*조", "", text)
        if text:
            b = re.search(r"([\d\.]+)", text)
            if b: val += float(b.group(1)) / 10_000
        if val > 0:
            data["market_cap"] = round(val, 2)

    # 3. 외국인 지분율 & 배당수익률
    full_text = soup.get_text()
    for pat in [r"외국인[^\d]*([\d,]+\.\d+)%", r"외국인\s*지분율[^\d]*([\d,]+\.\d+)%"]:
        m = re.search(pat, full_text)
        if m:
            data["foreign_ownership"] = float(m.group(1).replace(",", ""))
            break

    for pat in [r"배당수익률[^\d]*([\d,]+\.\d+)%", r"배당수익률\s*\[?[^\d]*([\d,]+\.\d+)%"]:
        m = re.search(pat, full_text)
        if m:
            data["dividend_yield"] = float(m.group(1).replace(",", ""))
            break

    return data


# 🚨 get_english_name 함수 추가 🚨
@st.cache_data(ttl=3600)
def get_english_name(symbol: str) -> str:
    """
    종목 티커를 사용하여 Yahoo Finance에서 회사 영문 이름을 가져와 필터링용 소문자로 반환합니다.
    """
    if not symbol:
        return ""
    
    try:
        ticker = yf.Ticker(symbol)
        # longName 또는 shortName을 사용하여 영문명을 가져옵니다.
        long_name = ticker.info.get('longName', ticker.info.get('shortName', ''))
        
        if long_name:
            # 특수 문자 제거 및 공백 기준으로 첫 2~3 단어만 사용
            cleaned_name = re.sub(r'[^\w\s]', '', long_name)
            # 'SK Hynix Inc' -> 'sk hynix' (소문자, 2단어만 사용)
            return ' '.join(cleaned_name.split()[:3]).lower()
            
        return ""
    except Exception:
        # 야후 파이낸스 데이터 로드 실패 시, 기본 영문 티커 반환
        return symbol.split(".")[0].lower()


@st.cache_data
def load_stock_data(input_text):
    symbol = search_stock_code(input_text)
    if not symbol:
        return pd.DataFrame(), None

    code = symbol.replace('.KS', '')
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
    all_data = []
    max_pages = 30

    with st.spinner(f"[{symbol}] 데이터 수집 중..."):
        session = requests.Session()
        for page in range(1, max_pages + 1):
            url = f"https://finance.naver.com/item/sise_day.naver?code={code}&page={page}"
            try:
                resp = session.get(url, headers=headers, timeout=10)
                df_page = pd.read_html(StringIO(resp.text), flavor='lxml')[0].dropna()
                if len(df_page) < 7:
                    break
                all_data.append(df_page)
                time.sleep(0.05)
            except:
                break

    if not all_data:
        return pd.DataFrame(), symbol

    df = pd.concat(all_data, ignore_index=True)
    df['날짜'] = pd.to_datetime(df['날짜'], format='%Y.%m.%d', errors='coerce')
    df = df.dropna(subset=['날짜'])

    for kr, en in zip(['종가', '시가', '고가', '저가', '거래량'], ['Close', 'Open', 'High', 'Low', 'Volume']):
        df[en] = pd.to_numeric(df[kr].astype(str).str.replace(',', ''), errors='coerce')

    df = df.set_index('날짜').sort_index()[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()

    if len(df) < 90:
        st.error(f"데이터 부족: {len(df)}일")
        return pd.DataFrame(), symbol

    st.success(f"로드 완료: {len(df)}일")
    return df, symbol