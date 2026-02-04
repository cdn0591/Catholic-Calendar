import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime, timezone, timedelta
import re
import hashlib
import time
import random

# 尝试导入繁简转换库，如果未安装则报错提示
try:
    import zhconv
except ImportError:
    print("❌ 错误: 未安装 zhconv 库。请在 requirements 或 workflow 中添加 'pip install zhconv'")
    zhconv = None

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
    
    rows = soup.find_all('tr')
    print(f"🔍 扫描到 {len(rows)} 个表格行，开始解析...")

    current_month = 1
    current_day = 0
    year = 2026
    
    exclude_keywords_partial = ['日期']
    exclude_exact_match = [
        '星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日', '主日',
        '自*', '自', 'O', 'M', 'F', 'S', 'P', 'W', 'R', 'G', 'V', 'L', 'D', 'Lit.', 'Ordo'
    ]
    month_names = ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月']

    for row in rows:
        row_text = row.get_text(strip=True)
        
        # --- 1. 日期定位 ---
        day_num = None
        date_match = re.search(r'(\d{1,2})\s*[月/]\s*(\d{1,2})', row_text)
        if date_match:
            try:
                m = int(date_match.group(1))
                d = int(date_match.group(2))
                if 1 <= m <= 12 and 1 <= d <= 31:
                    current_month = m
                    day_num = d
            except: pass
        
        if day_num is None:
            cells = row.find_all(['td', 'th'])
            for cell in cells:
                ctext = cell.get_text(strip=True)
                if ctext.isdigit():
                    d = int(ctext)
                    if 1 <= d <= 31:
                        if d == current_day + 1 or d == 1 or d == current_day:
                            day_num = d
                            break

        if day_num is not None:
            if day_num < current_day and current_month < 12 and day_num == 1:
                current_month += 1
            current_day = day_num
        else:
            if current_day == 0: continue
            if row_text in month_names or "月" in row_text and len(row_text) < 4: continue
            if "星期" in row_text and "日期" in row_text: continue
            pass

        # --- 2. 提取内容 ---
        cells = row.find_all(['td', 'th'])
        day_summaries = []

        for cell in cells:
            cell_text = cell.get_text(strip=True, separator=' ')
            
            if re.match(r'^[\d\s/-]+$', cell_text) or re.match(r'^\d+月\d+日$', cell_text): continue
            if cell_text in month_names: continue
            if cell_text in exclude_exact_match: continue
            if any(k in cell_text for k in exclude_keywords_partial): continue
            if cell_text.replace('*', '').strip() in ['自', 'O', 'M']: continue
            if len(cell_text) < 2 and not re.search(r'[\u4e00-\u9fff]', cell_text): continue

            clean_text = cell_text.replace('自*', '').replace('自 ', '').strip()
            clean_text = re.sub(r'^\d+\s*', '', clean_text)

            if len(clean_text) > 1:
                day_summaries.append(clean_text)

        # --- 3. 保存 ---
        if day_summaries:
            try:
                dt = datetime(year, current_month, current_day)
                for summary in day_summaries:
                    if not any(e['date'] == dt and e['summary'] == summary for e in events):
                        events.append({'date': dt, 'summary': summary})
            except ValueError:
                continue

    print(f"✅ 解析完成，共提取 {len(events)} 条数据 (原始繁体)")
    events.sort(key=lambda x: x['date'])
    return events

def generate_ics(events, output_file, calendar_name, convert_to_simplified=False):
    cal = Calendar()
    cal.add('prodid', '-//GCatholic HK//mxm.io//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', calendar_name)
    cal.add('x-wr-timezone', 'Asia/Hong_Kong')
    
    if not events:
        event = Event()
        event.add('summary', '暂无数据')
        event.add('dtstart', datetime(2026, 1, 1).date())
        cal.add_component(event)
    else:
        for e in events:
            event = Event()
            
            # 处理文本
            summary_text = e['summary']
            if convert_to_simplified and zhconv:
                summary_text = zhconv.convert(summary_text, 'zh-cn')
                
            # 使用日期+摘要做 UID
            uid = hashlib.md5(f"{e['date']}{summary_text}".encode()).hexdigest() + "@gcatholic"
            
            event.add('summary', summary_text)
            event.add('dtstart', e['date'].date())
            event.add('dtend', (e['date'] + timedelta(days=1)).date())
            event.add('uid', uid)
            cal.add_component(event)

    with open(output_file, 'wb') as f:
        f.write(cal.to_ical())

if __name__ == "__main__":
    TARGET_URL = "https://gcatholic.org/calendar/2026/HK-zt"
    
    FILE_HK = "catholic_hk_2026.ics"
    FILE_CN = "catholic_cn_2026.ics"
    
    html = fetch_calendar_data(TARGET_URL)
    
    if html:
        extracted_events = parse_html(html)
        
        # 1. 生成繁体版 (香港)
        print(f"✍️ 正在生成繁体版: {FILE_HK}")
        generate_ics(extracted_events, FILE_HK, '天主教香港教区礼仪日历 2026')
        
        # 2. 生成简体版 (大陆)
        if zhconv:
            print(f"✍️ 正在生成简体版: {FILE_CN}")
            generate_ics(extracted_events, FILE_CN, '天主教礼仪日历 2026 (简)', convert_to_simplified=True)
        else:
            print("⚠️ zhconv 未安装，跳过简体版生成")
            
        print("🎉 所有任务完成！")
    else:
        print("❌ 无法获取网页")
