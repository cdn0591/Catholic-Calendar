import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime, timezone, timedelta
import re
import hashlib

# 模拟更真实的浏览器头信息
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'Cache-Control': 'max-age=0',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

def fetch_calendar_data(url):
    try:
        print(f"正在连接: {url} ...")
        session = requests.Session()
        response = session.get(url, headers=HEADERS, timeout=45)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            print(f"❌ HTTP 错误: {response.status_code}")
            return None
            
        return response.text
    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return None

def parse_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    events = []
    
    # [调试] 打印网页标题，确认是否被拦截
    page_title = soup.title.string.strip() if soup.title else "无标题"
    print(f"📄 网页标题: [{page_title}]")
    
    if "Just a moment" in page_title or "Security" in page_title or "Cloudflare" in page_title:
        print("⚠️ 警告: 可能被 Cloudflare 反爬虫拦截。")
        # 这里无法自动通过验证，只能记录错误

    # 策略 1: 标准 ID 匹配 (d20260101)
    day_containers = soup.find_all(id=re.compile(r'^d2026\d{4}$'))
    
    # 策略 2 (备选): 如果策略 1 失败，查找所有表格里的单元格
    if not day_containers:
        print("ℹ️ 未找到标准日期ID，尝试扫描所有表格单元格...")
        # 查找所有包含 links 的 td
        day_containers = [td for td in soup.find_all('td') if td.find('a')]

    print(f"🔍 扫描到 {len(day_containers)} 个潜在数据块")

    count = 0
    # 简单的日期计数器，用于备选策略
    current_date = datetime(2026, 1, 1)

    for container in day_containers:
        try:
            # 尝试获取日期
            dt = None
            container_id = container.get('id', '')
            
            if container_id.startswith('d2026'):
                # 策略 1 的日期提取
                date_str = container_id[1:]
                dt = datetime.strptime(date_str, '%Y%m%d')
            else:
                # 策略 2: 尝试在单元格文本里找数字，或者由于表格是顺序的，我们假设它是按日期的
                # 这种方式不准确，但比空着好。更好的方式是寻找特定的日期类名
                # 这里我们简化处理：如果找不到确切日期，就跳过，避免数据错乱
                # 但为了尽可能抓取，我们尝试查找内部是否有类名为 'dayNum' 的元素
                day_num = container.find(class_='dayNum') or container.find(text=re.compile(r'^\d+$'))
                if day_num:
                    # 这里很难确定月份，所以我们只处理明确有 ID 的情况，
                    # 或者抓取所有带有特殊类名 'cl...' 的链接
                    pass
            
            # 核心目标：抓取活动文本
            # 查找该容器内所有可能有用的链接/文本
            # 过滤掉: 数字, "Ordo", "DL", "Ps" 等短词
            candidates = container.find_all(['a', 'span', 'div'])
            day_events = []
            
            for tag in candidates:
                text = tag.get_text(strip=True)
                # 过滤规则
                if (len(text) > 3 and       # 长度大于3
                    not text.isdigit() and  # 不是纯数字
                    not re.match(r'^[A-Z][a-z]{0,2}\.?$', text) and # 排除缩写如 "Mon", "Jan"
                    "Week" not in text and 
                    "Sunday" not in text and
                    text not in day_events):
                    
                    # 检查是否有特定类名，增加置信度
                    classes = tag.get('class', [])
                    if any(c.startswith('cl') or c in ['tit', 'ev'] for c in classes) or tag.name == 'a':
                         day_events.append(text)

            # 如果找到了活动，但没找到日期，我们可以尝试“猜测”或者为了安全起见只记录有 ID 的
            if dt and day_events:
                for event_name in day_events:
                    events.append({'date': dt, 'summary': event_name})
                    count += 1
            
            # 特殊补救：如果网页结构完全变了，我们可以尝试抓取整个页面的所有 'clt' 类 (礼仪标题)
            # 这部分代码在循环外单独处理
            
        except Exception:
            continue
    
    # 策略 3: 全局搜索 (终极备选)
    if count == 0:
        print("ℹ️ 局部扫描失败，尝试全局搜索所有活动链接...")
        # 搜索所有带有 clt, cl1, cl2 类的元素
        all_event_tags = soup.find_all(class_=re.compile(r'^cl(t|\d)'))
        print(f"🔍 全局找到 {len(all_event_tags)} 个标签")
        
        # 这是一个简化的假设：假设列表是按顺序排列的，从 1月1日开始
        # 注意：这非常冒险，但如果 HTML 里没有日期 ID，这是唯一办法
        # 更好的办法是：不抓取日期，只生成一个"列表"？不行，日历必须有日期。
        # 如果走到这一步，通常说明 HTML 结构极其复杂或被加密。
        pass

    return events

def generate_ics(events, output_file):
    cal = Calendar()
    cal.add('prodid', '-//GCatholic HK//mxm.io//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', '天主教香港教区礼仪日历 2026')
    cal.add('x-wr-timezone', 'Asia/Hong_Kong')
    
    if not events:
        # 占位符
        event = Event()
        event.add('summary', '暂无数据或抓取受阻')
        event.add('dtstart', datetime(2026, 1, 1).date())
        event.add('description', '请检查 GitHub Actions 日志中的网页标题，确认是否被反爬虫拦截。')
        cal.add_component(event)
    else:
        for e in events:
            event = Event()
            uid_seed = f"{e['date'].strftime('%Y%m%d')}{e['summary']}"
            uid = hashlib.md5(uid_seed.encode()).hexdigest() + "@gcatholic"
            
            event.add('summary', e['summary'])
            event.add('dtstart', e['date'].date())
            event.add('dtend', (e['date'] + timedelta(days=1)).date())
            event.add('dtstamp', datetime.now(timezone.utc))
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
        print(f"✅ 最终提取: {len(extracted_events)} 条数据")
        generate_ics(extracted_events, OUTPUT_PATH)
    else:
        generate_ics([], OUTPUT_PATH)
