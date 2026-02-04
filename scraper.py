import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime, timezone, timedelta
import re
import hashlib
import time
import random

def fetch_calendar_data(url):
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
    ]
    
    for attempt in range(3):
        try:
            print(f"🔄 尝试连接 (第 {attempt + 1}/3 次)...")
            headers = {
                'User-Agent': user_agents[attempt % len(user_agents)],
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
                'Referer': 'https://www.google.com/'
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            response.encoding = 'utf-8'
            
            # 简单检查
            if response.status_code == 200:
                return response.text
                
        except Exception as e:
            print(f"❌ 请求异常: {e}")
            time.sleep(5)
            
    return None

def parse_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    events = []
    
    # 调试：打印页面中前 5 个链接的完整信息，帮助定位问题
    print("🔍 [调试信息] 页面链接样本:")
    sample_links = soup.find_all('a', href=True, limit=5)
    for i, link in enumerate(sample_links):
        print(f"   Link {i+1}: Text='{link.get_text(strip=True)}' | Href='{link['href']}'")

    # 策略升级：按“行” (tr) 解析
    # 日历通常是一行一行排列的
    rows = soup.find_all('tr')
    print(f"🔍 扫描到 {len(rows)} 个表格行，开始解析...")

    current_month = 1
    current_day = 0
    year = 2026
    
    for row in rows:
        # 获取该行所有文本
        row_text = row.get_text(strip=True)
        
        # 1. 尝试寻找日期数字
        # 匹配规则：行首的数字，或包含 "M月D日" 格式
        day_num = None
        
        # 优先匹配中文日期格式 "1月1日" 或 "1/1"
        date_match = re.search(r'(\d{1,2})\s*[月/]\s*(\d{1,2})', row_text)
        if date_match:
            try:
                m = int(date_match.group(1))
                d = int(date_match.group(2))
                if 1 <= m <= 12 and 1 <= d <= 31:
                    current_month = m
                    day_num = d
            except:
                pass
        
        # 如果没有中文格式，尝试找行内的独立数字
        if day_num is None:
            # 获取行内所有单元格
            cells = row.find_all(['td', 'th'])
            for cell in cells:
                # 检查单元格是否只包含数字（可能是日期格）
                ctext = cell.get_text(strip=True)
                if ctext.isdigit():
                    d = int(ctext)
                    if 1 <= d <= 31:
                        # 简单的逻辑判断：日期应该是递增的
                        if d == current_day + 1 or d == 1:
                            day_num = d
                            break
                        # 或者是当前日期（同一天的不同活动）
                        elif d == current_day:
                            day_num = d
                            break
        
        if day_num is None:
            continue
            
        # 更新全局日期
        if day_num < current_day and current_month < 12 and day_num == 1:
            current_month += 1
        current_day = day_num
        
        # 2. 提取链接作为活动
        links = row.find_all('a')
        day_summaries = []
        
        for link in links:
            text = link.get_text(strip=True)
            href = link.get('href', '')
            
            # 过滤规则
            if (len(text) > 1 and 
                not text.isdigit() and 
                "Ordo" not in text and
                "reading" not in href.lower()): # 排除读经链接
                
                day_summaries.append(text)
        
        # 如果没有链接，尝试提取非数字的文本
        if not day_summaries:
            # 移除数字和日期部分，剩下的可能是标题
            clean_text = re.sub(r'\d{1,2}\s*[月/]\s*\d{1,2}', '', row_text) # 去掉 1月1日
            clean_text = re.sub(r'^\d+', '', clean_text).strip() # 去掉行首数字
            if len(clean_text) > 3:
                day_summaries.append(clean_text)

        # 3. 保存
        if day_summaries:
            try:
                dt = datetime(year, current_month, current_day)
                for summary in day_summaries:
                    # 去重
                    key = f"{dt}_{summary}"
                    # 简单检查列表中是否已存在
                    if not any(e['date'] == dt and e['summary'] == summary for e in events):
                        events.append({'date': dt, 'summary': summary})
            except ValueError:
                continue

    print(f"✅ 解析完成，共提取 {len(events)} 条数据")
    
    # 排序
    events.sort(key=lambda x: x['date'])
    return events

def generate_ics(events, output_file):
    cal = Calendar()
    cal.add('prodid', '-//GCatholic HK//mxm.io//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', '天主教香港教区礼仪日历 2026')
    cal.add('x-wr-timezone', 'Asia/Hong_Kong')
    
    if not events:
        event = Event()
        event.add('summary', '暂无数据 - 请检查日志中的链接样本')
        event.add('dtstart', datetime(2026, 1, 1).date())
        cal.add_component(event)
    else:
        for e in events:
            event = Event()
            uid = hashlib.md5(f"{e['date']}{e['summary']}".encode()).hexdigest() + "@gcatholic"
            
            event.add('summary', e['summary'])
            event.add('dtstart', e['date'].date())
            event.add('dtend', (e['date'] + timedelta(days=1)).date())
            event.add('uid', uid)
            cal.add_component(event)

    with open(output_file, 'wb') as f:
        f.write(cal.to_ical())

if __name__ == "__main__":
    TARGET_URL = "https://gcatholic.org/calendar/2026/HK-zt"
    OUTPUT_PATH = "catholic_hk_2026.ics"
    
    html = fetch_calendar_data(TARGET_URL)
    
    if html:
        extracted_events = parse_html(html)
        generate_ics(extracted_events, OUTPUT_PATH)
        print(f"🎉 文件已更新: {OUTPUT_PATH}")
    else:
        print("❌ 无法获取网页")
        generate_ics([], OUTPUT_PATH)
