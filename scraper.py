import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime
import pytz
import re
import hashlib

def fetch_calendar_data(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.encoding = 'utf-8'
        if response.status_code != 200:
            print(f"Error: HTTP {response.status_code}")
            return None
        return response.text
    except Exception as e:
        print(f"Fetch error: {e}")
        return None

def parse_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    events = []
    
    # 1. 查找所有日期容器 (ID 格式为 d2026XXXX)
    day_containers = soup.find_all(id=re.compile(r'^d2026\d{4}$'))
    print(f"Found {len(day_containers)} potential day containers.")

    for day in day_containers:
        try:
            date_id = day.get('id')
            date_str = date_id[1:]  # 去掉开头的 'd'
            dt = datetime.strptime(date_str, '%Y%m%d')
            
            # 2. 在日期容器内查找活动标题
            # 网站特征：活动通常在 <a> 标签中，且类名包含 'cl' (cl1, cl2, clt...)
            found_tags = day.find_all(['a', 'span'], class_=re.compile(r'cl\w+'))
            
            day_event_names = []
            for tag in found_tags:
                text = tag.get_text(strip=True)
                # 排除纯数字、重复项、以及过短的干扰项
                if text and not text.isdigit() and len(text) > 1:
                    if text not in day_event_names:
                        day_event_names.append(text)
            
            # 如果没找到带类的标签，尝试获取容器内所有 <a> 标签文本
            if not day_event_names:
                links = day.find_all('a')
                for link in links:
                    text = link.get_text(strip=True)
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
    cal.add('prodid', '-//GCatholic HK//mxm.io//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', '天主教香港教区礼仪日历 2026')
    cal.add('x-wr-timezone', 'Asia/Hong_Kong')
    cal.add('method', 'PUBLISH')

    for e in events:
        event = Event()
        # 使用摘要和日期的组合生成唯一 ID
        uid_seed = f"{e['date'].strftime('%Y%m%d')}{e['summary']}"
        uid = hashlib.md5(uid_seed.encode()).hexdigest() + "@gcatholic.org"
        
        event.add('summary', e['summary'])
        event.add('dtstart', e['date'].date())
        # 结束日期设为次日，确保苹果日历正确显示为全天事件
        event.add('dtstamp', datetime.now(pytz.utc))
        event.add('uid', uid)
        event.add('description', '来源: GCatholic.org')
        cal.add_component(event)

    with open(output_file, 'wb') as f:
        f.write(cal.to_ical())

if __name__ == "__main__":
    TARGET_URL = "https://gcatholic.org/calendar/2026/HK-zt"
    OUTPUT_PATH = "catholic_hk_2026.ics"
    
    print(f"Target: {TARGET_URL}")
    html = fetch_calendar_data(TARGET_URL)
    
    if html:
        events = parse_html(html)
        if not events:
            print("Failed: No events extracted. The website layout might have changed.")
        else:
            print(f"Extracted {len(events)} events.")
            generate_ics(events, OUTPUT_PATH)
            print(f"Success: {OUTPUT_PATH} updated.")
    else:
        print("Failed: Could not retrieve page content.")
