"""找到 500.com 连续数据的最大范围"""
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

# 测试不同 start 值的连续性
for start in [21000, 20500, 20000, 19800, 19500, 19300, 19200]:
    d = fetch_500(start)
    if d:
        d.sort(key=lambda x: x["issue"], reverse=True)
        issues = [x["issue"] for x in d]
        # 检查连续性: 只看正向间隙 (降序排列)
        diffs = [issues[i+1] - issues[i] for i in range(len(issues)-1)]
        # 降序: diff = issue[i+1] - issue[i], 应该是 -1
        # 如果 diff > 0, 表示 issue[i+1] > issue[i], 即有数据顺序问题
        # 如果 diff < -1, 表示有缺失
        gaps = [issues[i] - issues[i+1] - 1 for i in range(len(issues)-1) if issues[i] - issues[i+1] > 1]
        has_gap = len(gaps) > 0
        status = "⚠ 有间隙" if has_gap else "✓ 连续"
        print(f"start={start}: {len(d)} 期 ({issues[0]}~{issues[-1]}) {status}")
        if has_gap:
            # 显示前几个间隙
            for i in range(len(diffs)):
                if issues[i] - issues[i+1] > 1:
                    print(f"    {issues[i]} -> {issues[i+1]} (缺 {issues[i]-issues[i+1]-1} 期)")
                    break
    time.sleep(0.5)