"""测试 API 数据的连续性"""
import json, ssl, urllib.request, urllib.parse, time

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
HEADERS = {"User-Agent": UA, "Referer": "https://www.lottery.gov.cn/"}
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def fetch_page(page_no):
    params = {
        "gameNo": "85", "provinceId": "0",
        "pageSize": "30", "isVerify": "1",
        "pageNo": str(page_no),
    }
    url = "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry"
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(url + "?" + query, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("success"):
        return data["value"]["list"]
    return []

all_issues = []
for p in range(1, 35):
    items = fetch_page(p)
    if not items:
        print(f"第{p}页无数据，停止")
        break
    for item in items:
        issue = int(item.get("lotteryDrawNum", 0))
        all_issues.append(issue)
    print(f"第{p}页: {len(items)} 期, 总计 {len(all_issues)}")
    time.sleep(0.2)

all_issues.sort(reverse=True)
print(f"\n总期数: {len(all_issues)}")
print(f"范围: {all_issues[0]} ~ {all_issues[-1]}")

# 检查连续性
diffs = [all_issues[i+1] - all_issues[i] for i in range(len(all_issues)-1)]
gaps = [(all_issues[i], all_issues[i+1], d) for i, d in enumerate(diffs) if d != 1 and d > 0]
if gaps:
    print(f"\n⚠ API 数据存在 {len(gaps)} 个间断:")
    for before, after, d in gaps:
        print(f"  {before} -> {after} (缺失 {d-1} 期)")
else:
    print("\n✓ API 数据完全连续")

# 检查重复
dupes = [x for x in all_issues if all_issues.count(x) > 1]
if dupes:
    print(f"⚠ 重复期号: {len(set(dupes))} 个")
else:
    print("✓ 无重复")