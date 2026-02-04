import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime
import pytz
import os

def fetch_calendar_data(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    response = requests.get(url, headers=headers)
    response.encoding = 'utf-8'
    if response.status_code != 200:
        print(f"Failed to fetch data: {response.status_code}")
        return []
    return response.text

def parse_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    events = []
    
    # GCatholic 网页结构解析
    # 查找所有日期容器，通常是带有 class="cal-day" 的 div
    days = soup.find_all('div', class_='cal-day')
    
    for day in days:
        try:
            # 提取日期 (格式通常在 div 的 id 或内部文本中)
            date_str = day.get('id') # 示例: "d20260101"
            if not date_str or not date_str.startswith('d'):
                continue
            
            dt = datetime.strptime(date_str[1:], '%Y%m%d')
            
            # 提取活动名称
            # 查找内部的活动标题，通常在 a 标签或特定 span 中
            event_elements = day.find_all('span', class_='cal-event')
            for el in event_elements:
                summary = el.get_text(strip=True)
                if summary:
                    events.append({
                        'date': dt,
                        'summary': summary
                    })
        except Exception as e:
            print(f"Error parsing day: {e}")
            continue
            
    return events

def generate_ics(events, output_file):
    cal = Calendar()
    cal.add('prodid', '-//GCatholic HK Calendar//mxm.io//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', '天主教香港教区礼仪日历 2026')
    cal.add('x-wr-timezone', 'Asia/Hong_Kong')

    for e in events:
        event = Event()
        event.add('summary', e['summary'])
        event.add('dtstart', e['date'].date())
        # 全天事件不需要 dtend，或者设为次日开始
        event.add('description', '数据来源: GCatholic.org')
        cal.add_component(event)

    with open(output_file, 'wb') as f:
        f.write(cal.to_ical())

if __name__ == "__main__":
    TARGET_URL = "https://gcatholic.org/calendar/2026/HK-zt"
    OUTPUT_PATH = "catholic_hk_2026.ics"
    
    print("Fetching data...")
    html = fetch_calendar_data(TARGET_URL)
    if html:
        print("Parsing events...")
        events = parse_html(html)
        print(f"Found {len(events)} events. Generating ICS...")
        generate_ics(events, OUTPUT_PATH)
        print(f"Success: {OUTPUT_PATH} created.")
