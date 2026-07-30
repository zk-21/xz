"""
GitHub Actions 数据更新脚本
每天自动抓取最新500期数据，生成 all_draws.js

修复：使用 requests 库 + 重试机制 + 备用方案
"""
import json
import os
import sys
import time
import ssl
import urllib.request
import urllib.error

# 检查是否启用代理（环境变量设置）
PROXY = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
if PROXY:
    print(f"  使用代理: {PROXY}")

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# 多个备用 API 端点
API_ENDPOINTS = [
    "https://webapi.sporttery.cn/gateway/lottery/",
    "http://webapi.sporttery.cn/gateway/lottery/",  # HTTP 备用
]
API_BASE = API_ENDPOINTS[0]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.lottery.gov.cn/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
PERIOD = 1000
PAGE_SIZE = 30
OUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fetch_page_requests(page_no, timeout=45):
    """使用 requests 库（更稳定，支持代理）"""
    params = {
        "gameNo": "85",
        "provinceId": "0",
        "pageSize": str(PAGE_SIZE),
        "isVerify": "1",
        "pageNo": str(page_no),
    }
    url = API_BASE + "getHistoryPageListV1.qry"

    # 尝试每个 API 端点
    last_error = None
    for base_url in API_ENDPOINTS:
        try:
            full_url = base_url + "getHistoryPageListV1.qry"
            resp = requests.get(
                full_url,
                params=params,
                headers=HEADERS,
                timeout=timeout,
                proxies={"http": PROXY, "https": PROXY} if PROXY else None,
                verify=False,  # 跳过 SSL 验证
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("success"):
                return data["value"]["list"]
            else:
                last_error = Exception(data.get("errorMessage", "API error"))
        except Exception as e:
            last_error = e
            continue

    raise last_error or Exception("所有 API 端点都失败")


def fetch_page_urllib(page_no, timeout=45):
    """使用 urllib（备用方案）"""
    params = f"gameNo=85&provinceId=0&pageSize={PAGE_SIZE}&isVerify=1&pageNo={page_no}"

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    last_error = None
    for base_url in API_ENDPOINTS:
        try:
            url = base_url + "getHistoryPageListV1.qry?" + params
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("success"):
                return data["value"]["list"]
            else:
                last_error = Exception(data.get("errorMessage", "API error"))
        except Exception as e:
            last_error = e
            continue

    raise last_error or Exception("所有 API 端点都失败")


def fetch_page(page_no, max_retries=3):
    """带重试机制的获取"""
    last_error = None

    for attempt in range(max_retries):
        try:
            if HAS_REQUESTS:
                return fetch_page_requests(page_no, timeout=45)
            else:
                return fetch_page_urllib(page_no, timeout=45)
        except Exception as e:
            last_error = e
            wait = 2 ** attempt
            if attempt < max_retries - 1:
                print(f"    重试 {attempt+1}/{max_retries} (等待 {wait}s)...")
                time.sleep(wait)

    raise Exception(f"获取第{page_no}页失败（重试{max_retries}次）: {last_error}")


def fetch_all():
    total_pages = (PERIOD + PAGE_SIZE - 1) // PAGE_SIZE
    seen = set()
    draws = []

    print(f"Fetching {PERIOD} periods, {total_pages} pages")
    print(f"使用 {'requests' if HAS_REQUESTS else 'urllib'} 库")
    print(f"API 端点: {', '.join(API_ENDPOINTS)}")

    for p in range(1, total_pages + 1):
        print(f"  Page {p}/{total_pages}...", end=" ", flush=True)
        try:
            items = fetch_page(p)
            if not items:
                print("empty, stopping")
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
            print(f"{len(draws)} total")
            if len(draws) >= PERIOD:
                break
            time.sleep(0.5)
        except Exception as e:
            print(f"ERROR: {e}")
            print(f"  跳过第{p}页，继续...")
            time.sleep(1)
            continue

    draws.sort(key=lambda d: int(d["issue"]), reverse=True)
    return draws[:PERIOD]


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
            "期号", "日期", "星期",
            "前1", "前2", "前3", "前4", "前5", "后1", "后2",
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
        print("  建议: pip install requests")

    draws = fetch_all()
    print(f"\n  Total: {len(draws)} periods ({draws[-1]['issue'] if draws else 'N/A'} ~ {draws[0]['issue'] if draws else 'N/A'})\n")

    if draws:
        save_js(draws)
        save_xlsx(draws)
        print("\n  Done!")
    else:
        print("\n  错误: 未能获取任何数据")
        sys.exit(1)
