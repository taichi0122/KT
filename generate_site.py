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

# コース(枠)の公式カラー。番号チップの背景/文字色に使う
LANE_COLOR = {
    1: ("#F2F0E9", "#14304A"),
    2: ("#26262A", "#F2F0E9"),
    3: ("#D8342A", "#FFFFFF"),
    4: ("#1E6FD9", "#FFFFFF"),
    5: ("#E8B72E", "#14304A"),
    6: ("#2E9E52", "#FFFFFF"),
}
# カード左端のアクセント線。2号艇(黒)は暗い背景に埋もれるので視認性の高いグレーに調整
LANE_ACCENT = {1: "#F2F0E9", 2: "#6B7280", 3: "#D8342A", 4: "#1E6FD9", 5: "#E8B72E", 6: "#2E9E52"}

CLASS_BY_NUMBER = {1: "A1", 2: "A2", 3: "B1", 4: "B2"}
CLASS_COLOR = {
    "A1": ("#3A2E12", "#E8B72E", "#5C4A1E"),
    "A2": ("#22303A", "#8FC7DE", "#2E4552"),
    "B1": ("#1E2A38", "#8FA9BE", "#2A3D4E"),
    "B2": ("#1A2028", "#6B7A8A", "#26303C"),
}

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
        boats_raw = race.get("boats", {})
        # previewsのboatsは形式が配列/オブジェクトのどちらの場合もあるため両対応する
        boats_iter = boats_raw.values() if isinstance(boats_raw, dict) else boats_raw
        for b in boats_iter:
            lane = b.get("racer_boat_number")
            ex = b.get("racer_exhibition_time")
            if lane is not None and ex is not None:
                lookup[(*key_base, lane)] = ex
    return lookup


def render_boat_card(rank, sc, b, ex_time):
    lane = b["racer_boat_number"]
    lane_bg, lane_text = LANE_COLOR.get(lane, ("#0F2438", "#EAF2F8"))
    accent = LANE_ACCENT.get(lane, "#3EC6E0")
    cls = CLASS_BY_NUMBER.get(b.get("racer_class_number"), None)
    cls_bg, cls_text, cls_border = CLASS_COLOR.get(cls, ("#1A2028", "#6B7A8A", "#26303C"))

    marks = ["◎", "○", "▲", "△", "△", "△"]
    mark = marks[rank] if rank < len(marks) else ""
    mark_color = "#E8B72E" if rank == 0 else ("#8FA9BE" if rank == 1 else "#D8342A" if rank == 2 else "#5C7A90")

    name = b.get("racer_name", "")
    age = b.get("racer_age")
    weight = b.get("racer_weight")
    nat1 = b.get("racer_national_top_1_percent") or 0
    nat2 = b.get("racer_national_top_2_percent") or 0
    nat3 = b.get("racer_national_top_3_percent") or 0
    loc1 = b.get("racer_local_top_1_percent") or 0
    loc2 = b.get("racer_local_top_2_percent") or 0
    loc3 = b.get("racer_local_top_3_percent") or 0
    motor2 = b.get("racer_assigned_motor_top_2_percent") or 0
    boat2 = b.get("racer_assigned_boat_top_2_percent") or 0
    st = b.get("racer_average_start_timing") or 0.17
    flying = b.get("racer_flying_count") or 0
    late = b.get("racer_late_count") or 0

    class_badge = (
        f'<span class="class-badge" style="background:{cls_bg};color:{cls_text};border-color:{cls_border}">{cls}</span>'
        if cls else ""
    )
    meta_bits = [f"登録番号 {b.get('racer_number', b.get('racer_registration_number', '-'))}"]
    if age is not None:
        meta_bits.append(f"{age}歳")
    if weight:
        meta_bits.append(f"{weight:.1f}kg")
    meta_row = " ・ ".join(meta_bits)

    return f"""
    <div class="boat-card" style="border-left:4px solid {accent}">
      <div class="boat-top">
        <div class="lane-chip" style="background:{lane_bg};color:{lane_text}">{lane}</div>
        <div class="boat-info">
          <div class="boat-name-row">
            <span class="boat-name">{name}</span>
            {class_badge}
            <span class="mark-badge" style="color:{mark_color}">{mark}</span>
          </div>
          <div class="boat-meta">{meta_row}</div>
        </div>
        <div class="boat-score">
          <div class="score-val">{sc:.1f}</div>
          <div class="score-rank">{rank + 1}位</div>
        </div>
      </div>
      <div class="stat-grid">
        <div class="stat-chip"><div class="stat-label">全国 勝率/2連/3連</div>
          <div class="stat-value">{nat1:.2f} / {nat2:.1f}% / {nat3:.1f}%</div></div>
        <div class="stat-chip"><div class="stat-label">当地 勝率/2連/3連</div>
          <div class="stat-value">{loc1:.2f} / {loc2:.1f}% / {loc3:.1f}%</div></div>
        <div class="stat-chip"><div class="stat-label">モーター2連率</div>
          <div class="stat-value">{motor2:.1f}%</div></div>
        <div class="stat-chip"><div class="stat-label">ボート2連率</div>
          <div class="stat-value">{boat2:.1f}%</div></div>
        <div class="stat-chip"><div class="stat-label">展示タイム</div>
          <div class="stat-value">{ex_time:.2f}秒</div></div>
        <div class="stat-chip"><div class="stat-label">平均ST</div>
          <div class="stat-value">{st:.2f}</div></div>
        <div class="stat-chip"><div class="stat-label">F数 / L数</div>
          <div class="stat-value">{flying} / {late}</div></div>
      </div>
    </div>
    """


def render_race(race, ex_lookup):
    stadium = race["race_stadium_number"]
    race_no = race["race_number"]
    boats = race.get("boats", [])
    scored = []
    for b in boats:
        ex = ex_lookup.get((stadium, race_no, b["racer_boat_number"]), 7.1)
        scored.append((score_boat(b, ex), b, ex))
    scored.sort(key=lambda x: -x[0])

    venue_name = STADIUM_NAMES.get(stadium, f"場{stadium}")
    formation = "-".join(str(b["racer_boat_number"]) for _, b, _ in scored[:3])
    cards = "".join(
        render_boat_card(i, sc, b, ex) for i, (sc, b, ex) in enumerate(scored)
    )

    return f"""
    <div class="race-card">
      <h3>{venue_name} {race_no}R <span class="formation">予想: {formation}</span></h3>
      {cards}
    </div>
    """


def render_venue_section(stadium, races_for_venue, ex_lookup, is_first):
    venue_name = STADIUM_NAMES.get(stadium, f"場{stadium}")
    anchor = f"venue-{stadium}"
    cards = "".join(render_race(race, ex_lookup) for race in races_for_venue)
    open_attr = " open" if is_first else ""
    return f"""
    <details class="venue" id="{anchor}"{open_attr}>
      <summary>{venue_name} <span class="race-count">({len(races_for_venue)}R)</span></summary>
      <div class="venue-body">{cards}</div>
    </details>
    """


def main():
    programs = fetch(PROGRAMS_URL)
    previews = fetch(PREVIEWS_URL)
    ex_lookup = build_exhibition_lookup(previews)

    venues_html = []
    nav_html = ""
    if programs:
        races = programs.get("programs", [])
        by_stadium = {}
        for race in races:
            by_stadium.setdefault(race["race_stadium_number"], []).append(race)

        stadium_order = sorted(by_stadium.keys())
        for s in stadium_order:
            by_stadium[s].sort(key=lambda r: r["race_number"])

        nav_links = []
        for s in stadium_order:
            name = STADIUM_NAMES.get(s, f"場{s}")
            nav_links.append(f'<a href="#venue-{s}">{name}</a>')
        nav_html = f'<nav class="venue-nav">{"".join(nav_links)}</nav>' if nav_links else ""

        for i, s in enumerate(stadium_order):
            venues_html.append(render_venue_section(s, by_stadium[s], ex_lookup, is_first=(i == 0)))

    date_str = today.strftime("%Y年%m月%d日")
    body = "".join(venues_html) if venues_html else (
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

.venue-nav {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:18px; max-width:520px; }}
.venue-nav a {{ background:#0F2438; border:1px solid #16324A; border-radius:16px;
                padding:6px 12px; font-size:12px; color:#3EC6E0; text-decoration:none; }}

.venue {{ max-width:520px; margin-bottom:12px; background:#0F2438; border:1px solid #16324A;
          border-radius:10px; overflow:hidden; }}
.venue summary {{ list-style:none; cursor:pointer; padding:14px 16px; font-size:16px;
                   font-weight:700; display:flex; align-items:center; gap:8px; }}
.venue summary::-webkit-details-marker {{ display:none; }}
.venue summary::before {{ content:"▸"; color:#3EC6E0; font-size:13px; transition:transform 0.15s; }}
.venue[open] summary::before {{ transform:rotate(90deg); }}
.race-count {{ font-size:12px; color:#5C7A90; font-weight:400; }}
.venue-body {{ padding:0 14px 14px; }}

.race-card {{ background:#14304A; border:1px solid #1E4560; border-radius:8px;
              padding:12px; margin-bottom:10px; }}
.race-card h3 {{ margin:0 0 10px; font-size:14px; }}
.formation {{ color:#3EC6E0; font-size:12.5px; margin-left:8px; }}

.boat-card {{ background:#0F2438; border:1px solid #1E4560; border-radius:8px;
              padding:10px 12px; margin-bottom:8px; }}
.boat-top {{ display:flex; align-items:center; gap:10px; margin-bottom:8px; }}
.lane-chip {{ width:32px; height:32px; min-width:32px; border-radius:7px; display:flex;
              align-items:center; justify-content:center; font-size:16px; font-weight:900;
              font-family: ui-monospace, "SF Mono", "Roboto Mono", monospace;
              border:1px solid rgba(255,255,255,0.15); }}
.boat-info {{ flex:1; min-width:0; }}
.boat-name-row {{ display:flex; align-items:center; gap:7px; flex-wrap:wrap; }}
.boat-name {{ font-size:14px; font-weight:700; color:#F5F9FC; }}
.class-badge {{ font-size:9.5px; font-weight:700; padding:1px 6px; border-radius:5px;
                 border:1px solid; font-family: ui-monospace, "SF Mono", "Roboto Mono", monospace; }}
.mark-badge {{ font-size:11px; font-weight:700; }}
.boat-meta {{ font-size:10px; color:#5C7A90; margin-top:2px;
              font-family: ui-monospace, "SF Mono", "Roboto Mono", monospace; }}
.boat-score {{ text-align:right; min-width:46px; }}
.score-val {{ font-size:16px; font-weight:900; color:#3EC6E0;
              font-family: ui-monospace, "SF Mono", "Roboto Mono", monospace; }}
.score-rank {{ font-size:10px; color:#5C7A90; }}

.stat-grid {{ display:grid; grid-template-columns:repeat(2, 1fr); gap:6px; }}
.stat-chip {{ background:#0A1F33; border:1px solid #16324A; border-radius:6px; padding:5px 8px; }}
.stat-label {{ font-size:9px; color:#5C7A90; margin-bottom:2px; }}
.stat-value {{ font-size:11.5px; color:#EAF2F8; font-weight:700;
               font-family: ui-monospace, "SF Mono", "Roboto Mono", monospace; }}

.disclaimer {{ font-size:11px; color:#5C7A90; margin-top:20px; line-height:1.6; max-width:520px; }}
</style>
</head><body>
<h1>競艇予想 {date_str}</h1>
<div class="updated">最終更新: {generated_at}</div>
{nav_html}
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
