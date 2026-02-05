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
            print(f"🔄 尝试连接 (第 {attempt + 1}/3 次): {url} ...")
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

def get_liturgical_emoji(cell_soup):
    """
    扫描单元格内部标签的 class 和 style 属性，
    判断礼仪颜色并返回对应的 Emoji。
    """
    # 遍历单元格内所有子标签
    for tag in cell_soup.find_all(True):
        # 获取 class 列表 (转为字符串)
        classes = " ".join(tag.get('class', [])).lower()
        # 获取 style 属性
        style = str(tag.get('style', '')).lower()
        
        # 拼接检查字符串
        check_str = f"{classes} {style}"
        
        # 颜色判断逻辑 (优先级：绿 > 紫 > 红 > 白)
        if 'green' in check_str:
            return "🟢 "
        elif 'violet' in check_str or 'purple' in check_str:
            return "🟣 "
        elif 'red' in check_str:
            return "🔴 "
        elif 'white' in check_str:
            return "⚪ "
        elif 'gold' in check_str or 'yellow' in check_str:
            return "🟡 "
            
    return ""

def parse_html(html_content, target_year):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    events_map = {}
    
    rows = soup.find_all('tr')
    print(f"🔍 [{target_year}] 扫描到 {len(rows)} 个表格行，开始解析...")

    current_month = 1
    current_day = 0
    year = target_year
    
    exclude_keywords_partial = ['日期']
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
            cell_text = cell.get_text(strip=True, separator=' ')
            
            # 基础过滤
            if re.match(r'^[\d\s/-]+$', cell_text) or re.match(r'^\d+月\d+日$', cell_text): continue
            if cell_text in month_names: continue
            if cell_text in exclude_exact_match: continue
            if any(k in cell_text for k in exclude_keywords_partial): continue
            if cell_text.replace('*', '').strip() in ['自', 'O', 'M']: continue
            if len(cell_text) < 2 and not re.search(r'[\u4e00-\u9fff]', cell_text): continue

            # === 核心修改：获取颜色 Emoji ===
            emoji_prefix = get_liturgical_emoji(cell)

            # 文本清洗
            clean_text = cell_text.replace('自*', '').replace('自 ', '').strip()
            clean_text = re.sub(r'^\d+\s*', '', clean_text)
            clean_text = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', clean_text)

            if len(clean_text) > 1:
                try:
                    dt = datetime(year, current_month, current_day)
                    if dt not in events_map:
                        events_map[dt] = []
                    
                    # 组合 Emoji 和 文本
                    final_text = f"{emoji_prefix}{clean_text}"
                    
                    # 去重检查 (只检查文本部分，忽略 emoji 差异，防止同一节日因颜色判定不同重复)
                    # 但为了简单，直接检查完整字符串
                    if final_text not in events_map[dt]:
                        events_map[dt].append(final_text)
                except ValueError:
                    continue

    sorted_events = []
    for dt in sorted(events_map.keys()):
        full_summary = " | ".join(events_map[dt])
        sorted_events.append({'date': dt, 'summary': full_summary})

    print(f"✅ [{target_year}] 解析完成，共提取 {len(sorted_events)} 天的数据")
    return sorted_events

def generate_ics(events, output_file, calendar_name, year, convert_to_simplified=False):
    cal = Calendar()
    cal.add('prodid', '-//GCatholic HK//mxm.io//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', calendar_name)
    cal.add('x-wr-timezone', 'Asia/Hong_Kong')
    
    if not events:
        event = Event()
        event.add('summary', '暂无数据')
        event.add('dtstart', datetime(year, 1, 1).date())
        cal.add_component(event)
    else:
        for e in events:
            event = Event()
            
            summary_text = e['summary']
            if convert_to_simplified and zhconv:
                # 繁简转换时，emoji 不会被影响，因为它们不是中文字符
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
    TASKS = [
        { "year": 2026, "url": "https://gcatholic.org/calendar/2026/HK-zt" },
        { "year": 2027, "url": "https://gcatholic.org/calendar/2027/General-D-zt" },
        { "year": 2028, "url": "https://gcatholic.org/calendar/2028/General-D-zt" },
        { "year": 2029, "url": "https://gcatholic.org/calendar/2029/General-D-zt" }
    ]
    
    master_events = []

    print("🚀 启动批量抓取任务 (2026-2029) + 颜色识别...")
    
    for task in TASKS:
        html = fetch_calendar_data(task['url'])
        if html:
            extracted_events = parse_html(html, task['year'])
            master_events.extend(extracted_events)
        else:
            print(f"❌ 严重错误: 无法获取 {task['year']} 年数据，该年份将被跳过。")

    master_events.sort(key=lambda x: x['date'])
    
    print(f"\n📊 统计: 4年共收集到 {len(master_events)} 条数据，准备生成合并文件...")

    # 1. 生成合并繁体版
    FILE_TRAD = "catholic_calendar_2026-2029.ics"
    print(f"✍️ 生成合并繁体版: {FILE_TRAD}")
    generate_ics(master_events, FILE_TRAD, "天主教礼仪日历 2026-2029", 2026)
    
    # 2. 生成合并简体版
    if zhconv:
        FILE_SIMP = "catholic_calendar_2026-2029_cn.ics"
        print(f"✍️ 生成合并简体版: {FILE_SIMP}")
        generate_ics(master_events, FILE_SIMP, "天主教礼仪日历 2026-2029 (简)", 2026, convert_to_simplified=True)
    else:
        print("⚠️ zhconv 未安装，跳过简体版生成")
        
    print("🎉 任务全部完成！")
