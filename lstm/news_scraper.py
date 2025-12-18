# news_scraper.py

import streamlit as st
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import re
import numpy as np 
# 🚨 [추가] URL 인코딩을 위해 urllib.parse 임포트
from urllib.parse import quote 

# ⚠️ 크롤링 주의 사항: Selenium은 requests보다 느리지만, 403 에러 회피에 필수적입니다.
#    비상업적 학습 목적으로만 사용하고, 충분한 time.sleep을 유지해야 합니다.

@st.cache_data(ttl=600, show_spinner=False)
def scrape_investing_news_titles_selenium(query: str, max_articles: int = 10) -> list:
    """
    한국 Investing.com의 종목 검색 뉴스 결과 페이지에서 크롤링합니다.
    (예: https://kr.investing.com/search/?q=%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90&tab=news)
    """
    
    # 🚨 [수정] 검색 결과 페이지 URL 사용
    encoded_query = quote(query) # 한국어 쿼리 인코딩
    base_url = f"https://kr.investing.com/search/?q={encoded_query}&tab=news" 
    target_url = base_url

    news_list = []
    
    # 🚨 [삭제] 검색 결과 페이지에서는 별도의 키워드 필터링은 하지 않습니다.
    #    (검색 결과 자체가 이미 필터링된 것이므로)
    
    # --- Selenium 설정 ---
    options = Options()
    options.add_argument("--headless")              
    options.add_argument("--no-sandbox")            
    options.add_argument("--disable-dev-shm-usage") 
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        with st.spinner(f"[{query.upper()}] 뉴스 검색 페이지를 브라우저로 로딩 중 (5초 대기)..."):
            driver.get(target_url) 
            # 페이지 로딩 및 동적 콘텐츠 생성을 위해 충분히 기다립니다.
            time.sleep(5) 
            soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # --- 데이터 추출 로직 ---
        # 🚨 [수정] 검색 결과 페이지의 뉴스 제목/링크 CSS Selector
        # Investing.com 검색 결과 뉴스 탭의 링크 컨테이너
        news_containers = soup.select('div.search-result-items article a')
        
        for container in news_containers:
            # 제목은 a 태그의 텍스트
            title = container.get_text(strip=True)
            link = container.get('href')
            
            # 검색 결과 페이지이므로 별도 키워드 필터링 로직은 삭제 (성능 개선)
            
            if link and title:
                # kr.investing.com 도메인을 사용하여 링크 구성
                full_link = f"https://kr.investing.com{link}" if link.startswith('/') else link
                news_list.append({"title": title, "link": full_link})
            
            if len(news_list) >= max_articles:
                break
                
        driver.quit()
        return news_list

    except Exception as e:
        if driver:
             try: driver.quit()
             except: pass
        st.error(f"뉴스 크롤링 (Selenium) 실패: {e}")
        st.error("Selenium 설정 및 드라이버 오류 또는 웹사이트 구조 변경 문제일 수 있습니다.")
        return []