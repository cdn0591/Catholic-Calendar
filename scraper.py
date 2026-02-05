import cloudscraper
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime, timezone, timedelta
import re
import hashlib
import time
import random
import sys

try:
    import zhconv
except ImportError:
    zhconv = None

# ===========================
# 1. 网络请求模块
# ===========================
def fetch_calendar_data(url):
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            print(f"🔄 [尝试 {attempt + 1}/{max_retries}] 连接: {url} ...")
            response = scraper.get(url, timeout=60)
            response.encoding = 'utf-8'
            
            # 简单校验
            if response.status_code == 200 and len(response.text) > 2000:
                return response.text
            
            print(f"   ⚠️ 状态码 {response.status_code} 或内容过短，重试...")
            time.sleep(random.randint(5, 10))
                
        except Exception as e:
            print(f"❌ 请求异常: {e}")
            time.sleep(5)
            
    return None

# ===========================
# 2. 颜色识别逻辑 (三重保险版)
# ===========================
def get_liturgical_emoji(cell_soup, row_soup, text_content):
    """
    判断礼仪颜色。优先级：
    1. HTML 标签中的 class/style (精确匹配)
    2. HTML 标签中的 Hex 颜色代码 (模糊匹配)
    3. 文本关键字 (保底策略)
    """
    text_content = text_content.strip()
    
    # 定义颜色特征库
    PATTERNS = {
        "🔴 ": ["red", "day_r", "#ff0000", "#f00", "殉道", "圣枝", "圣神", "受难"],
        "🟣 ": ["violet", "purple", "day_v", "day_p", "#800080", "四旬期", "将临期", "忏悔"],
        "🟢 ": ["green", "day_g", "#008000", "#00ff00", "常年期"],
        "⚪ ": ["white", "day_w", "#ffffff", "#fff", "圣诞", "复活", "圣母", "白"],
        "🟡 ": ["gold", "yellow", "day_y", "#ffd700"],
    }

    # 收集所有相关的 HTML 属性字符串
    check_pool = []
    
    # 1. 检查单元格及其子元素
    for tag in [cell_soup] + list(cell_soup.find_all(True)):
        cls = " ".join(tag.get('class', [])).lower()
        sty = str(tag.get('style', '')).lower()
        check_pool.append(f"{cls} {sty}")

    # 2. 检查整行
    if row_soup:
        r_cls = " ".join(row_soup.get('class', [])).lower()
        r_sty = str(row_soup.get('style', '')).lower()
        check_pool.append(f"{r_cls} {r_sty}")

    # 合并成一个大字符串进行匹配
    full_html_str = " | ".join(check_pool)

    # --- 匹配逻辑 ---
    
    # 策略 A: HTML 属性匹配 (最准)
    for emoji, keywords in PATTERNS.items():
        for kw in keywords:
            # 忽略中文关键字，只匹配英文代码
            if not re.search(r'[\u4e00-\u9fff]', kw): 
                if kw in full_html_str:
                    return emoji

    # 策略 B: 文本内容强制匹配 (补漏)
    # 如果 HTML 里没写颜色，但文字是 "四旬期"，那肯定是紫色
    for emoji, keywords in PATTERNS.items():
        for kw in keywords:
            if kw in text_content: # 匹配中文
                return emoji
            
    return ""

# ===========================
# 3. HTML 解析逻辑
# ===========================
def parse_html(html_content, target_year):
    soup = BeautifulSoup(html_content, 'html.parser')
    events_map = {}
    rows = soup.find_all('tr')
    
    if len(rows) < 10:
        print(f"❌ [{target_year}] 解析失败：页面无效。")
        return []

    print(f"🔍 [{target_year}] 扫描到 {len(rows)} 行，开始解析...")
    
    # 调试：打印前 3 行的 HTML 结构，看看颜色到底藏在哪
    print(f"   [调试] 第一行 HTML: {str(rows[1])[:200]}...")

    current_month = 1
    current_day = 0
    
    # 黑名单
    exclude_exact = [
        '星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日', '主日',
        '自*', '自', 'O', 'M', 'F', 'S', 'P', 'W', 'R', 'G', 'V', 'L', 'D', 'Lit.', 'Ordo',
        'I', 'II', 'III', 'IV', 'V'
    ]
    month_names = ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月']

    for row in rows:
        row_text = row.get_text(strip=True)
        
        # --- 日期定位 ---
        day_num = None
        date_match = re.search(r'(\d{1,2})\s*[月/]\s*(\d{1,2})', row_text)
        if date_match:
            try:
                m = int(date_match.group(1)); d = int(date_match.group(2))
                if 1 <= m <= 12 and 1 <= d <= 31: current_month = m; day_num = d
            except: pass
        
        if day_num is None:
            for cell in row.find_all(['td', 'th']):
                if cell.get_text(strip=True).isdigit():
                    d = int(cell.get_text(strip=True))
                    if 1 <= d <= 31:
                        if d == current_day + 1 or d == 1 or d == current_day: day_num = d; break

        if day_num is not None:
            if day_num < current_day and current_month < 12 and day_num == 1: current_month += 1
            current_day = day_num
        else:
            if current_day == 0: continue
            if row_text in month_names or "月" in row_text and len(row_text) < 4: continue
            if "星期" in row_text and "日期" in row_text: continue

        # --- 提取内容 ---
        for cell in row.find_all(['td', 'th']):
            cell_text = cell.get_text(strip=True, separator=' ')
            
            # 过滤
            if re.match(r'^[\d\s/-]+$', cell_text) or re.match(r'^\d+月\d+日$', cell_text): continue
            if cell_text in month_names or cell_text in exclude_exact: continue
            if "日期" in cell_text: continue
            if cell_text.replace('*', '').strip() in ['自', 'O', 'M']: continue
            if len(cell_text) < 2 and not re.search(r'[\u4e00-\u9fff]', cell_text): continue

            # 清洗文本
            clean_text = cell_text.replace('自*', '').replace('自 ', '').strip()
            clean_text = re.sub(r'^\d+\s*', '', clean_text)
            clean_text = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', clean_text) # 去除中文间空格

            if len(clean_text) > 1:
                # 获取颜色 (传入清洗后的文本用于辅助判断)
                emoji_prefix = get_liturgical_emoji(cell, row, clean_text)
                
                try:
                    dt = datetime(target_year, current_month, current_day)
                    if dt not in events_map: events_map[dt] = []
                    
                    final_text = f"{emoji_prefix}{clean_text}"
                    if final_text not in events_map[dt]:
                        events_map[dt].append(final_text)
                except ValueError: continue

    sorted_events = []
    for dt in sorted(events_map.keys()):
        full_summary = " | ".join(events_map[dt])
        sorted_events.append({'date': dt, 'summary': full_summary})

    print(f"✅ [{target_year}] 解析成功: {len(sorted_events)} 条数据")
    return sorted_events

# ===========================
# 4. 生成模块
# ===========================
def generate_ics(events, output_file, calendar_name, convert_to_simplified=False):
    cal = Calendar()
    cal.add('prodid', '-//GCatholic HK//mxm.io//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', calendar_name)
    cal.add('x-wr-timezone', 'Asia/Hong_Kong')
    
    for e in events:
        event = Event()
        summary = e['summary']
        if convert_to_simplified and zhconv: summary = zhconv.convert(summary, 'zh-cn')
        
        uid = hashlib.md5(f"{e['date']}{summary}".encode()).hexdigest() + "@gcatholic"
        event.add('summary', summary)
        event.add('dtstart', e['date'].date())
        event.add('dtend', (e['date'] + timedelta(days=1)).date())
        event.add('uid', uid)
        cal.add_component(event)

    with open(output_file, 'wb') as f: f.write(cal.to_ical())

if __name__ == "__main__":
    TASKS = [
        { "year": 2026, "url": "https://gcatholic.org/calendar/2026/HK-zt" },
        { "year": 2027, "url": "https://gcatholic.org/calendar/2027/General-D-zt" },
        { "year": 2028, "url": "https://gcatholic.org/calendar/2028/General-D-zt" },
        { "year": 2029, "url": "https://gcatholic.org/calendar/2029/General-D-zt" }
    ]
    
    master_events = []
    print("🚀 启动任务 (2026-2029) + 智能颜色识别...")
    
    for task in TASKS:
        if master_events: time.sleep(random.randint(5, 8))
        html = fetch_calendar_data(task['url'])
        if html:
            master_events.extend(parse_html(html, task['year']))
        else:
            print(f"⚠️ 跳过 {task['year']} 年")

    if master_events:
        master_events.sort(key=lambda x: x['date'])
        print(f"\n📊 总计: {len(master_events)} 条数据。正在生成...")
        generate_ics(master_events, "catholic_calendar_2026-2029.ics", "天主教礼仪日历 2026-2029")
        if zhconv:
            generate_ics(master_events, "catholic_calendar_2026-2029_cn.ics", "天主教礼仪日历 2026-2029 (简)", True)
        print("🎉 完成！")
    else:
        print("❌ 失败：无数据。")
        sys.exit(1)
