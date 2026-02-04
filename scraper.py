import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime, timezone, timedelta
import re
import hashlib
import time
import random

def fetch_calendar_data(url):
    # 使用更丰富的 Header 列表轮换，模拟真实用户
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
    ]
    
    # 重试 3 次
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
            
            # 检查是否被拦截
            page_title = ""
            try:
                soup_check = BeautifulSoup(response.text[:5000], 'html.parser')
                page_title = soup_check.title.string.strip() if soup_check.title else ""
            except:
                pass

            print(f"📄 状态码: {response.status_code} | 标题: {page_title}")
            
            if "Just a moment" in page_title or "Security" in page_title or "Cloudflare" in page_title:
                print("⚠️ 检测到反爬虫拦截，等待后重试...")
                time.sleep(10 + random.random() * 5) # 等待 10-15 秒
                continue
                
            if response.status_code == 200 and len(response.text) > 1000:
                return response.text
                
        except Exception as e:
            print(f"❌ 请求异常: {e}")
            time.sleep(5)
            
    print("❌ 所有重试均失败。")
    return None

def parse_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    events = []
    
    # 策略：扫描所有表格单元格
    # 逻辑：
    # 1. 找到包含数字（日期）和链接（节日）的格子
    # 2. 顺序遍历。如果数字变小（例如从 31 变成 1），说明进入了下一个月。
    # 3. 初始月份设为 1 月。
    
    current_month = 1
    last_day = 0
    year = 2026
    
    # 查找所有 TD (表格单元格)
    cells = soup.find_all('td')
    print(f"🔍 扫描到 {len(cells)} 个表格单元格，开始解析日期...")

    valid_event_count = 0

    for cell in cells:
        try:
            cell_text = cell.get_text(separator=' ').strip()
            
            # 1. 尝试在格子里找“日期数字”
            # 匹配开头或结尾的独立数字，或者类名为 dayNum 的元素
            day_num = None
            
            # 方法A: 找特定类名
            num_tag = cell.find(class_=re.compile(r'day|date|num', re.I))
            if num_tag:
                match = re.search(r'\d+', num_tag.get_text())
                if match: day_num = int(match.group())
            
            # 方法B: 如果没找到，尝试在整个格子文本里找独立数字
            if day_num is None:
                # 寻找形如 "1" 或 "15" 这样的独立数字
                # 排除像 "2026" 这样的年份
                matches = re.findall(r'\b(\d{1,2})\b', cell_text)
                for m in matches:
                    d = int(m)
                    if 1 <= d <= 31:
                        # 简单的上下文判断：如果是日历，数字通常在开头
                        day_num = d
                        break
            
            if day_num is None:
                continue

            # 2. 逻辑判断月份递增
            # 如果日期突然变小（例如从 31 变成 1），说明换月了
            if day_num < last_day:
                current_month += 1
                if current_month > 12: break # 防止溢出
            
            last_day = day_num
            
            # 3. 提取活动文本
            # 查找该格子内的所有链接
            links = cell.find_all('a')
            day_events = []
            
            for link in links:
                text = link.get_text(strip=True)
                # 过滤垃圾词
                if (len(text) > 1 and 
                    not text.isdigit() and 
                    text not in ['Ordo', 'Mass', 'Readings', 'W', 'R', 'G', 'V', 'P', 'D', 'L']):
                    day_events.append(text)
            
            # 如果没有链接，尝试找 span 里的文本
            if not day_events:
                spans = cell.find_all('span', class_=re.compile(r'tit|ev|cl'))
                for span in spans:
                    text = span.get_text(strip=True)
                    if len(text) > 1: day_events.append(text)

            # 4. 保存结果
            if day_events:
                try:
                    dt = datetime(year, current_month, day_num)
                    for summary in day_events:
                        events.append({'date': dt, 'summary': summary})
                        valid_event_count += 1
                except ValueError:
                    # 处理无效日期（如 2月30日）
                    continue

        except Exception:
            continue
            
    return events

def generate_ics(events, output_file):
    cal = Calendar()
    cal.add('prodid', '-//GCatholic HK//mxm.io//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', '天主教香港教区礼仪日历 2026')
    cal.add('x-wr-timezone', 'Asia/Hong_Kong')
    
    if not events:
        event = Event()
        event.add('summary', '暂无数据 (请检查 GitHub Actions 日志)')
        event.add('dtstart', datetime(2026, 1, 1).date())
        cal.add_component(event)
    else:
        for e in events:
            event = Event()
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
    
    print("🚀 启动抓取任务...")
    html = fetch_calendar_data(TARGET_URL)
    
    if html:
        extracted_events = parse_html(html)
        print(f"✅ 成功提取: {len(extracted_events)} 条活动")
        generate_ics(extracted_events, OUTPUT_PATH)
    else:
        print("❌ 获取 HTML 失败，生成占位文件。")
        generate_ics([], OUTPUT_PATH)
