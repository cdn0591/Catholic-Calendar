import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime, timezone, timedelta
import re
import hashlib

def fetch_calendar_data(url):
    # 模拟真实浏览器，防止被网站拦截
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    try:
        print(f"正在请求页面: {url}")
        response = requests.get(url, headers=headers, timeout=30)
        response.encoding = 'utf-8'
        if response.status_code != 200:
            print(f"错误: 网页返回状态码 {response.status_code}")
            return None
        return response.text
    except Exception as e:
        print(f"请求失败: {e}")
        return None

def parse_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    events = []
    
    # 查找所有日期容器 (ID 格式为 d2026XXXX)
    day_containers = soup.find_all(id=re.compile(r'^d2026\d{4}$'))
    print(f"找到 {len(day_containers)} 个日期单元格。")

    for day in day_containers:
        try:
            date_id = day.get('id')
            date_str = date_id[1:]
            dt = datetime.strptime(date_str, '%Y%m%d')
            
            # 查找活动名称：通常在 a 标签或具有 cl-title 类的元素中
            # 针对 gcatholic 特有的类名：cl1, cl2, clt, clh 等
            potential_tags = day.find_all(['a', 'span', 'div'], class_=re.compile(r'cl\w+|tit|ev'))
            
            day_event_names = []
            for tag in potential_tags:
                text = tag.get_text(strip=True)
                # 排除纯数字（日期）、空字符串和重复内容
                if text and not text.isdigit() and len(text) > 1:
                    if text not in day_event_names:
                        day_event_names.append(text)
            
            # 如果还是没找到，提取所有链接文本
            if not day_event_names:
                for link in day.find_all('a'):
                    text = link.get_text(strip=True)
                    if text and not text.isdigit() and len(text) > 1:
                        if text not in day_event_names:
                            day_event_names.append(text)

            for name in day_event_names:
                events.append({
                    'date': dt,
                    'summary': name
                })
        except Exception:
            continue
            
    return events

def generate_ics(events, output_file):
    cal = Calendar()
    cal.add('prodid', '-//GCatholic HK Calendar//mxm.io//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', '天主教香港教区礼仪日历 2026')
    cal.add('x-wr-timezone', 'Asia/Hong_Kong')
    cal.add('method', 'PUBLISH')

    if not events:
        # 如果没有抓到事件，添加一个提醒事件，防止 ics 文件完全为空
        event = Event()
        event.add('summary', '日历数据暂未更新或抓取失败')
        event.add('dtstart', datetime(2026, 1, 1).date())
        event.add('description', '请检查 GitHub Actions 运行记录')
        cal.add_component(event)
    else:
        for e in events:
            event = Event()
            uid_seed = f"{e['date'].strftime('%Y%m%d')}{e['summary']}"
            uid = hashlib.md5(uid_seed.encode()).hexdigest() + "@gcatholic.org"
            
            event.add('summary', e['summary'])
            event.add('dtstart', e['date'].date())
            # 苹果日历全天事件建议 dtend 为次日
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
        print(f"成功抓取到 {len(extracted_events)} 条活动数据。")
        generate_ics(extracted_events, OUTPUT_PATH)
        print(f"文件已更新: {OUTPUT_PATH}")
    else:
        # 即使失败也创建一个基础文件，防止 GitHub Actions 报错
        generate_ics([], OUTPUT_PATH)
        print("抓取失败，已生成基础占位文件。")
