import re, json

with open(r'c:\Users\61419\Downloads\20260729103215\20260729103215\gh-pages\all_draws.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 解析所有数据
pattern = r'\{issue:"(\d+)",date:"([^"]+)",front:\[([^\]]+)\],back:\[([^\]]+)\]'
records = []
for m in re.finditer(pattern, content):
    issue = int(m.group(1))
    date = m.group(2)
    front = [int(x.strip()) for x in m.group(3).split(",") if x.strip()]
    back = [int(x.strip()) for x in m.group(4).split(",") if x.strip()]
    records.append({"issue": issue, "date": date, "front": front, "back": back})

print(f"总记录数: {len(records)}")
print(f"期号范围: {records[0]['issue']} ~ {records[-1]['issue']}")

# 1. 检查连续性
issues = [r["issue"] for r in records]
diffs = [issues[i+1] - issues[i] for i in range(len(issues)-1)]
gaps = [d for d in diffs if d != 1]
if gaps:
    print(f"\n⚠ 不连续！存在 {len(gaps)} 个间断:")
    for i, d in enumerate(diffs):
        if d != 1:
            print(f"  {issues[i]} -> {issues[i+1]} (间隔 {d})")
else:
    print("\n✓ 期号完全连续，无间断")

# 2. 检查号码有效性
invalid = []
for r in records:
    if len(r["front"]) != 5 or len(r["back"]) != 2:
        invalid.append(f"{r['issue']}: 号码数量错误")
    elif not all(1 <= n <= 35 for n in r["front"]):
        invalid.append(f"{r['issue']}: 前区号码超范围 {r['front']}")
    elif not all(1 <= n <= 12 for n in r["back"]):
        invalid.append(f"{r['issue']}: 后区号码超范围 {r['back']}")
    elif len(set(r["front"])) != 5:
        invalid.append(f"{r['issue']}: 前区有重复号码 {r['front']}")
    elif len(set(r["back"])) != 2:
        invalid.append(f"{r['issue']}: 后区有重复号码 {r['back']}")

if invalid:
    print(f"\n⚠ 号码异常 ({len(invalid)} 条):")
    for e in invalid[:10]:
        print(f"  {e}")
else:
    print("✓ 所有号码有效 (前区5个1-35不重复, 后区2个1-12不重复)")

# 3. 检查日期一致性
import datetime
date_issues = []
for r in records:
    try:
        dt = datetime.datetime.strptime(r["date"], "%Y-%m-%d")
        weekday_cn = ["日","一","二","三","四","五","六"]
        expected_weekday = weekday_cn[dt.weekday()]  # Monday=0
        d = {"issue": r["issue"], "date": r["date"], "weekday": dt.weekday()}
        date_issues.append(d)
    except:
        print(f"⚠ 日期格式错误: {r['issue']}: {r['date']}")

# 检查大乐透开奖日: 周一、三、六
draw_days = {0, 2, 5}  # Mon, Wed, Sat
non_draw = [d for d in date_issues if d["weekday"] not in draw_days]
if non_draw:
    print(f"\n⚠ 非开奖日数据 ({len(non_draw)} 条):")
    for d in non_draw[:10]:
        print(f"  {d['issue']}: {d['date']} (周{d['weekday']+1})")
else:
    print("✓ 所有日期均为大乐透开奖日 (周一、三、六)")

# 4. 抽样展示
print(f"\n=== 最新 5 期 ===")
for r in records[-5:]:
    print(f"  {r['issue']} | {r['date']} | 前区:{r['front']} 后区:{r['back']}")

print(f"\n=== 最早 5 期 ===")
for r in records[:5]:
    print(f"  {r['issue']} | {r['date']} | 前区:{r['front']} 后区:{r['back']}")

print(f"\n=== 总结 ===")
print(f"  期号连续: {'✓ 是' if not gaps else '✗ 否'}")
print(f"  号码有效: {'✓ 是' if not invalid else '✗ 否'}")
print(f"  日期合法: {'✓ 是' if not non_draw else '✗ 否'}")