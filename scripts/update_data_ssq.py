"""
双色球数据更新脚本（独立于大乐透，输出 all_draws_ssq.js / 1_ssq.xlsx）
策略：多数据源自动切换
  1. 中国福彩官网 API (www.cwl.gov.cn) - 主要来源
  2. 500彩票网 (datachart.500.com) - 备用
"""
import json
import os
import re
import sys
import time
import ssl
import urllib.request
import urllib.parse
import warnings

warnings.filterwarnings("ignore", message="Unverified HTTPS request")
try:
    import urllib3
    warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    pass

PROXY = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
if PROXY:
    print(f"  使用代理: {PROXY}")

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

PERIOD = 1000
OUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
HTML_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}
API_HEADERS = {
    "User-Agent": UA,
    "Referer": "https://www.cwl.gov.cn/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}


def _http_get(url, headers=None, timeout=60):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers=headers or HTML_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _requests_get(url, params=None, headers=None, timeout=60):
    kwargs = {"headers": headers or HTML_HEADERS, "timeout": timeout, "verify": False}
    if PROXY:
        kwargs["proxies"] = {"http": PROXY, "https": PROXY}
    if params:
        kwargs["params"] = params
    resp = requests.get(url, **kwargs)
    return resp


# ============ 数据源 1: 中国福彩官网 API (主) ============

API_URLS = [
    "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice",
    "http://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice",
]


def parse_ssq_item(item):
    """解析单条开奖记录，返回 dict 或 None"""
    issue = str(item.get("code", ""))
    date = str(item.get("date", ""))[:10]
    red_raw = item.get("red", "")
    blue_raw = item.get("blue", "")
    if isinstance(red_raw, str):
        red = [int(x) for x in re.split(r"[,\s]+", red_raw.strip()) if x.strip().isdigit()]
    else:
        red = [int(x) for x in red_raw]
    if isinstance(blue_raw, str):
        blue = [int(x) for x in re.split(r"[,\s]+", blue_raw.strip()) if x.strip().isdigit()]
    else:
        blue = [int(x) for x in blue_raw]
    if issue and re.match(r"^\d{5,7}$", issue) and len(red) == 6 and len(blue) == 1:
        return {"issue": issue, "date": date, "front": sorted(red), "back": sorted(blue)}
    return None


def fetch_from_api(timeout=60):
    """通过福彩官网 API 分页获取全部数据"""
    draws = []
    seen = set()
    page_no = 1
    page_size = 50
    empty_pages = 0

    print("  尝试中国福彩官网 API...")
    while page_no <= 60 and empty_pages < 2:
        params = {
            "name": "ssq",
            "systemType": "PC",
            "pageNo": str(page_no),
            "pageSize": str(page_size),
        }
        got_data = False
        for url in API_URLS:
            try:
                if HAS_REQUESTS:
                    resp = _requests_get(url, params, API_HEADERS, timeout)
                    if resp.status_code in (403, 567):
                        print(f"    API 被阻止 ({resp.status_code})")
                        return []
                    resp.raise_for_status()
                    data = resp.json()
                else:
                    query = urllib.parse.urlencode(params)
                    raw = _http_get(url + "?" + query, API_HEADERS, timeout)
                    data = json.loads(raw)

                items = data.get("result", [])
                if not items:
                    empty_pages += 1
                    got_data = True
                    break
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    d = parse_ssq_item(item)
                    if d and d["issue"] not in seen:
                        seen.add(d["issue"])
                        draws.append(d)
                got_data = True
                break
            except Exception as e:
                if "403" in str(e) or "567" in str(e):
                    print(f"    API 被阻止")
                    return []
                continue

        if not got_data:
            break

        if page_no == 1:
            print(f"    第1页: {len(draws)} 期")
        if page_no % 5 == 0:
            print(f"    第{page_no}页: 共 {len(draws)} 期")

        page_no += 1
        time.sleep(0.4)

    draws.sort(key=lambda d: int(d["issue"]), reverse=True)
    print(f"    API 共获取 {len(draws)} 期")
    return draws


# ============ 数据源 2: 500彩票网 ============

def fetch_from_500(start_period=3001, timeout=60):
    """从 500.com 抓取双色球历史数据"""
    draws = []
    url = f"https://datachart.500.com/shuangseqiu/history/newinc/history.php?start={start_period:05d}&end=99999"

    print(f"  尝试 500彩票网: {url[:80]}...")
    try:
        raw = _http_get(url, HTML_HEADERS, timeout)
        print(f"    获取成功: {len(raw)} bytes")

        trs = re.findall(r'<tr[^>]*>(.*?)</tr>', raw, re.DOTALL)
        for tr in trs:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
            if len(tds) < 10:
                continue
            clean = [re.sub(r'<[^>]+>', '', td).strip() for td in tds]

            # 找期号（首个5位纯数字单元格）
            issue = ""
            for c in clean[:3]:
                if re.match(r'^\d{5}$', c):
                    issue = c
                    break
            if not issue:
                continue

            # 期号后连续 7 个球号：前 6 个红球(1-33)，第 7 个蓝球(1-16)
            reds, blue = [], []
            for c in clean:
                if c == issue or not re.match(r'^\d{1,2}$', c):
                    if reds:
                        break
                    continue
                n = int(c)
                if len(reds) < 6:
                    if 1 <= n <= 33:
                        reds.append(n)
                    else:
                        break
                else:
                    if 1 <= n <= 16:
                        blue = [n]
                        break
                    else:
                        break
            if len(reds) != 6 or len(blue) != 1:
                continue

            date_str = ""
            for c in reversed(clean):
                if re.match(r'\d{4}-\d{2}-\d{2}', c):
                    date_str = c[:10]
                    break
            if not date_str:
                continue

            draws.append({
                "issue": issue,
                "date": date_str,
                "front": sorted(reds),
                "back": sorted(blue),
            })

        if draws:
            # 去重
            uniq = {}
            for d in draws:
                uniq[d["issue"]] = d
            draws = list(uniq.values())
            draws.sort(key=lambda d: int(d["issue"]), reverse=True)
            print(f"    解析到 {len(draws)} 期 (最新 {draws[0]['issue']})")
        else:
            print(f"    未解析到数据")
    except Exception as e:
        print(f"    失败: {type(e).__name__}: {str(e)[:80]}")

    return draws


# ============ 核心获取逻辑 ============

def fetch_all():
    print(f"获取双色球 {PERIOD} 期数据")
    print(f"使用 {'requests' if HAS_REQUESTS else 'urllib'} 库\n")

    all_draws = {}

    print("--- 数据源 1: 中国福彩官网 API ---")
    api_draws = fetch_from_api(timeout=60)
    for d in api_draws:
        all_draws[d["issue"]] = d

    if len(all_draws) < PERIOD:
        print(f"\n--- 数据源 2: 500彩票网 ---")
        d500 = fetch_from_500(timeout=60)
        for d in d500:
            if d["issue"] not in all_draws:
                all_draws[d["issue"]] = d
        print(f"  合并后: {len(all_draws)} 期")

    draws = sorted(all_draws.values(), key=lambda d: int(d["issue"]), reverse=True)
    return draws[:PERIOD]


# ============ 数据验证 ============

def verify_continuity(draws):
    """验证数据连续性（双色球期号 3 位年度内递增，跨年归 1）"""
    if not draws:
        return False
    issues = [int(d["issue"]) for d in draws]
    diffs = [issues[i+1] - issues[i] for i in range(len(issues)-1)]
    gaps = [(issues[i], issues[i+1], d) for i, d in enumerate(diffs) if d > 1]
    if gaps:
        print(f"\n  ⚠ 数据存在 {len(gaps)} 个间断:")
        for b, a, d in gaps[:5]:
            print(f"    {b} -> {a} (缺 {d-1} 期)")
        if len(gaps) > 5:
            print(f"    ... 还有 {len(gaps)-5} 个")
        return False
    else:
        print(f"\n  ✓ 数据完全连续 ({len(draws)} 期)")
        return True


def verify_numbers(draws):
    """验证号码范围: 红球 1-33 六个不重复, 蓝球 1-16"""
    bad = 0
    for d in draws:
        r, b = d["front"], d["back"]
        if len(set(r)) != 6 or not all(1 <= n <= 33 for n in r):
            bad += 1
        if len(b) != 1 or not (1 <= b[0] <= 16):
            bad += 1
    if bad:
        print(f"  ⚠ {bad} 期号码范围异常")
    else:
        print(f"  ✓ 号码范围全部正确")
    return bad == 0


# ============ 保存逻辑 ============

def save_js(draws):
    path = os.path.join(OUT_DIR, "all_draws_ssq.js")
    lines = [
        f"// 双色球开奖数据 — {len(draws)}期",
        f"// 自动更新: {time.strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "// 数据来源: 中国福彩官网API / 500彩票网",
        "",
        "var SSQ_DRAWS = [",
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
    print(f"  all_draws_ssq.js: {size:,} bytes")
    return path


def save_xlsx(draws):
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        path = os.path.join(OUT_DIR, "1_ssq.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "双色球开奖数据"

        headers = [
            "期号", "开奖时间", "周",
            "红球一", "红球二", "红球三", "红球四", "红球五", "红球六",
            "蓝球",
        ]

        hdr_fill = PatternFill(start_color="1565C0", end_color="1565C0", fill_type="solid")
        hdr_font = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
        front_font = Font(name="微软雅黑", size=11, bold=True, color="C0392B")
        back_font = Font(name="微软雅黑", size=11, bold=True, color="1565C0")
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
            except Exception:
                pass
            for i, n in enumerate(d["front"]):
                ws.cell(row=r, column=4 + i, value=n).font = front_font
            for i, n in enumerate(d["back"]):
                ws.cell(row=r, column=10 + i, value=n).font = back_font
            for c in range(1, 12):
                ws.cell(row=r, column=c).alignment = center
                ws.cell(row=r, column=c).border = thin

        widths = [10, 12, 6, 6, 6, 6, 6, 6, 6, 6]
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(draws) + 1}"

        wb.save(path)
        print(f"  1_ssq.xlsx: {os.path.getsize(path):,} bytes")
        return path
    except ImportError:
        print("  openpyxl 未安装，跳过 xlsx 生成")
        return None


def load_existing():
    """加载已有的 all_draws_ssq.js 数据"""
    path = os.path.join(OUT_DIR, "all_draws_ssq.js")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        pattern = r'\{issue:"(\d+)",date:"([^"]+)",front:\[([^\]]+)\],back:\[([^\]]+)\]'
        existing = {}
        for m in re.finditer(pattern, content):
            issue = m.group(1)
            date = m.group(2)
            front = [int(x.strip()) for x in m.group(3).split(",") if x.strip()]
            back = [int(x.strip()) for x in m.group(4).split(",") if x.strip()]
            if len(front) == 6 and len(back) == 1:
                existing[issue] = {
                    "issue": issue,
                    "date": date,
                    "front": sorted(front),
                    "back": sorted(back),
                }
        print(f"  加载已有数据: {len(existing)} 期")
        return existing
    except Exception as e:
        print(f"  加载已有数据失败: {e}")
        return {}


if __name__ == "__main__":
    print("=" * 50)
    print("  双色球数据自动更新")
    print("=" * 50)

    if not HAS_REQUESTS:
        print("  警告: 未安装 requests 库")

    try:
        existing = load_existing()
        draws = fetch_all()

        # 与现有数据合并 (现有数据只补充缺失的)
        if existing and len(draws) < PERIOD:
            for issue, d in existing.items():
                if issue not in {x["issue"] for x in draws}:
                    draws.append(d)
            draws.sort(key=lambda d: int(d["issue"]), reverse=True)
            draws = draws[:PERIOD]
            print(f"\n与现有数据合并后: {len(draws)} 期")

        print(f"\n共获取 {len(draws)} 期")

        # 验证数据
        verify_continuity(draws)
        verify_numbers(draws)

        if draws:
            save_js(draws)
            save_xlsx(draws)
            print("\n完成！")
        else:
            print("\n警告: 未能获取新数据，保留现有数据")
    except Exception as e:
        import traceback
        print(f"\n获取数据失败: {e}")
        traceback.print_exc()
        print("保留现有数据")
        sys.exit(0)
