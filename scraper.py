import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime, timezone, timedelta
import re
import hashlib

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
}

def fetch_calendar_data(url):
    try:
        print(f"正在连接: {url} ...")
        session = requests.Session()
        response = session.get(url, headers=HEADERS, timeout=45)
        response.encoding = 'utf-8'
        return response.text
    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return None

def parse_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    events = []
    
    # 策略升级：直接查找所有包含日期的链接
    # GCatholic 的链接通常包含日期数字，例如 href="...20260101..."
    # 这种方法不依赖页面 ID，只要有链接就能抓到
    all_links = soup.find_all('a', href=True)
    print(f"🔍 页面共找到 {len(all_links)} 个链接，正在筛选...")

    # 用于去重 (日期+标题)
    seen_events = set()

    for link in all_links:
        try:
            href = link['href']
            text = link.get_text(strip=True)
            
            # 1. 从链接中提取日期 (匹配 2026MMDD)
            # 兼容几种格式: /20260101, date=20260101, 20260101.html
            date_match = re.search(r'(2026)(\d{2})(\d{2})', href)
            
            if not date_match:
                continue

            year, month, day = map(int, date_match.groups())
            event_date = datetime(year, month, day)

            # 2. 过滤无效文本
            # 排除纯数字(通常是日历上的号数)、短代码(Ordo, W, R)
            if (not text or 
                text.isdigit() or 
                len(text) < 2 or 
                text in ['Ordo', 'Vespers', 'Lauds', 'Mass', 'Readings', 'Lit.', 'D', 'L', 'R', 'W', 'V', 'G', 'P']):
                continue

            # 3. 这里的文本通常就是节日名称
            # 清理文本，去掉多余的符号
            clean_summary = text.replace('\n', ' ').strip()
            
            # 生成唯一标识用于去重
            unique_key = f"{event_date.strftime('%Y-%m-%d')}|{clean_summary}"
            
            if unique_key not in seen_events:
                events.append({
                    'date': event_date,
                    'summary': clean_summary
                })
                seen_events.add(unique_key)
                
        except Exception as e:
            continue

    # 按日期排序
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
        event.add('summary', '暂无数据')
        event.add('dtstart', datetime(2026, 1, 1).date())
        cal.add_component(event)
    else:
        for e in events:
            event = Event()
            # 使用日期+摘要做 UID
            uid_seed = f"{e['date'].strftime('%Y%m%d')}-{e['summary']}"
            uid = hashlib.md5(uid_seed.encode()).hexdigest() + "@gcatholic"
            
            event.add('summary', e['summary'])
            event.add('dtstart', e['date'].date())
            # 设置为全天事件 (结束时间为第二天)
            event.add('dtend', (e['date'] + timedelta(days=1)).date())
            event.add('dtstamp', datetime.now(timezone.utc))
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
        print(f"✅ 成功提取: {len(extracted_events)} 条活动")
        generate_ics(extracted_events, OUTPUT_PATH)
    else:
        generate_ics([], OUTPUT_PATH)
