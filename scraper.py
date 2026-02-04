import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime, timezone, timedelta
import re
import hashlib
import time
import random

# ===========================
# 1. 网络请求模块 (保持不变，因为已经成功)
# ===========================
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
            
            # 调试：打印网页标题
            page_title = ""
            try:
                soup_check = BeautifulSoup(response.text[:10000], 'html.parser')
                page_title = soup_check.title.string.strip() if soup_check.title else "无标题"
            except:
                pass

            print(f"📄 状态码: {response.status_code} | 标题: {page_title}")
            
            if "Just a moment" in page_title or "Security" in page_title:
                print("⚠️ 被拦截，正在重试...")
                time.sleep(10)
                continue
                
            if response.status_code == 200:
                return response.text
                
        except Exception as e:
            print(f"❌ 请求异常: {e}")
            time.sleep(5)
            
    return None

# ===========================
# 2. 解析模块 (核心修改：改回链接扫描)
# ===========================
def parse_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    events = []
    
    # 查找页面上所有的链接 <a>
    all_links = soup.find_all('a', href=True)
    print(f"🔍 页面共包含 {len(all_links)} 个链接，开始筛选有效数据...")

    seen_keys = set()
    valid_count = 0

    for link in all_links:
        try:
            href = link['href']
            text = link.get_text(strip=True)
            
            # 1. 核心特征：链接地址里包含 2026xxxx 这样的日期
            # 无论是 #d20260101 还是 /20260101.htm 都能匹配
            date_match = re.search(r'(2026)(\d{2})(\d{2})', href)
            
            if not date_match:
                continue

            # 提取日期
            year, month, day = map(int, date_match.groups())
            
            # 2. 过滤掉纯数字链接 (那是日历上的日期号数，不是节日名)
            if text.isdigit():
                continue
                
            # 3. 过滤掉无意义的短词
            if len(text) < 2 or text in ['Ordo', 'Mass', 'Readings', 'Lit.', 'D', 'L', 'R', 'W', 'V', 'G', 'P']:
                continue

            # 4. 成功匹配
            dt = datetime(year, month, day)
            summary = text.replace('\n', ' ').strip()
            
            # 去重键 (日期+名称)
            key = f"{dt.strftime('%Y%m%d')}_{summary}"
            
            if key not in seen_keys:
                events.append({'date': dt, 'summary': summary})
                seen_keys.add(key)
                valid_count += 1
                
        except Exception:
            continue

    print(f"✅ 筛选出 {valid_count} 条有效节日数据")
    
    # 按日期排序
    events.sort(key=lambda x: x['date'])
    return events

# ===========================
# 3. 生成模块
# ===========================
def generate_ics(events, output_file):
    cal = Calendar()
    cal.add('prodid', '-//GCatholic HK//mxm.io//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', '天主教香港教区礼仪日历 2026')
    cal.add('x-wr-timezone', 'Asia/Hong_Kong')
    
    if not events:
        print("⚠️ 警告：没有抓取到任何事件，生成占位文件。")
        event = Event()
        event.add('summary', '暂无数据 - 请检查脚本')
        event.add('dtstart', datetime(2026, 1, 1).date())
        cal.add_component(event)
    else:
        for e in events:
            event = Event()
            uid = hashlib.md5(f"{e['date']}{e['summary']}".encode()).hexdigest() + "@gcatholic"
            
            event.add('summary', e['summary'])
            event.add('dtstart', e['date'].date())
            # 全天事件：结束时间 = 开始时间 + 1天
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
        print(f"🎉 处理完成！文件已生成: {OUTPUT_PATH}")
    else:
        print("❌ 致命错误：无法获取网页内容")
        generate_ics([], OUTPUT_PATH)
