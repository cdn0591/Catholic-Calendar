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
            
            page_title = ""
            try:
                soup_check = BeautifulSoup(response.text[:5000], 'html.parser')
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

def parse_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    events = []
    
    # 获取所有表格单元格
    cells = soup.find_all('td')
    print(f"🔍 扫描到 {len(cells)} 个单元格，开始按视觉顺序解析...")
    
    # 调试：打印前几个包含链接的单元格内容，帮助诊断
    debug_count = 0
    for cell in cells[:50]:
        if cell.find('a'):
            debug_count += 1
            if debug_count <= 3:
                print(f"   [调试样本] {cell.get_text(strip=True)[:30]}...")

    current_month = 1
    current_day = 0
    year = 2026
    
    for cell in cells:
        # 获取所有文本
        text = cell.get_text(strip=True)
        if not text:
            continue

        # 1. 提取日期数字
        # 策略：寻找开头的一到两位数字。
        # 兼容 "1", "01", "1日", "1月" 等格式
        day_match = re.match(r'^(\d{1,2})', text)
        
        # 备选：有时候数字被包在 div 里，不在开头
        if not day_match:
             # 找 cell 内部是否有专门的日期类
             day_num_tag = cell.find(class_=re.compile(r'day|date|num', re.I))
             if day_num_tag:
                 day_match = re.search(r'(\d{1,2})', day_num_tag.get_text())
        
        # 如果还是没找到，尝试在纯文本里找单独的数字
        if not day_match:
            # 查找独立的数字，前后不是字母或数字
            # 在中文里 \b 不好用，所以我们用简单的查找
            nums = re.findall(r'\d+', text)
            if nums:
                # 假设日历格子里第一个数字就是日期
                possible_day = int(nums[0])
                if 1 <= possible_day <= 31:
                    # 验证逻辑：必须是递增的，或者是下个月的1号
                    if possible_day == current_day + 1 or (possible_day == 1 and current_day >= 28):
                        day_match = re.match(r'()', '') # 伪造一个 match 对象
                        matched_day = possible_day
                    else:
                        # 可能是干扰数字（如年份2026），跳过
                        pass

        if not day_match and 'matched_day' not in locals():
            continue
            
        # 确定日期
        if 'matched_day' in locals():
            d = matched_day
            del matched_day # 重置
        else:
            d = int(day_match.group(1))

        # 2. 逻辑校验与月份切换
        if d > 31 or d < 1:
            continue
            
        # 关键逻辑：如果日期变小（如从31变回1），说明进入下个月
        if d < current_day:
            current_month += 1
            if current_month > 12:
                break # 防止溢出到下一年
        
        # 如果日期跳跃太大（如1号直接变10号），可能是读错了，忽略
        if d > current_day + 1 and not (d == 1 and current_day == 0):
             # 允许少量跳跃（日历空白格），但通常日历td是连续的
             pass

        current_day = d
        
        # 3. 提取节日内容
        # 查找格子里所有的链接文本
        links = cell.find_all('a')
        day_summaries = []
        
        for link in links:
            t = link.get_text(strip=True)
            # 过滤掉纯数字、无意义短词
            if (len(t) > 1 and 
                not t.isdigit() and 
                t not in ['Ordo', 'Mass', 'Readings', 'W', 'R', 'G', 'V', 'P', 'D', 'L']):
                day_summaries.append(t)
        
        # 如果没有链接，尝试找 span
        if not day_summaries:
             spans = cell.find_all('span')
             for span in spans:
                 t = span.get_text(strip=True)
                 if len(t) > 1 and not t.isdigit():
                     day_summaries.append(t)

        # 4. 保存
        if day_summaries:
            try:
                dt = datetime(year, current_month, d)
                for summary in day_summaries:
                    # 去重
                    is_duplicate = False
                    for existing in events:
                        if existing['date'] == dt and existing['summary'] == summary:
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        events.append({'date': dt, 'summary': summary})
            except ValueError:
                continue

    print(f"✅ 从表格中解析出 {len(events)} 条数据")
    return events

def generate_ics(events, output_file):
    cal = Calendar()
    cal.add('prodid', '-//GCatholic HK//mxm.io//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', '天主教香港教区礼仪日历 2026')
    cal.add('x-wr-timezone', 'Asia/Hong_Kong')
    
    if not events:
        print("⚠️ 警告：没有抓取到任何事件")
        event = Event()
        event.add('summary', '暂无数据 - 请检查 GitHub Actions 日志')
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
    
    html = fetch_calendar_data(TARGET_URL)
    
    if html:
        extracted_events = parse_html(html)
        generate_ics(extracted_events, OUTPUT_PATH)
        print(f"🎉 文件已生成: {OUTPUT_PATH}")
    else:
        print("❌ 无法获取网页")
        generate_ics([], OUTPUT_PATH)
