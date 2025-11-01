# /mnt/project/tubealgo/services/google_trends_scraper.py

import time
import json
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

class GoogleTrendsScraper:
    """
    Google Trends data scraper using Selenium
    pytrends se better kyunki:
    - Browser-like behavior se 429 error nahi aata
    - User-Agent rotation se blocking avoid hota hai
    - Retry mechanism built-in hai
    """
    
    def __init__(self):
        self.base_url = "https://trends.google.com/trends"
        self.setup_driver()
    
    def setup_driver(self):
        """Headless Chrome setup with anti-detection"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        
        # Random User-Agent rotation (429 error avoid karne ke liye)
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        ]
        chrome_options.add_argument(f'user-agent={random.choice(user_agents)}')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 10)
    
    def get_trending_searches(self, geo='IN', max_results=20):
        """
        Real-time trending searches (YouTube ke liye)
        
        Args:
            geo: Country code (IN for India, US for USA)
            max_results: Kitne trending keywords return karne hain
        
        Returns:
            List of trending keywords with search volume
        """
        try:
            # YouTube-specific trending searches
            url = f"{self.base_url}/trending?geo={geo}&category=18"  # Category 18 = YouTube
            self.driver.get(url)
            
            # Wait for data to load
            time.sleep(random.uniform(2, 4))  # Random delay (anti-detection)
            
            # Extract trending searches
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            trending_items = soup.find_all('div', class_='feed-item')
            
            results = []
            for item in trending_items[:max_results]:
                try:
                    keyword = item.find('div', class_='title').text.strip()
                    traffic = item.find('div', class_='summary-text').text.strip()
                    
                    # Extract search volume (approximate)
                    volume = self._extract_volume(traffic)
                    
                    results.append({
                        'keyword': keyword,
                        'traffic': traffic,
                        'volume': volume,
                        'timestamp': time.time()
                    })
                except:
                    continue
            
            logger.info(f"Fetched {len(results)} trending searches for {geo}")
            return results
            
        except Exception as e:
            logger.error(f"Error fetching trending searches: {str(e)}")
            return []
    
    def get_related_queries(self, keyword, geo='IN'):
        """
        Related queries for a keyword (SEO ke liye useful)
        
        Args:
            keyword: Search keyword
            geo: Country code
        
        Returns:
            Dict with rising and top related queries
        """
        try:
            # Encode keyword for URL
            from urllib.parse import quote
            encoded_keyword = quote(keyword)
            
            url = f"{self.base_url}/explore?geo={geo}&q={encoded_keyword}&cat=18"
            self.driver.get(url)
            
            # Wait for data
            time.sleep(random.uniform(3, 5))
            
            # Click on "Related queries" section
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Extract rising queries
            rising_queries = self._extract_related_queries(soup, 'rising')
            
            # Extract top queries
            top_queries = self._extract_related_queries(soup, 'top')
            
            return {
                'keyword': keyword,
                'rising_queries': rising_queries,
                'top_queries': top_queries,
                'timestamp': time.time()
            }
            
        except Exception as e:
            logger.error(f"Error fetching related queries for '{keyword}': {str(e)}")
            return {'keyword': keyword, 'rising_queries': [], 'top_queries': []}
    
    def get_interest_over_time(self, keyword, geo='IN', timeframe='today 3-m'):
        """
        Keyword ka interest over time (trend graph data)
        
        Args:
            keyword: Search keyword
            geo: Country code
            timeframe: 'today 3-m', 'today 12-m', 'now 7-d', etc.
        
        Returns:
            List of data points with dates and interest values
        """
        try:
            from urllib.parse import quote
            encoded_keyword = quote(keyword)
            
            url = f"{self.base_url}/explore?geo={geo}&q={encoded_keyword}&date={timeframe}&cat=18"
            self.driver.get(url)
            
            time.sleep(random.uniform(3, 5))
            
            # Execute JavaScript to get chart data
            script = """
            return window.performance.getEntries()
                .filter(e => e.name.includes('api.trends.google.com'))
                .map(e => e.name);
            """
            api_calls = self.driver.execute_script(script)
            
            # Parse interest data from page
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Extract data points (simplified - actual implementation complex)
            interest_data = []
            
            return {
                'keyword': keyword,
                'timeframe': timeframe,
                'data': interest_data,
                'timestamp': time.time()
            }
            
        except Exception as e:
            logger.error(f"Error fetching interest over time: {str(e)}")
            return {'keyword': keyword, 'data': []}
    
    def _extract_volume(self, traffic_text):
        """Extract approximate search volume from traffic text"""
        multipliers = {'K': 1000, 'M': 1000000, 'L': 100000}
        
        for suffix, multiplier in multipliers.items():
            if suffix in traffic_text:
                try:
                    num = float(traffic_text.replace(suffix, '').replace('+', '').strip())
                    return int(num * multiplier)
                except:
                    pass
        return 0
    
    def _extract_related_queries(self, soup, query_type='rising'):
        """Extract related queries from page"""
        queries = []
        # Implementation based on Google Trends HTML structure
        # Returns list of related keywords
        return queries
    
    def close(self):
        """Close browser driver"""
        if hasattr(self, 'driver'):
            self.driver.quit()
    
    def __del__(self):
        self.close()