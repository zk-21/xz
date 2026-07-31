"""测试 500.com 分块请求能否消除间隙"""
import ssl, urllib.request, re, time

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
HEADERS = {"User-Agent": UA}
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def fetch_500(start, end=99999):
    url = f"https://datachart.500.com/dlt/history/newinc/history.php?start={start:05d}&end={end:05d}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return []

    draws = []
    trs = re.findall(r'<tr[^>]*>(.*?)</tr>', raw, re.DOTALL)
    for tr in trs:
        td_detail = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
        if len(td_detail) < 16:
            continue
        clean = [re.sub(r'<[^>]+>', '', td).strip() for td in td_detail]
        issue = clean[1]
        if not re.match(r'^\d{5}$', issue):
            continue
        front_nums = []
        for j in range(2, 7):
            v = clean[j]
            if re.match(r'^\d{1,2}$', v):
                n = int(v)
                if 1 <= n <= 35:
                    front_nums.append(n)
        back_nums = []
        for j in range(7, 9):
            v = clean[j]
            if re.match(r'^\d{1,2}$', v):
                n = int(v)
                if 1 <= n <= 35:
                    back_nums.append(n)
        date_str = clean[15] if len(clean) > 15 else ""
        if not re.match(r'\d{4}-\d{2}-\d{2}', date_str):
            date_str = ""
        if len(front_nums) == 5 and len(back_nums) == 2 and date_str:
            draws.append({"issue": int(issue)})
    return draws

# 方案 A: 分块请求 (每块 300 期)
print("=== 方案 A: 分块请求 (每块 300 期) ===")
chunk_size = 300
all_issues = {}
for start_base in range(25200, 26100, chunk_size):
    end = min(start_base + chunk_size + 50, 26085)
    d = fetch_500(start_base, end)
    for r in d:
        all_issues[r["issue"]] = r
    print(f"  {start_base}-{end}: {len(d)} 期")
    time.sleep(0.3)

issues = sorted(all_issues.keys(), reverse=True)
print(f"\n合计: {len(issues)} 期 ({issues[0]}~{issues[-1]})")
diffs = [issues[i+1] - issues[i] for i in range(len(issues)-1)]
gaps = [(issues[i], issues[i+1], d) for i, d in enumerate(diffs) if d > 1]
if gaps:
    print(f"⚠ 仍有 {len(gaps)} 个间隙:")
    for b, a, d in gaps:
        print(f"  {b} -> {a} (缺失 {d-1} 期)")
else:
    print("✓ 完全连续!")

# 方案 B: 用 end=最新, 不同 start 从小到大覆盖
print("\n=== 方案 B: 渐进式 start ===")
all_issues2 = {}
for start in [25800, 25500, 25200, 24900, 24600, 24300, 24000, 23500, 23000, 22500]:
    d = fetch_500(start, 26085)
    for r in d:
        all_issues2[r["issue"]] = r
    print(f"  start={start}: {len(d)} 期, 累计 {len(all_issues2)}")
    time.sleep(0.3)

issues2 = sorted(all_issues2.keys(), reverse=True)
print(f"\n合计: {len(issues2)} 期 ({issues2[0]}~{issues2[-1]})")
diffs2 = [issues2[i+1] - issues2[i] for i in range(len(issues2)-1)]
gaps2 = [(issues2[i], issues2[i+1], d) for i, d in enumerate(diffs2) if d > 1]
if gaps2:
    print(f"⚠ 仍有 {len(gaps2)} 个间隙:")
    for b, a, d in gaps2[:10]:
        print(f"  {b} -> {a} (缺失 {d-1} 期)")
else:
    print("✓ 完全连续!")