import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime
import pytz
import os
import re

def fetch_calendar_data(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.encoding = 'utf-8'
        if response.status_code != 200:
            print(f"Failed to fetch data: {response.status_code}")
            return None
        return response.text
    except Exception as e:
        print(f"Request error: {e}")
        return None

def parse_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    events = []
    
    # GCatholic 2026 页面结构：通常日期在 <td> 或 <div> 中，且带有特定 ID
    # 查找所有包含日期信息的元素
    # 该网站通常使用 id="d20260101" 这种格式
    day_elements = soup.find_all(id=re.compile(r'^d2026\d{4}$'))
    
    if not day_elements:
        # 备选方案：查找所有带有日期数字的单元格
        day_elements = soup.find_all(['td', 'div'], class_=re.compile(r'cal'))

    for day in day_elements:
        try:
            element_id = day.get('id', '')
            if not element_id.startswith('d2026'):
                continue
            
            # 提取日期
            date_str = element_id[1:] # "20260101"
            dt = datetime.strptime(date_str, '%Y%m%d')
            
            # 提取活动名称
            # GCatholic 的活动通常在 <a> 标签中，或者带有 'clt' (liturgy title) 类的 span/div 中
            event_tags = day.find_all(['a', 'span', 'div'], class_=re.compile(r'cl|ev|tit'))
            
            # 过滤并去重活动名称
            day_event_names = []
            for tag in event_tags:
                text = tag.get_text(strip=True)
                # 过滤掉纯数字（日期数字）和过短的无效字符
                if text and not text.isdigit() and len(text) > 1:
                    if text not in day_event_names:
                        day_event_names.append(text)
            
            for name in day_event_names:
                events.append({
                    'date': dt,
                    'summary': name
                })
        except Exception as e:
            continue
            
    return events

def generate_ics(events, output_file):
    cal = Calendar()
    cal.add('prodid', '-//GCatholic HK Calendar//mxm.io//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', '天主教香港教区礼仪日历 2026')
    cal.add('x-wr-timezone', 'Asia/Hong_Kong')
    cal.add('method', 'PUBLISH')

    for e in events:
        event = Event()
        event.add('summary', e['summary'])
        event.add('dtstart', e['date'].date())
        # 设置结束日期为次日（全天事件标准格式）
        # 这里 icalendar 库处理 date 对象会自动设为全天
        event.add('dtstamp', datetime.now(pytz.utc))
        event.add('uid', f"{e['date'].strftime('%Y%m%d')}-{hash(e['summary'])}@gcatholic")
        cal.add_component(event)

    with open(output_file, 'wb') as f:
        f.write(cal.to_ical())

if __name__ == "__main__":
    TARGET_URL = "https://gcatholic.org/calendar/2026/HK-zt"
    OUTPUT_PATH = "catholic_hk_2026.ics"
    
    print("Fetching data from GCatholic...")
    html = fetch_calendar_data(TARGET_URL)
    if html:
        print("Analyzing HTML structure...")
        events = parse_html(html)
        if not events:
            print("Warning: No events found. Please check if the website structure has changed.")
        else:
            print(f"Found {len(events)} events. Generating ICS...")
            generate_ics(events, OUTPUT_PATH)
            print(f"Success: {OUTPUT_PATH} generated with {len(events)} events.")
    else:
        print("Failed to retrieve HTML content.")
