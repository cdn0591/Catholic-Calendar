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
            
            if response.status_code == 200:
                return response.text
                
        except Exception as e:
            print(f"❌ 请求异常: {e}")
            time.sleep(5)
            
    return None

def parse_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    events = []
    
    # 策略：按表格行 (tr) 解析，并处理 rowspan 情况
    rows = soup.find_all('tr')
    print(f"🔍 扫描到 {len(rows)} 个表格行，开始解析...")

    current_month = 1
    current_day = 0
    year = 2026
    
    # 定义中文月份，用于排除月份标题行
    month_names = ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月']

    for row in rows:
        row_text = row.get_text(strip=True)
        
        # --- 1. 尝试寻找日期 ---
        day_num = None
        
        # A. 优先匹配 "M月D日" 格式 (针对跨月部分)
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
        
        # B. 尝试找行内的独立数字单元格 (针对普通日期行)
        if day_num is None:
            cells = row.find_all(['td', 'th'])
            for cell in cells:
                ctext = cell.get_text(strip=True)
                if ctext.isdigit():
                    d = int(ctext)
                    # 逻辑校验：日期应该是递增的，或者换月变成了1
                    if 1 <= d <= 31:
                        if d == current_day + 1 or d == 1 or d == current_day:
                            day_num = d
                            break
        
        # --- 2. 日期状态更新与逻辑判断 ---
        if day_num is not None:
            # 找到了新日期，更新状态
            if day_num < current_day and current_month < 12 and day_num == 1:
                current_month += 1
            current_day = day_num
        else:
            # === 关键修复 ===
            # 如果没找到日期，说明可能是 rowspan 的第二行，或者是个标题行
            
            # 排除情况1：还没开始解析到任何日期
            if current_day == 0: continue
            
            # 排除情况2：是纯月份标题 (如 "三月")
            if row_text in month_names or "月" in row_text and len(row_text) < 4: continue
            
            # 排除情况3：是表头 (如 "日期 星期")
            if "星期" in row_text and "日期" in row_text: continue
            
            # 如果排除以上情况，我们假设这是属于 current_day 的后续活动行
            pass

        # --- 3. 提取活动 ---
        links = row.find_all('a')
        day_summaries = []
        
        for link in links:
            text = link.get_text(strip=True)
            href = link.get('href', '')
            
            # 过滤规则
            if (len(text) > 1 and 
                not text.isdigit() and 
                "Ordo" not in text and
                "reading" not in href.lower()): 
                
                day_summaries.append(text)
        
        # 备选：如果没有链接，尝试提取非数字的文本 (针对没有链接的节日)
        if not day_summaries:
            # 移除日期数字，防止把 "15" 当作节日
            clean_text = re.sub(r'\d{1,2}\s*[月/]\s*\d{1,2}', '', row_text)
            # 移除行首的纯数字 (如 "15")
            clean_text = re.sub(r'^\d+', '', clean_text).strip() 
            # 移除 "星期X"
            clean_text = re.sub(r'星期[一二三四五六日]', '', clean_text).strip()
            
            # 如果剩下的文本够长且不是无意义字符
            if len(clean_text) > 3 and clean_text not in month_names:
                # 再次清理可能残留的 "自*" 等标记
                clean_text = clean_text.replace('自*', '').strip()
                day_summaries.append(clean_text)

        # --- 4. 保存结果 ---
        if day_summaries:
            try:
                dt = datetime(year, current_month, current_day)
                for summary in day_summaries:
                    # 去重检查
                    if not any(e['date'] == dt and e['summary'] == summary for e in events):
                        events.append({'date': dt, 'summary': summary})
            except ValueError:
                continue

    print(f"✅ 解析完成，共提取 {len(events)} 条数据")
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
            # 使用日期+摘要做 UID，确保唯一性
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
