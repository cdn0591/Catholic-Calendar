import cloudscraper
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime, timezone, timedelta
from lunarcalendar import Converter, Solar
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
            
            if response.status_code == 200 and len(response.text) > 2000:
                return response.text
            
            print(f"   ⚠️ 状态码 {response.status_code} 或内容过短，重试...")
            time.sleep(random.randint(5, 10))
                
        except Exception as e:
            print(f"❌ 请求异常: {e}")
            time.sleep(5)
            
    return None

# ===========================
# 2. 颜色识别逻辑
# ===========================
def get_liturgical_emoji(cell_soup, row_soup, text_content):
    text_content = text_content.strip()
    
    if "追思已亡" in text_content: return "🟣⚫⚪ "
    
    PATTERNS = [
        ("🔴 ", ["red", "day_r", "#ff0000", "#f00", "殉道", "圣枝", "聖枝", "圣神", "聖神", "受难", "受難"]),
        ("🟣 ", ["violet", "purple", "day_v", "day_p", "#800080", "四旬期", "将临期", "將臨期", "忏悔", "懺悔"]),
        ("🟢 ", ["green", "day_g", "#008000", "#00ff00", "常年期"]),
        ("⚫ ", ["black", "day_b", "#000000", "#000"]),
        ("⚪ ", ["white", "day_w", "#ffffff", "#fff", "圣诞", "聖誕", "复活", "復活", "圣母", "聖母", "白", "诸圣", "諸聖", "献主", "獻主", "耶稣升天"]),
        ("🟡 ", ["gold", "yellow", "day_y", "#ffd700"]),
    ]
    
    WEAK_WHITE_KEYWORDS = ["纪", "紀", "庆", "慶", "圣", "聖"]

    check_pool = []
    for tag in [cell_soup] + list(cell_soup.find_all(True)):
        cls = " ".join(tag.get('class', [])).lower()
        sty = str(tag.get('style', '')).lower()
        check_pool.append(f"{cls} {sty}")

    if row_soup:
        r_cls = " ".join(row_soup.get('class', [])).lower()
        r_sty = str(row_soup.get('style', '')).lower()
        check_pool.append(f"{r_cls} {r_sty}")

    full_html_str = " | ".join(check_pool)
    found_emojis = []

    for emoji, keywords in PATTERNS:
        for kw in keywords:
            if not re.search(r'[\u4e00-\u9fff]', kw): 
                if kw in full_html_str:
                    if emoji not in found_emojis: found_emojis.append(emoji)
                    break 

    for emoji, keywords in PATTERNS:
        if emoji in found_emojis: continue 
        for kw in keywords:
            if re.search(r'[\u4e00-\u9fff]', kw):
                if kw in text_content:
                    found_emojis.append(emoji)
                    break

    if not found_emojis:
        for kw in WEAK_WHITE_KEYWORDS:
            if kw in text_content: return "⚪ "
    
    return "".join(found_emojis)

# ===========================
# 3. HTML 解析逻辑
# ===========================
def parse_html(html_content, target_year):
    soup = BeautifulSoup(html_content, 'html.parser')
    local_events = [] 
    rows = soup.find_all('tr')
    
    if len(rows) < 10:
        print(f"❌ [{target_year}] 解析失败：页面无效。")
        return []

    print(f"🔍 [{target_year}] 扫描到 {len(rows)} 行，开始解析...")

    current_month = 1
    current_day = 0
    
    exclude_exact = [
        '星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日', '主日',
        '自*', '自', 'O', 'M', 'F', 'S', 'P', 'W', 'R', 'G', 'V', 'L', 'D', 'Lit.', 'Ordo',
        'I', 'II', 'III', 'IV', 'V'
    ]
    month_names = ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月']

    for row in rows:
        row_text = row.get_text(strip=True)
        
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

        for cell in row.find_all(['td', 'th']):
            cell_text = cell.get_text(strip=True, separator=' ')
            
            if re.match(r'^[\d\s/-]+$', cell_text) or re.match(r'^\d+月\d+日$', cell_text): continue
            if cell_text in month_names or cell_text in exclude_exact: continue
            if "日期" in cell_text: continue
            if cell_text.replace('*', '').strip() in ['自', 'O', 'M']: continue
            if len(cell_text) < 2 and not re.search(r'[\u4e00-\u9fff]', cell_text): continue

            clean_text = cell_text.replace('自*', '').replace('自 ', '').strip()
            clean_text = re.sub(r'^\d+\s*', '', clean_text)
            
            # 标点紧凑化
            clean_text = clean_text.replace('（', '(').replace('）', ')')
            for char in ['、', '，', '。', '．', '・', '‧', '･']:
                clean_text = clean_text.replace(char, '.')
            clean_text = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', clean_text)
            clean_text = re.sub(r'\s*\.\s*', '.', clean_text)
            clean_text = re.sub(r'\s*\(\s*', '(', clean_text)
            clean_text = re.sub(r'\s*\)\s*', ')', clean_text)

            # === 核心修改：移除 "圣灰礼仪后" 相关文字 ===
            # 只要包含 "灰禮儀後" 或 "灰礼仪后"，就直接跳过该文本，不添加到日历中
            if '灰禮儀後' in clean_text or '灰礼仪后' in clean_text:
                continue

            if len(clean_text) > 1:
                emoji_prefix = get_liturgical_emoji(cell, row, clean_text)
                try:
                    dt = datetime(target_year, current_month, current_day)
                    final_text = f"{emoji_prefix}{clean_text}"
                    local_events.append({'date': dt, 'summary': final_text})
                except ValueError: continue

    print(f"✅ [{target_year}] 初步解析: {len(local_events)} 条记录")
    return local_events

# ===========================
# 4. 规则后处理 (农历与斋戒)
# ===========================
def process_special_rules(raw_events):
    processed_map = {}
    
    # 归档
    for e in raw_events:
        dt = e['date']
        if dt not in processed_map: processed_map[dt] = []
        if e['summary'] not in processed_map[dt]:
            processed_map[dt].append(e['summary'])

    sorted_dates = sorted(processed_map.keys())
    final_events = []

    for dt in sorted_dates:
        events_list = processed_map[dt]
        combined_text = " ".join(events_list) 
        
        # --- A. 农历计算 ---
        solar = Solar(dt.year, dt.month, dt.day)
        lunar = Converter.Solar2Lunar(solar)
        # 农历正月(1月) 初一(1) 到 十五(15) 豁免
        is_lny_exempt = (lunar.month == 1 and 1 <= lunar.day <= 15)
        
        # --- B. 每月敬礼 ---
        # 使用繁体以保持一致性 (生成简体版时会自动转换)
        month_label = ""
        if dt.day == 1:
            if dt.month == 2: month_label = "聖神月"
            elif dt.month == 3: month_label = "聖若瑟月"
            elif dt.month == 5: month_label = "聖母月"
            elif dt.month == 6: month_label = "聖心月"
            elif dt.month == 10: month_label = "玫瑰月"
            elif dt.month == 11: month_label = "煉靈月"
        
        if month_label:
            events_list.append(month_label)

        # --- C. 斋戒规则 ---
        # 关键词匹配
        is_ash_wednesday = any(x in combined_text for x in ["聖灰禮儀", "圣灰礼仪"])
        is_good_friday = any(x in combined_text for x in ["耶穌受難日", "耶稣受难日", "救主受難"])
        is_friday = (dt.weekday() == 4) # 星期五

        fasting_tag = ""
        
        # 优先级 1: 大小斋 (圣灰 or 受难)
        # 注意：因为parse_html已经删除了"圣灰礼仪后..."，所以这里只会匹配真正的圣灰礼仪日
        if is_ash_wednesday or is_good_friday:
            if is_lny_exempt:
                fasting_tag = "免大小齋"
            else:
                fasting_tag = "大小齋"
        # 优先级 2: 小斋 (星期五)
        elif is_friday:
            if is_lny_exempt:
                fasting_tag = "免小齋"
            else:
                fasting_tag = "小齋"
        
        if fasting_tag:
            events_list.append(fasting_tag)

        # 重新打包
        full_summary = " | ".join(events_list)
        final_events.append({'date': dt, 'summary': full_summary})
        
    return final_events

# ===========================
# 5. 生成模块
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
    
    all_raw_events = []
    print("🚀 启动任务 (2026-2029) + 农历豁免 + 移除圣灰后...")
    
    for task in TASKS:
        if all_raw_events: time.sleep(random.randint(5, 8))
        html = fetch_calendar_data(task['url'])
        if html:
            all_raw_events.extend(parse_html(html, task['year']))
        else:
            print(f"⚠️ 跳过 {task['year']} 年")

    if all_raw_events:
        processed_events = process_special_rules(all_raw_events)
        
        print(f"\n📊 总计: {len(processed_events)} 天数据。正在生成...")
        generate_ics(processed_events, "catholic_calendar_2026-2029.ics", "天主教礼仪日历 2026-2029")
        if zhconv:
            generate_ics(processed_events, "catholic_calendar_2026-2029_cn.ics", "天主教礼仪日历 2026-2029 (简)", True)
        print("🎉 完成！")
    else:
        print("❌ 失败：无数据。")
        sys.exit(1)
