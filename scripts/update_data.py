"""
GitHub Actions 数据更新脚本
每天自动抓取最新500期数据，生成 all_draws.js 和 1.xlsx
"""
import urllib.request
import urllib.error
import json
import os
import sys
import time
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

API_BASE = "https://webapi.sporttery.cn/gateway/lottery/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.lottery.gov.cn/",
}
PERIOD = 500  # 固定500期
PAGE_SIZE = 30
OUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fetch_page(page_no):
    params = f"getHistoryPageListV1.qry?gameNo=85&provinceId=0&pageSize={PAGE_SIZE}&isVerify=1&pageNo={page_no}"
    url = API_BASE + params
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("success"):
        raise Exception(data.get("errorMessage", "API error"))
    return data["value"]["list"]


def fetch_all():
    total_pages = (PERIOD + PAGE_SIZE - 1) // PAGE_SIZE
    seen = set()
    draws = []

    print(f"Fetching {PERIOD} periods, {total_pages} pages")
    for p in range(1, total_pages + 1):
        print(f"  Page {p}/{total_pages}...", end=" ")
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
        time.sleep(0.3)

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
    print(f"  all_draws.js: {os.path.getsize(path):,} bytes")


def save_xlsx(draws):
    path = os.path.join(OUT_DIR, "1.xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "大乐透开奖数据"

    headers = [
        "期号", "日期", "星期",
        "前1", "前2", "前3", "前4", "前5", "后1", "后2",
        "一等注数", "一等金额", "一等追加注数", "一等追加金额",
        "二等注数", "二等金额", "二等追加注数", "二等追加金额",
        "三等注数", "三等金额", "四等注数", "四等金额",
        "五等注数", "五等金额", "六等注数", "六等金额",
        "销售额", "奖池",
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
            ws.cell(row=r, column=10 + i, value=n).font = back_font
        for c in range(1, 29):
            ws.cell(row=r, column=c).alignment = center
            ws.cell(row=r, column=c).border = thin

    widths = [8, 12, 5, 6, 6, 6, 6, 6, 6, 6,
              10, 10, 10, 10, 10, 10, 10, 10,
              10, 10, 10, 10, 10, 10, 10, 10, 14, 14]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(draws) + 1}"

    wb.save(path)
    print(f"  1.xlsx: {os.path.getsize(path):,} bytes")


if __name__ == "__main__":
    print("=" * 50)
    print("  大乐透数据自动更新")
    print("=" * 50)
    draws = fetch_all()
    print(f"\n  Total: {len(draws)} periods ({draws[-1]['issue']} ~ {draws[0]['issue']})\n")
    save_js(draws)
    save_xlsx(draws)
    print("\n  Done!")
