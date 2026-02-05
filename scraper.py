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
# 1. 网络请求模块 (保持 Cloudscraper 不变)
# ===========================
def fetch_calendar_data(url):
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            print(f"🔄 [尝试 {attempt + 1}/{max_retries}] 连接: {url} ...")
            response = scraper.get(url, timeout=60)
            response.encoding = 'utf-8'
            
            page_title = "未知标题"
            try:
                soup_check = BeautifulSoup(response.text[:5000], 'html.parser')
                if soup_check.title:
                    page_title = soup_check.title.string.strip()
            except: pass
            
            print(f"   📄 状态码: {response.status_code} | 标题: {page_title}")

            if "Just a moment" in page_title or "Security" in page_title:
                print("   ⚠️ 遇到验证页，等待重试...")
            elif response.status_code == 200 and len(response.text) > 5000:
                return response.text
            else:
                print("   ⚠️ 内容过短或状态异常")

            time.sleep(random.randint(5, 10))
                
        except Exception as e:
            print(f"❌ 请求异常: {e}")
            time.sleep(5)
            
    return None

# ===========================
# 2. 颜色识别逻辑 (核心修复)
# ===========================
def get_liturgical_emoji(cell_soup, row_soup):
    """
    判断礼仪颜色。
    策略：
    1. 优先检查单元格(td)及其子元素(span/b/a)的 class/style (特定节日颜色)
    2. 如果没找到，检查行(tr)的 class (季节颜色，如四旬期紫色)
    """
    
    # 辅助函数：从 class 列表或 style 字符串中推断颜色
    def check_color(classes, style):
        s = f"{' '.join(classes).lower()} {style.lower()}"
        
        # GCatholic 特有类名匹配
        if 'day_r' in s or 'red' in s: return "🔴 "
        if 'day_v' in s or 'day_p' in s or 'violet' in s or 'purple' in s: return "🟣 "
        if 'day_g' in s or 'green' in s: return "🟢 "
        if 'day_w' in s or 'white' in s: return "⚪ "
        if 'day_y' in s or 'gold' in s or 'yellow' in s: return "🟡 "
        return None

    # 1. 检查单元格内部 (Override)
    # 遍历 cell 自身和所有子节点
    for tag in [cell_soup] + list(cell_soup.find_all(True)):
        color = check_color(tag.get('class', []), str(tag.get('style', '')))
        if color: return color

    # 2. 检查整行 (Fallback)
    # 很多时候 "四旬期" 的紫色是定义在 <tr> 上的
    if row_soup:
        color = check_color(row_soup.get('class', []), str(row_soup.get('style', '')))
        if color: return color
            
    return ""

# ===========================
# 3. HTML 解析逻辑
# ===========================
def parse_html(html_content, target_year):
    soup = BeautifulSoup(html_content, 'html.parser')
    events_map = {}
    
    rows = soup.find_all('tr')
    if len(rows) < 10:
        print(f"❌ [{target_year}] 解析失败：未发现有效表格数据。")
        return []

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
        
        # --- 日期定位 ---
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

        # --- 提取内容 ---
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

            # === 获取颜色 (传递 row 对象) ===
            emoji_prefix = get_liturgical_emoji(cell, row)

            # 文本清洗
            clean_text = cell_text.replace('自*', '').replace('自 ', '').strip()
            clean_text = re.sub(r'^\d+\s*', '', clean_text)
            clean_text = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', clean_text)

            if len(clean_text) > 1:
                try:
                    dt = datetime(year, current_month, current_day)
                    if dt not in events_map:
                        events_map[dt] = []
                    
                    final_text = f"{emoji_prefix}{clean_text}"
                    
                    if final_text not in events_map[dt]:
                        events_map[dt].append(final_text)
                except ValueError:
                    continue

    sorted_events = []
    for dt in sorted(events_map.keys()):
        full_summary = " | ".join(events_map[dt])
        sorted_events.append({'date': dt, 'summary': full_summary})

    print(f"✅ [{target_year}] 解析成功: {len(sorted_events)} 条数据")
    return sorted_events

# ===========================
# 4. 生成 ICS 文件
# ===========================
def generate_ics(events, output_file, calendar_name, year, convert_to_simplified=False):
    cal = Calendar()
    cal.add('prodid', '-//GCatholic HK//mxm.io//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', calendar_name)
    cal.add('x-wr-timezone', 'Asia/Hong_Kong')
    
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
    TASKS = [
        { "year": 2026, "url": "https://gcatholic.org/calendar/2026/HK-zt" },
        { "year": 2027, "url": "https://gcatholic.org/calendar/2027/General-D-zt" },
        { "year": 2028, "url": "https://gcatholic.org/calendar/2028/General-D-zt" },
        { "year": 2029, "url": "https://gcatholic.org/calendar/2029/General-D-zt" }
    ]
    
    master_events = []
    print("🚀 启动批量抓取任务 (2026-2029) [增强颜色识别]...")
    
    for task in TASKS:
        if master_events: time.sleep(random.randint(5, 10))

        html = fetch_calendar_data(task['url'])
        if html:
            extracted_events = parse_html(html, task['year'])
            if extracted_events:
                master_events.extend(extracted_events)
            else:
                print(f"⚠️ {task['year']} 年未提取到数据。")
        else:
            print(f"❌ {task['year']} 年连接失败。")

    if not master_events:
        print("❌ 致命错误: 无数据生成。")
        sys.exit(1)

    master_events.sort(key=lambda x: x['date'])
    print(f"\n📊 总计: {len(master_events)} 条数据。正在生成文件...")

    generate_ics(master_events, "catholic_calendar_2026-2029.ics", "天主教礼仪日历 2026-2029", 2026)
    
    if zhconv:
        generate_ics(master_events, "catholic_calendar_2026-2029_cn.ics", "天主教礼仪日历 2026-2029 (简)", 2026, convert_to_simplified=True)
    
    print("🎉 任务完成！")
