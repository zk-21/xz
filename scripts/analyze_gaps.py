"""分析 500.com 数据缺失原因"""
import ssl, urllib.request, re

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
        return [], 0

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
            draws.append({
                "issue": issue,
                "date": date_str,
            })
    return draws, len(raw)

# 测试不同 end 值
print("=== 测试不同 end 参数 ===")
for start, end in [(25000, 26085), (25500, 26085), (26000, 26085), (26050, 26085)]:
    d, size = fetch_500(start, end)
    if d:
        d.sort(key=lambda x: int(x["issue"]), reverse=True)
        issues = [int(x["issue"]) for x in d]
        diffs = [issues[i+1] - issues[i] for i in range(len(issues)-1)]
        gaps = [x for x in diffs if x != 1]
        print(f"  start={start}, end={end}: {len(d)} 期, HTML={size:,}B")
        if gaps:
            print(f"    间断: {gaps[:5]}")
            for i, diff in enumerate(diffs):
                if diff != 1:
                    print(f"    {issues[i]} -> {issues[i+1]} (间隔 {diff})")
        else:
            print(f"    连续: {issues[0]} ~ {issues[-1]}")

# 测试：每次只请求 100 期的小窗口
print("\n=== 小窗口请求测试 ===")
for start in [25900, 25800, 25700, 25600]:
    d, size = fetch_500(start, start + 150)
    if d:
        d.sort(key=lambda x: int(x["issue"]), reverse=True)
        issues = [int(x["issue"]) for x in d]
        print(f"  start={start}: {len(d)} 期 ({issues[0]}~{issues[-1]})")
        # 检查是否连续
        diffs = [issues[i+1] - issues[i] for i in range(len(issues)-1)]
        gaps = [x for x in diffs if x != 1]
        if gaps:
            print(f"    有间断: {gaps}")
        else:
            print(f"    连续 ✓")