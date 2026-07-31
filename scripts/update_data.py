"""
GitHub Actions 数据更新脚本
每天自动抓取最新1000期数据，生成 all_draws.js

修复：多 API 端点 + 备用网页爬虫 + 容错机制
"""
import json
import os
import re
import sys
import time
import ssl
import urllib.request
import urllib.error
import urllib.parse
from html.parser import HTMLParser

PROXY = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
if PROXY:
    print(f"  使用代理: {PROXY}")

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# 多个 API 端点（优先 HTTPS，再 HTTP）
API_ENDPOINTS = [
    "https://webapi.sporttery.cn/gateway/lottery/",
    "http://webapi.sporttery.cn/gateway/lottery/",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.lottery.gov.cn/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}
PERIOD = 1000
PAGE_SIZE = 30
OUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _http_get(url, headers, timeout=60):
    """使用 urllib 直接发起 HTTP/HTTPS 请求（跳过 SSL 验证）"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _try_requests_get(url, params, headers, timeout=60):
    """使用 requests 发起请求"""
    kwargs = {
        "headers": headers,
        "timeout": timeout,
        "verify": False,
    }
    if PROXY:
        kwargs["proxies"] = {"http": PROXY, "https": PROXY}
    if params:
        kwargs["params"] = params
    resp = requests.get(url, **kwargs)
    resp.raise_for_status()
    return resp.json()


# ============ 方式一：API 接口 ============

def fetch_page_via_api(page_no, timeout=60):
    """通过官方 API 接口获取单页数据"""
    params = {
        "gameNo": "85",
        "provinceId": "0",
        "pageSize": str(PAGE_SIZE),
        "isVerify": "1",
        "pageNo": str(page_no),
    }

    last_error = None
    for base_url in API_ENDPOINTS:
        try:
            full_url = base_url + "getHistoryPageListV1.qry"
            print(f"      尝试: {full_url[:50]}...")
            if HAS_REQUESTS:
                data = _try_requests_get(full_url, params, HEADERS, timeout)
            else:
                query = urllib.parse.urlencode(params)
                raw = _http_get(full_url + "?" + query, HEADERS, timeout)
                data = json.loads(raw)

            if data.get("success"):
                return data["value"]["list"]
            else:
                last_error = Exception(data.get("errorMessage", "API error"))
                print(f"      API 错误: {data.get('errorMessage')}")
        except Exception as e:
            last_error = e
            print(f"      失败: {type(e).__name__}: {str(e)[:80]}")
            continue

    raise last_error or Exception("所有 API 端点都失败")


# ============ 方式二：官网网页爬虫（备用） ============

class LotteryPageParser(HTMLParser):
    """解析官网开奖页面的 HTML"""
    def __init__(self):
        super().__init__()
        self.in_draw_row = False
        self.in_issue = False
        self.in_date = False
        self.in_num = False
        self.current_draw = {}
        self.draws = []
        self.numbers = []
        self.current_tag = ""
        self.current_class = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        self.current_tag = tag
        self.current_class = cls

        if tag == "tr" and "kj_tr" in cls:
            self.in_draw_row = True
            self.current_draw = {}
            self.numbers = []
        elif tag == "td" and self.in_draw_row:
            if "kj_issue" in cls or "issue" in cls:
                self.in_issue = True
            elif "kj_date" in cls or "date" in cls:
                self.in_date = True
            elif "kj_num" in cls or "red" in cls or "blue" in cls:
                self.in_num = True

    def handle_endtag(self, tag):
        if tag == "tr" and self.in_draw_row:
            self.in_draw_row = False
            if self.current_draw and self.numbers:
                self.current_draw["numbers"] = self.numbers
                self.draws.append(self.current_draw)
        elif tag == "td":
            self.in_issue = self.in_date = self.in_num = False

    def handle_data(self, data):
        if self.in_issue:
            self.current_draw["issue"] = data.strip()
        elif self.in_date:
            self.current_draw["date"] = data.strip()
        elif self.in_num:
            num = data.strip()
            if num.isdigit():
                self.numbers.append(int(num))


def fetch_page_via_web(page_no=1, timeout=60):
    """从官网抓取开奖数据页面（备用方案）"""
    draws = []

    urls_to_try = [
        "https://www.lottery.gov.cn/kj/kjlb.html?dlt",
        "http://www.lottery.gov.cn/kj/kjlb.html?dlt",
    ]

    for url in urls_to_try:
        try:
            print(f"      尝试网页: {url}")
            raw = _http_get(url, HEADERS, timeout)

            # 尝试用正则提取数据（官网页面结构可能变化）
            # 格式1: <td class="kj_issue">期号</td><td class="kj_date">日期</td>...<td class="red">号码</td>...
            pattern_old = r'<tr[^>]*class="kj_tr"[^>]*>.*?<td[^>]*class="[^"]*issue[^"]*"[^>]*>(\d+)</td>.*?<td[^>]*class="[^"]*date[^"]*"[^>]*>([\d\-]+)</td>(.*?)</tr>'

            # 格式2: 用更宽松的方式提取
            # 提取所有 <tr> 包含开奖信息的行
            tr_pattern = r'<tr[^>]*>(.*?)</tr>'
            td_pattern = r'<td[^>]*>(.*?)</td>'

            # 尝试多种解析方式
            # 方式A：找 JSON 数据
            json_match = re.search(r'var\s+kjData\s*=\s*(\[.*?\]);', raw, re.DOTALL)
            if json_match:
                print(f"      找到 JSON 数据")
                json_str = json_match.group(1)
                data = json.loads(json_str)
                for item in data:
                    if isinstance(item, dict):
                        issue = item.get("lotteryDrawNum", item.get("issue", ""))
                        date = item.get("lotteryDrawTime", item.get("date", ""))
                        nums_str = item.get("lotteryDrawResult", item.get("numbers", ""))
                        if isinstance(nums_str, str):
                            nums = [int(x) for x in nums_str.split() if x.isdigit()]
                        elif isinstance(nums_str, list):
                            nums = [int(x) for x in nums_str]
                        else:
                            nums = []
                        if issue and date and len(nums) >= 7:
                            draws.append({
                                "issue": str(issue),
                                "date": str(date),
                                "front": sorted(nums[:5]),
                                "back": sorted(nums[5:7]),
                            })
                if draws:
                    print(f"      从 JSON 解析到 {len(draws)} 期")
                    return draws[:PERIOD]

            # 方式B：正则提取 <tr> 行
            tr_matches = re.findall(tr_pattern, raw, re.DOTALL)
            for tr_content in tr_matches:
                td_matches = re.findall(td_pattern, tr_content, re.DOTALL)
                nums = []
                issue = ""
                date = ""
                for td in td_matches:
                    td_clean = re.sub(r'<[^>]+>', '', td).strip()
                    # 检查是否为期号 (5位数字)
                    if re.match(r'^\d{5}$', td_clean) and not issue:
                        issue = td_clean
                    # 检查是否为日期
                    elif re.match(r'^\d{4}-\d{2}-\d{2}$', td_clean) and not date:
                        date = td_clean
                    # 检查是否为号码 (1-35)
                    elif re.match(r'^\d{1,2}$', td_clean):
                        n = int(td_clean)
                        if 1 <= n <= 35:
                            nums.append(n)

                if issue and date and len(nums) >= 7:
                    draws.append({
                        "issue": issue,
                        "date": date,
                        "front": sorted(nums[:5]),
                        "back": sorted(nums[5:7]),
                    })

            if draws:
                print(f"      从 HTML 解析到 {len(draws)} 期")
                return draws[:PERIOD]
            else:
                print(f"      网页解析未找到数据")

        except Exception as e:
            print(f"      网页抓取失败: {type(e).__name__}: {str(e)[:80]}")
            continue

    return draws


# ============ 核心获取逻辑 ============

def fetch_page(page_no, max_retries=3, timeout=60):
    """带重试机制的单页获取"""
    last_error = None

    for attempt in range(max_retries):
        try:
            items = fetch_page_via_api(page_no, timeout=timeout)
            if items is not None:
                return items
        except Exception as e:
            last_error = e
            wait = 2 ** attempt
            print(f"    重试 {attempt+1}/{max_retries} (等待 {wait}s)...")
            time.sleep(wait)

    raise Exception(f"第{page_no}页失败（重试{max_retries}次）: {last_error}")


def fetch_all():
    total_pages = (PERIOD + PAGE_SIZE - 1) // PAGE_SIZE
    seen = set()
    draws = []

    print(f"获取 {PERIOD} 期数据，共 {total_pages} 页")
    print(f"使用 {'requests' if HAS_REQUESTS else 'urllib'} 库")

    # 先用 API 获取
    print("\n--- 尝试 API 接口 ---")
    api_success = False
    for p in range(1, total_pages + 1):
        print(f"  第 {p}/{total_pages} 页...", end=" ", flush=True)
        try:
            items = fetch_page(p, max_retries=2, timeout=60)
            if not items:
                print("空，停止")
                break
            for item in items:
                issue = item["lotteryDrawNum"]
                if issue in seen:
                    continue
                seen.add(issue)
                nums = [int(x) for x in item["lotteryDrawResult"].split()]
                if len(nums) < 7:
                    continue
                draws.append({
                    "issue": issue,
                    "date": item.get("lotteryDrawTime", ""),
                    "front": sorted(nums[:5]),
                    "back": sorted(nums[5:7]),
                })
            print(f"已获取 {len(draws)} 期")
            if len(draws) >= PERIOD:
                break
            api_success = True
            time.sleep(0.5)
        except Exception as e:
            print(f"错误: {type(e).__name__}")
            print(f"  跳过第{p}页")
            time.sleep(1)
            continue

    # 如果 API 完全失败，使用网页爬虫备用方案
    if not api_success or len(draws) < 10:
        print(f"\n--- API 获取不足（仅 {len(draws)} 期），尝试网页爬虫备用方案 ---")
        web_draws = fetch_page_via_web()
        if web_draws:
            for d in web_draws:
                if d["issue"] not in seen:
                    draws.append(d)
                    seen.add(d["issue"])
            draws.sort(key=lambda d: int(d["issue"]), reverse=True)
            draws = draws[:PERIOD]
            print(f"  合并后共 {len(draws)} 期")

    draws.sort(key=lambda d: int(d["issue"]), reverse=True)
    return draws[:PERIOD]


# ============ 保存逻辑 ============

def save_js(draws):
    path = os.path.join(OUT_DIR, "all_draws.js")
    lines = [
        f"// 大乐透开奖数据 — {len(draws)}期",
        f"// 自动更新: {time.strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "// 数据来源: 中国体彩官方API",
        "",
        "const ALL_DRAWS = [",
    ]
    for i, d in enumerate(reversed(draws)):
        front_str = " ".join(f"{n:02d}" for n in d["front"])
        back_str = " ".join(f"{n:02d}" for n in d["back"])
        line = (
            f'  {{issue:"{d["issue"]}",date:"{d["date"]}",'
            f'front:[{",".join(map(str, d["front"]))}],'
            f'back:[{",".join(map(str, d["back"]))}],'
            f'front_str:"{front_str}",back_str:"{back_str}"}}'
        )
        if i < len(draws) - 1:
            line += ","
        lines.append(line)
    lines.append("];\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    size = os.path.getsize(path)
    print(f"  all_draws.js: {size:,} bytes")
    return path


def save_xlsx(draws):
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        path = os.path.join(OUT_DIR, "1.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "大乐透开奖数据"

        headers = [
            "期号", "开奖时间", "周",
            "前区一", "前区二", "前区三", "前区四", "前区五",
            "后区一", "后区二",
        ]

        hdr_fill = PatternFill(start_color="C0392B", end_color="C0392B", fill_type="solid")
        hdr_font = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
        front_font = Font(name="微软雅黑", size=11, bold=True, color="C0392B")
        back_font = Font(name="微软雅黑", size=11, bold=True, color="2980B9")
        normal_font = Font(name="微软雅黑", size=10)
        center = Alignment(horizontal="center", vertical="center")
        thin = Border(
            left=Side(style="thin", color="D0D0D0"),
            right=Side(style="thin", color="D0D0D0"),
            top=Side(style="thin", color="D0D0D0"),
            bottom=Side(style="thin", color="D0D0D0"),
        )

        for c, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=c, value=h)
            cell.fill = hdr_fill
            cell.font = hdr_font
            cell.alignment = center
            cell.border = thin

        weekdays = ["日", "一", "二", "三", "四", "五", "六"]
        for r, d in enumerate(draws, 2):
            ws.cell(row=r, column=1, value=d["issue"]).font = normal_font
            ws.cell(row=r, column=2, value=d["date"]).font = normal_font
            try:
                t = time.strptime(d["date"], "%Y-%m-%d")
                ws.cell(row=r, column=3, value=weekdays[t.tm_wday]).font = normal_font
            except:
                pass
            for i, n in enumerate(d["front"]):
                ws.cell(row=r, column=4 + i, value=n).font = front_font
            for i, n in enumerate(d["back"]):
                ws.cell(row=r, column=9 + i, value=n).font = back_font
            for c in range(1, 11):
                ws.cell(row=r, column=c).alignment = center
                ws.cell(row=r, column=c).border = thin

        widths = [10, 12, 6, 6, 6, 6, 6, 6, 6, 6]
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(draws) + 1}"

        wb.save(path)
        print(f"  1.xlsx: {os.path.getsize(path):,} bytes")
        return path
    except ImportError:
        print("  openpyxl 未安装，跳过 xlsx 生成")
        return None


if __name__ == "__main__":
    print("=" * 50)
    print("  大乐透数据自动更新")
    print("=" * 50)

    if not HAS_REQUESTS:
        print("  警告: 未安装 requests 库，使用 urllib 备用方案")

    try:
        draws = fetch_all()
        print(f"\n共获取 {len(draws)} 期")
        if draws:
            save_js(draws)
            save_xlsx(draws)
            print("\n完成！")
        else:
            print("\n警告: 未能获取新数据，保留现有数据")
    except Exception as e:
        print(f"\n获取数据失败: {e}")
        print("保留现有数据，不中断流程")
        sys.exit(0)