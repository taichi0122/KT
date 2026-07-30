"""
競艇予想サイト 生成スクリプト
================================
BoatraceOpenAPI（非公式）から当日の出走表(programs)・直前情報(previews)を取得し、
学習済みの重みでスコアリングして docs/index.html を生成する。
GitHub Actionsから毎日自動実行される想定。
"""

import datetime
import os
import zoneinfo

import requests

JST = zoneinfo.ZoneInfo("Asia/Tokyo")
today = datetime.datetime.now(JST).date()
YMD = today.strftime("%Y%m%d")
YEAR = today.year

PROGRAMS_URL = f"https://boatraceopenapi.github.io/programs/v2/{YEAR}/{YMD}.json"
PREVIEWS_URL = f"https://boatraceopenapi.github.io/previews/v2/{YEAR}/{YMD}.json"

# Colabで学習した重み（2026-06-01〜2026-07-27のデータ、previews込み）
WEIGHTS = {
    "lane": 0.1485,
    "natWin": 0.411,
    "locWin": 0.0216,
    "motor2": 0.163,
    "exTime": -0.1139,
    "st": 8.8732,
}
LANE_BASE = {1: 20, 2: 6, 3: 4, 4: 2, 5: 1, 6: 0.5}

STADIUM_NAMES = {
    1: "桐生", 2: "戸田", 3: "江戸川", 4: "平和島", 5: "多摩川", 6: "浜名湖",
    7: "蒲郡", 8: "常滑", 9: "津", 10: "三国", 11: "びわこ", 12: "住之江",
    13: "尼崎", 14: "鳴門", 15: "丸亀", 16: "児島", 17: "宮島", 18: "徳山",
    19: "下関", 20: "若松", 21: "芦屋", 22: "福岡", 23: "唐津", 24: "大村",
}


def fetch(url):
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        print(f"[警告] 取得失敗: {url} ({e})")
        return None


def score_boat(boat, ex_time):
    lane = boat["racer_boat_number"]
    nat = boat.get("racer_national_top_1_percent") or 0
    loc = boat.get("racer_local_top_1_percent") or 0
    motor2 = boat.get("racer_assigned_motor_top_2_percent") or 0
    st = boat.get("racer_average_start_timing") or 0.17

    s = LANE_BASE.get(lane, 0) * WEIGHTS["lane"]
    s += nat * WEIGHTS["natWin"]
    s += loc * WEIGHTS["locWin"]
    s += motor2 * (WEIGHTS["motor2"] / 10)
    s += (7.1 - ex_time) * WEIGHTS["exTime"]
    s += (0.22 - st) * WEIGHTS["st"]
    return s


def build_exhibition_lookup(previews):
    lookup = {}
    if not previews:
        return lookup
    for race in previews.get("previews", []):
        key_base = (race["race_stadium_number"], race["race_number"])
        for _, b in race.get("boats", {}).items():
            lane = b.get("racer_boat_number")
            ex = b.get("racer_exhibition_time")
            if lane is not None and ex is not None:
                lookup[(*key_base, lane)] = ex
    return lookup


def render_race(race, ex_lookup):
    stadium = race["race_stadium_number"]
    race_no = race["race_number"]
    boats = race.get("boats", [])
    scored = []
    for b in boats:
        ex = ex_lookup.get((stadium, race_no, b["racer_boat_number"]), 7.1)
        scored.append((score_boat(b, ex), b))
    scored.sort(key=lambda x: -x[0])

    venue_name = STADIUM_NAMES.get(stadium, f"場{stadium}")
    marks = ["◎", "○", "▲", "△", "△", "△"]
    rows = ""
    for i, (sc, b) in enumerate(scored):
        mark = marks[i] if i < len(marks) else ""
        rows += (
            f"<tr><td>{mark}</td><td>{b['racer_boat_number']}</td>"
            f"<td>{b.get('racer_name', '')}</td><td>{sc:.1f}</td></tr>"
        )
    formation = "-".join(str(b["racer_boat_number"]) for _, b in scored[:3])

    return f"""
    <div class="race-card">
      <h3>{venue_name} {race_no}R <span class="formation">予想: {formation}</span></h3>
      <table>
        <thead><tr><th></th><th>枠</th><th>選手</th><th>score</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    """


def main():
    programs = fetch(PROGRAMS_URL)
    previews = fetch(PREVIEWS_URL)
    ex_lookup = build_exhibition_lookup(previews)

    races_html = []
    if programs:
        races = sorted(
            programs.get("programs", []),
            key=lambda r: (r["race_stadium_number"], r["race_number"]),
        )
        for race in races:
            races_html.append(render_race(race, ex_lookup))

    date_str = today.strftime("%Y年%m月%d日")
    body = "".join(races_html) if races_html else (
        "<p>本日のレースデータがまだ取得できていません"
        "（非開催日、またはデータ反映待ちの可能性があります）。</p>"
    )
    generated_at = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")

    html = f"""<!DOCTYPE html>
<html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>競艇予想 {date_str}</title>
<style>
body {{ font-family: -apple-system, "Hiragino Kaku Gothic ProN", "Yu Gothic", sans-serif;
       background:#0A1929; color:#EAF2F8; margin:0; padding:20px; }}
h1 {{ font-size:20px; margin-bottom:4px; }}
.updated {{ font-size:11px; color:#5C7A90; margin-bottom:16px; }}
.race-card {{ background:#0F2438; border:1px solid #16324A; border-radius:10px;
              padding:14px; margin-bottom:14px; max-width:520px; }}
.race-card h3 {{ margin:0 0 8px; font-size:15px; }}
.formation {{ color:#3EC6E0; font-size:13px; margin-left:8px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th, td {{ padding:4px 6px; text-align:left; border-bottom:1px solid #16324A; }}
.disclaimer {{ font-size:11px; color:#5C7A90; margin-top:20px; line-height:1.6; max-width:520px; }}
</style>
</head><body>
<h1>競艇予想 {date_str}</h1>
<div class="updated">最終更新: {generated_at}</div>
{body}
<div class="disclaimer">
このページは非公式オープンAPI（BoatraceOpenAPI）を利用した個人の分析ツールで、BOATRACE公式・関連団体とは一切関係ありません。
表示している予想は過去データに基づく参考情報であり、的中や利益を保証するものではありません。
このページから舟券を購入することはできません。楽しむための参考情報としてご利用ください。
</div>
</body></html>"""

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("生成完了: docs/index.html")


if __name__ == "__main__":
    main()
