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

# ===========================
# 1. 增强型网络请求模块
# ===========================
def fetch_calendar_data(url):
    # 使用 Session 可以在多次重试中保持 Cookies，有助于绕过简单的 Cloudflare 检查
    session = requests.Session()
    
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    ]
    
    max_retries = 5
    
    for attempt in range(max_retries):
        try:
            print(f"🔄 [尝试 {attempt + 1}/{max_retries}] 连接: {url} ...")
            headers = {
                'User-Agent': random.choice(user_agents),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
                'Referer': 'https://www.google.com/',
                'Cache-Control': 'max-age=0',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Ch-Ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"'
            }
            
            response = session.get(url, headers=headers, timeout=45)
            response.encoding = 'utf-8'
            
            # --- 关键校验步骤 ---
            # 1. 获取网页标题进行诊断
            page_title = "未知标题"
            try:
                soup_check = BeautifulSoup(response.text[:5000], 'html.parser')
                if soup_check.title:
                    page_title = soup_check.title.string.strip()
            except: pass
            
            print(f"   📄 状态码: {response.status_code} | 标题: {page_title}")

            # 2. 检查是否为有效日历页面
            # 有效页面通常包含 "Diocese" 字样或大量的 "tr" 标签，或者 table
            is_blocked = False
            if "Just a moment" in page_title or "Security" in page_title or "Cloudflare" in page_title:
                is_blocked = True
            
            if response.status_code == 200 and not is_blocked:
                # 进一步检查内容长度，防止空白页
                if len(response.text) > 1000:
                    return response.text
                else:
                    print("   ⚠️ 警告: 页面内容过短，可能加载失败。")
            else:
                print("   ⚠️ 警告: 检测到拦截页面，准备重试...")

            # 失败后等待
            wait_time = 5 + (attempt * 3) + random.random() * 5 # 递增等待 5s, 8s, 11s...
            print(f"   ⏳ 等待 {wait_time:.1f} 秒后重试...")
            time.sleep(wait_time)
                
        except Exception as e:
            print(f"❌ 请求异常: {e}")
            time.sleep(5)
            
    print("❌ 所有重试均失败，放弃此链接。")
    return None

# ===========================
# 2. 颜色识别与 Emoji
# ===========================
def get_liturgical_emoji(cell_soup):
    """
    扫描单元格内部标签的 class 和 style 属性，
    判断礼仪颜色并返回对应的 Emoji。
    """
    for tag in cell_soup.find_all(True):
        classes = " ".join(tag.get('class', [])).lower()
        style = str(tag.get('style', '')).lower()
        check_str = f"{classes} {style}"
        
        if 'green' in check_str: return "🟢 "
        elif 'violet' in check_str or 'purple' in check_str: return "🟣 "
        elif 'red' in check_str: return "🔴 "
        elif 'white' in check_str: return "⚪ "
        elif 'gold' in check_str or 'yellow' in check_str: return "🟡 "
            
    return ""

# ===========================
# 3. HTML 解析逻辑
# ===========================
def parse_html(html_content, target_year):
    soup = BeautifulSoup(html_content, 'html.parser')
    events_map = {}
    
    rows = soup.find_all('tr')
    
    # === 如果这里是 0，说明 fetch 到的页面不对 ===
    if len(rows) == 0:
        print(f"❌ [{target_year}] 严重错误: 页面源代码中未发现表格行 (tr)。")
        # 尝试打印部分源码以供调试 (可选)
        # print(html_content[:500])
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
            
            if re.match(r'^[\d\s/-]+$', cell_text) or re.match(r'^\d+月\d+日$', cell_text): continue
            if cell_text in month_names: continue
            if cell_text in exclude_exact_match: continue
            if any(k in cell_text for k in exclude_keywords_partial): continue
            if cell_text.replace('*', '').strip() in ['自', 'O', 'M']: continue
            if len(cell_text) < 2 and not re.search(r'[\u4e00-\u9fff]', cell_text): continue

            # 获取颜色
            emoji_prefix = get_liturgical_emoji(cell)

            # 清洗
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

    print(f"✅ [{target_year}] 解析完成，共提取 {len(sorted_events)} 天的数据")
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
    
    if not events:
        event = Event()
        event.add('summary', '暂无数据 - 抓取失败')
        event.add('dtstart', datetime(year, 1, 1).date())
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
    TASKS = [
        { "year": 2026, "url": "https://gcatholic.org/calendar/2026/HK-zt" },
        { "year": 2027, "url": "https://gcatholic.org/calendar/2027/General-D-zt" },
        { "year": 2028, "url": "https://gcatholic.org/calendar/2028/General-D-zt" },
        { "year": 2029, "url": "https://gcatholic.org/calendar/2029/General-D-zt" }
    ]
    
    master_events = []

    print("🚀 启动批量抓取任务 (2026-2029) + 颜色识别...")
    print("ℹ️ 提示: 如果日志显示 '标题: Just a moment...'，说明正在重试绕过反爬虫。")
    
    for task in TASKS:
        # 在任务之间添加随机延迟，减少连续请求被封的概率
        if master_events: 
            sleep_time = random.randint(3, 8)
            print(f"😴 休息 {sleep_time} 秒...")
            time.sleep(sleep_time)

        html = fetch_calendar_data(task['url'])
        if html:
            extracted_events = parse_html(html, task['year'])
            if extracted_events:
                master_events.extend(extracted_events)
            else:
                print(f"⚠️ 警告: {task['year']} 年虽然连接成功但未提取到数据。")
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
