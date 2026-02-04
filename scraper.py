import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime, timezone, timedelta
import re
import hashlib
import time
import random

try:
    import zhconv
except ImportError:
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
    
    # 使用字典来存储每一天的活动列表，key=date, value=[summary1, summary2]
    # 这样可以方便合并同一天的内容，并保持网页上的原始顺序
    events_map = {}
    
    rows = soup.find_all('tr')
    print(f"🔍 扫描到 {len(rows)} 个表格行，开始解析...")

    current_month = 1
    current_day = 0
    year = 2026
    
    exclude_keywords_partial = ['日期']
    # 在这里增加了 'I', 'II', 'III', 'IV' 等罗马数字的屏蔽
    exclude_exact_match = [
        '星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日', '主日',
        '自*', '自', 'O', 'M', 'F', 'S', 'P', 'W', 'R', 'G', 'V', 'L', 'D', 'Lit.', 'Ordo',
        'I', 'II', 'III', 'IV', 'V'
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
        
        for cell in cells:
            # 使用 separator='' 避免中文之间出现不必要的空格（如 "圣若瑟 劳工" -> "圣若瑟劳工"）
            # 但为了防止英文粘连，我们先获取，再手动处理
            cell_text = cell.get_text(strip=True, separator=' ')
            
            if re.match(r'^[\d\s/-]+$', cell_text) or re.match(r'^\d+月\d+日$', cell_text): continue
            if cell_text in month_names: continue
            if cell_text in exclude_exact_match: continue
            if any(k in cell_text for k in exclude_keywords_partial): continue
            if cell_text.replace('*', '').strip() in ['自', 'O', 'M']: continue
            if len(cell_text) < 2 and not re.search(r'[\u4e00-\u9fff]', cell_text): continue

            clean_text = cell_text.replace('自*', '').replace('自 ', '').strip()
            clean_text = re.sub(r'^\d+\s*', '', clean_text)
            
            # 修复中文中间的空格 (例如 "圣若瑟 劳工" -> "圣若瑟劳工")
            # 逻辑：如果空格两边都是中文字符，则去掉空格
            clean_text = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', clean_text)

            if len(clean_text) > 1:
                try:
                    dt = datetime(year, current_month, current_day)
                    if dt not in events_map:
                        events_map[dt] = []
                    
                    # 只有当该文本还没被添加过时才添加（去重）
                    if clean_text not in events_map[dt]:
                        events_map[dt].append(clean_text)
                except ValueError:
                    continue

    # 将 map 转换为 list 以便后续处理，保持日期排序
    sorted_events = []
    for dt in sorted(events_map.keys()):
        # 合并同一天的所有事件，用 " | " 分隔
        # 网页解析是从上到下的，所以 events_map[dt] 里的顺序就是网页显示的顺序
        # 这样 "复活期..." (Row 1) 就会排在 "圣若瑟..." (Row 2) 前面
        full_summary = " | ".join(events_map[dt])
        sorted_events.append({'date': dt, 'summary': full_summary})

    print(f"✅ 解析完成，共提取 {len(sorted_events)} 天的数据 (已合并同日事件)")
    return sorted_events

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
            
            summary_text = e['summary']
            if convert_to_simplified and zhconv:
                summary_text = zhconv.convert(summary_text, 'zh-cn')
                
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
        
        print(f"✍️ 正在生成繁体版: {FILE_HK}")
        generate_ics(extracted_events, FILE_HK, '天主教香港教区礼仪日历 2026')
        
        if zhconv:
            print(f"✍️ 正在生成简体版: {FILE_CN}")
            generate_ics(extracted_events, FILE_CN, '天主教礼仪日历 2026 (简)', convert_to_simplified=True)
        else:
            print("⚠️ zhconv 未安装，跳过简体版生成")
            
        print("🎉 所有任务完成！")
    else:
        print("❌ 无法获取网页")
