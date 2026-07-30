"""
本地数据更新脚本
在本地电脑运行，然后推送到 GitHub

使用方法：
1. 安装依赖: pip install requests
2. 运行: python scripts/local_update.py
3. 脚本会自动更新 all_draws.js 并提交到 GitHub
"""
import json
import os
import sys
import time
import subprocess

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    print("错误: 请先安装 requests 库")
    print("  pip install requests")
    sys.exit(1)

API_BASE = "https://webapi.sporttery.cn/gateway/lottery/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.lottery.gov.cn/",
}
PERIOD = 1000
PAGE_SIZE = 30
OUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fetch_page(page_no, timeout=30):
    """获取单页数据"""
    params = {
        "gameNo": "85",
        "provinceId": "0",
        "pageSize": str(PAGE_SIZE),
        "isVerify": "1",
        "pageNo": str(page_no),
    }
    resp = requests.get(
        API_BASE + "getHistoryPageListV1.qry",
        params=params,
        headers=HEADERS,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise Exception(data.get("errorMessage", "API error"))
    return data["value"]["list"]


def fetch_all():
    """获取所有数据"""
    total_pages = (PERIOD + PAGE_SIZE - 1) // PAGE_SIZE
    seen = set()
    draws = []

    print(f"获取 {PERIOD} 期数据，共 {total_pages} 页")
    for p in range(1, total_pages + 1):
        print(f"  第 {p}/{total_pages} 页...", end=" ", flush=True)
        try:
            items = fetch_page(p)
            if not items:
                print("无数据，停止")
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
            time.sleep(0.3)
        except Exception as e:
            print(f"错误: {e}")
            print("  跳过此页")
            time.sleep(1)
            continue

    draws.sort(key=lambda d: int(d["issue"]), reverse=True)
    return draws[:PERIOD]


def save_js(draws):
    """保存为 JS 文件"""
    path = os.path.join(OUT_DIR, "all_draws.js")
    lines = [
        f"// 大乐透开奖数据 — {len(draws)}期",
        f"// 本地更新: {time.strftime('%Y-%m-%d %H:%M:%S')}",
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
    print(f"  已保存: all_draws.js ({os.path.getsize(path):,} 字节)")


def git_push():
    """推送到 GitHub"""
    try:
        print("\n正在推送到 GitHub...")
        subprocess.run(["git", "add", "all_draws.js"], cwd=OUT_DIR, check=True)
        
        # 检查是否有更改
        result = subprocess.run(
            ["git", "diff", "--staged", "--quiet"],
            cwd=OUT_DIR,
            capture_output=True
        )
        if result.returncode == 0:
            print("  数据已是最新，无需推送")
            return False
        
        subprocess.run(
            ["git", "commit", "-m", f"更新数据 {time.strftime('%Y-%m-%d %H:%M')}"],
            cwd=OUT_DIR,
            check=True
        )
        subprocess.run(["git", "push"], cwd=OUT_DIR, check=True)
        print("  推送成功！")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  Git 操作失败: {e}")
        return False
    except Exception as e:
        print(f"  错误: {e}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("  大乐透数据本地更新")
    print("=" * 50)
    
    draws = fetch_all()
    print(f"\n共获取 {len(draws)} 期")
    
    if draws:
        save_js(draws)
        
        # 询问是否推送到 GitHub
        print("\n" + "=" * 50)
        choice = input("是否推送到 GitHub? (y/n): ").strip().lower()
        if choice == 'y':
            git_push()
        else:
            print("\n已跳过推送。手动推送:")
            print("  git add all_draws.js")
            print("  git commit -m '更新数据'")
            print("  git push")
    else:
        print("\n错误: 未能获取任何数据")
        sys.exit(1)
    
    print("\n完成！")
