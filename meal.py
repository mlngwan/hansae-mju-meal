import os
import re
import datetime as dt
from collections import defaultdict
import html as html_lib

import requests
from bs4 import BeautifulSoup

# 크롤링 대상 페이지
URL = "https://www.mju.ac.kr/diet/mjukr/7/view.do"


# ---------- 1. HTML 가져오기 ----------

def fetch_html() -> str:
    """학식 페이지 HTML 가져오기"""
    try:
        resp = requests.get(
            URL,
            timeout=10,
            headers={"User-Agent": "MJU-MealBot/1.0 (+github.com)"}
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"[ERROR] fetch_html failed: {e}")
        return ""


# ---------- 2. HTML에서 주간 범위 + 테이블 파싱 ----------

def parse_html(html: str):
    """
    HTML을 DOM 기준으로 파싱해서
    (week_range, menus) 튜플을 리턴한다.

    menus 형식:
      {
        "md": "11.10",
        "weekday": "월",
        "meal": "점심" or "저녁",
        "title": "메인 메뉴 제목",
        "items": [...반찬/부메뉴 리스트...],
        "info": "기타정보"
      }
    """
    soup = BeautifulSoup(html, "html.parser")

    # 주간 범위: 상단 '11.10 ~ 11.16'
    week_range = None
    date_el = soup.select_one("div.scedule .date")
    if date_el:
        week_range = date_el.get_text(strip=True)
        print(f"[INFO] Week range: {week_range}")
    else:
        print("[WARN] Week range (.scedule .date) not found")

    # 식단 테이블 찾기
    table = soup.find("table", id="listTable")
    if not table:
        # id가 없으면 summary 기준으로
        table = soup.find("table", summary=lambda s: s and "일주일간의 식단을" in s)
    if not table:
        # 그래도 못 찾으면 caption 텍스트 확인
        for t in soup.find_all("table"):
            cap = t.find("caption")
            if cap and "일주일간 식단 안내" in cap.get_text():
                table = t
                break

    if not table:
        print("[ERROR] 메뉴 테이블을 찾지 못했습니다.")
        return week_range, []

    print("[INFO] 메뉴 테이블 발견")

    tbody = table.find("tbody") or table

    menus = []
    current_md = None
    current_weekday = None

    for tr in tbody.find_all("tr"):
        # 빈 tr 스킵
        if not tr.find("td") and not tr.find("th"):
            continue

        # 날짜/요일 (예: "11.10  (월)")
        th = tr.find("th")
        if th:
            date_text = th.get_text(" ", strip=True)  # 공백 기준으로 정리
            m = re.search(r"(\d{2}\.\d{2})\s*\((.)\)", date_text)
            if m:
                current_md = m.group(1)
                current_weekday = m.group(2)
            else:
                current_md = date_text.strip()
                current_weekday = ""

        tds = tr.find_all("td")
        if len(tds) < 4:
            # 예상 구조: [식단구분, 식단제목, 식단내용, 기타정보]
            continue

        meal_type = tds[0].get_text(strip=True)  # 점심 / 저녁
        title = tds[1].get_text(strip=True)      # 보통 "-"
        content_td = tds[2]                      # 메뉴 상세 (br 태그 포함)
        info = tds[3].get_text(strip=True)       # 보통 "-"

        # <br/> 기준으로 메뉴 줄 나누기
        menu_text = content_td.get_text("\n", strip=True)
        items = [line.strip() for line in menu_text.split("\n") if line.strip()]

        # 메뉴 제목이 '-'인 경우, 첫 번째 상세 메뉴를 제목으로 사용
        if title == "-" and items:
            title = items.pop(0)

        menus.append({
            "md": current_md,           # "11.10"
            "weekday": current_weekday, # "월"
            "meal": meal_type,          # "점심" / "저녁"
            "title": title,             # 메인 메뉴
            "items": items,             # 반찬 리스트
            "info": info,               # 기타정보
        })

    print(f"[DEBUG] Parsed {len(menus)} menu rows from table")
    return week_range, menus


# ---------- 3. HTML 생성 ----------

def generate_html(week_range, menus):
    # 마지막 업데이트 시간 (KST 기준, timezone-aware)
    updated_kst = (
        dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)
    ).strftime("%Y-%m-%d %H:%M")

    grouped = defaultdict(list)
    for m in menus:
        grouped[(m["md"], m["weekday"])].append(m)

    day_keys = sorted(grouped.keys(), key=lambda x: x[0] or "")

    def esc(s: str) -> str:
        return html_lib.escape(s if s is not None else "", quote=True)

    parts: list[str] = []
    parts.append("<!doctype html>")
    parts.append('<html lang="ko">')
    parts.append("<head>")
    parts.append('  <meta charset="utf-8">')
    parts.append("  <title>명지대 자연캠 교직원식당 식단</title>")
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    # Pretendard 폰트 링크
    parts.append(
        '  <link rel="stylesheet" '
        'href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css">'
    )
    parts.append("  <style>")
    parts.append(
        r"""
:root {
  --mju-blue: #005a9c;
  --mju-blue-light: #e3f2fd;
  --card-radius: 10px;
}

/* Reset-ish */
* { box-sizing: border-box; }

body { 
  font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
               "Helvetica Neue", Arial, "Noto Sans", sans-serif, "Apple Color Emoji",
               "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji";
  max-width: 1000px; 
  margin: 0 auto; 
  padding: 16px; 
  background: #f0f2f5; 
  color: #333;
}

h1 { 
  font-size: 2.0rem; 
  color: #2c3e50; 
  margin-bottom: 0.5rem; 
  text-align: center;
}

.meta { 
  color: #7f8c8d; 
  font-size: 0.9rem; 
  text-align: center; 
  margin-bottom: 1.0rem; 
  line-height: 1.4;
}

.today-summary {
  font-size: 0.9rem;
  margin: 0 auto 1.2rem auto;
  padding: 8px 10px;
  border-radius: 8px;
  background: #fff8e1;
  border: 1px solid #ffe082;
  max-width: 600px;
}

/* 전체 레이아웃: 상단/좌측 요일 탭 + 우측 패널 */
.week-layout {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 요일 탭 영역 */
.day-tabs {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 6px;
  margin-bottom: 10px;  /* 살짝 더 여유 */
  border-bottom: 1px solid #e0e0e0;
}

.day-tabs::-webkit-scrollbar {
  height: 4px;
}
.day-tabs::-webkit-scrollbar-thumb {
  background: #ccc;
  border-radius: 999px;
}

/* 요일 탭 버튼 (크기 줄인 버전) */
.day-tab {
  flex: 0 0 auto;
  border: 1px solid #dde1e7;
  border-radius: 8px;       /* 살짝 둥근 직사각형 */
  padding: 4px 8px 6px 8px;
  background: #ffffff;
  cursor: pointer;
  font-size: 0.85rem;
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  min-width: 64px;
  transition: background 0.15s ease, border-color 0.15s ease,
              transform 0.1s, box-shadow 0.1s;
  color: #333;
}

.day-tab:hover {
  background: #f5f7fb;
  transform: translateY(-1px);
}

.day-tab:active {
  transform: translateY(0);
  box-shadow: inset 0 1px 2px rgba(0,0,0,0.08);
}

.day-tab .weekday {
  font-weight: 600;
  font-size: 0.80rem;
  padding: 2px 8px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #111827;
}

.day-tab .date {
  font-size: 0.72rem;
  color: #6b7280;
}

/* 오늘 요일 탭 표시 (선택 안 되어 있을 때) */
.day-tab.is-today {
  border-color: #ef4444;          /* 빨간 테두리 */
  background: #fff5f5;
}
.day-tab.is-today .weekday {
  background: #fee2e2;
  color: #b91c1c;
}

/* 오늘 탭에 은은한 pulse 애니메이션 (선택 안 된 상태일 때만) */
@keyframes pulse-border {
  0%   { box-shadow: 0 0 0 0 rgba(239,68,68,0.45); }
  100% { box-shadow: 0 0 0 7px rgba(239,68,68,0); }
}

.day-tab.is-today:not(.active) {
  animation: pulse-border 1.6s infinite;
}

/* 현재 선택된 요일 탭(누른 상태) */
.day-tab.active {
  background: var(--mju-blue);
  border-color: var(--mju-blue);
  color: #ffffff;
}
.day-tab.active .weekday {
  background: #ffffff;
  color: var(--mju-blue);
}
.day-tab.active .date {
  color: #dbeafe;
}

/* "오늘 + 선택됨"인 경우 → 파란 배경 + 빨간 테두리 */
.day-tab.is-today.active {
  border-color: #ef4444;            /* 얇은 빨간 테두리 */
  box-shadow: 0 0 0 1px #ef4444;    /* 살짝 더 강조 */
  animation: none;                  /* pulse 중단 */
}

/* 요일별 패널 영역 */
.day-panels {
  margin-top: 12px;   /* 탭 아래 여백 늘림 (윗부분 잘려 보이는 느낌 완화) */
}

/* 패널 입장 애니메이션 */
@keyframes fade-slide {
  0%   { opacity: 0; transform: translateY(6px); }
  100% { opacity: 1; transform: translateY(0); }
}

.day-panel {
  display: none;
}

.day-panel.active {
  display: block;
  animation: fade-slide 0.28s ease-out;  /* 전환 속도 살짝 느리게 */
}

.day-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 10px;  /* 헤더 아래도 여유 조금 추가 */
}

.day-panel-header h2 {
  margin: 0;
  font-size: 1.15rem;
}

.day-panel-header .sub {
  font-size: 0.8rem;
  color: #777;
}

/* 끼니 카드 */
.meal-card {
  background: #fff;
  border-radius: var(--card-radius);
  padding: 10px 12px;
  margin-bottom: 10px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  border: 1px solid #e5e7eb;
  position: relative;
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}

/* 카드 hover 애니메이션 */
.meal-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 10px rgba(0,0,0,0.12);
}

/* 상단 색띠로 점심/저녁 구분 */
.meal-card::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  height: 3px;
  width: 100%;
  border-radius: var(--card-radius) var(--card-radius) 0 0;
  background: #e5e7eb;
}
.meal-card.lunch::before {
  background: #facc15;  /* 노랑 (점심) */
}
.meal-card.dinner::before {
  background: #6366f1;  /* 보라 (저녁) */
}

.meal-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.meal-type {
  font-weight: 600;
  font-size: 0.95rem;
  display: flex;
  align-items: center;
  gap: 4px;
}

.meal-type .emoji {
  font-size: 1.1rem;
}

.meal-info {
  font-size: 0.75rem;
  color: #999;
}

/* 메인디쉬 따로 박스 없이, 첫 줄만 살짝 강조 */
.meal-items {
  margin: 4px 0 0 0;
  padding-left: 18px;
  font-size: 0.9rem;
}

.meal-items li {
  margin: 2px 0;
  color: #333;
}

.meal-items li:first-child {
  font-weight: 600;
  color: #111827;
}

.no-menu {
  color: #999;
  font-size: 0.9rem;
}

/* 하단 푸터 */
footer {
  margin-top: 20px;
  font-size: 0.8rem;
  color: #777;
  text-align: center;
}

/* 데스크톱: 좌측 탭 / 우측 내용 2단 */
@media (min-width: 900px) {
  .week-layout {
    flex-direction: row;
    align-items: flex-start;
  }

  .day-tabs {
    flex-direction: column;
    border-bottom: none;
    border-right: 1px solid #e0e0e0;
    padding-right: 8px;
    margin-right: 8px;
    max-width: 150px;
  }

  .day-tab {
    width: 100%;
  }

  .day-panels {
    flex: 1;
    padding-left: 8px;
  }
}
"""
    )
    parts.append("  </style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append("<h1>🍽️ 교직원 식단 메뉴</h1>")

    meta = (
        f"<span>{esc(week_range)}</span> · 마지막 업데이트: {updated_kst} (KST)"
        if week_range
        else f"마지막 업데이트: {updated_kst} (KST)"
    )
    parts.append(f'<p class="meta">{meta}</p>')

    parts.append('<div id="today-summary" class="today-summary"></div>')

    parts.append('<div class="week-layout">')

    # 요일 탭
    parts.append('<div class="day-tabs" id="day-tabs">')
    for (md, weekday) in day_keys:
        if not md:
            continue
        parts.append(
            f'<button class="day-tab" type="button" data-date="{esc(md)}">'
            f'<span class="weekday">{esc(weekday)}요일</span>'
            f'<span class="date">{esc(md)}</span>'
            f"</button>"
        )
    parts.append("</div>")  # .day-tabs

    # 요일별 패널
    parts.append('<div class="day-panels" id="day-panels">')
    for (md, weekday) in day_keys:
        if not md:
            continue

        parts.append(f'<section class="day-panel" data-date="{esc(md)}">')
        parts.append('<div class="day-panel-header">')
        parts.append(f'<h2>{esc(md)} {esc(weekday)}요일</h2>')
        parts.append('<span class="sub">점심 · 저녁 식단</span>')
        parts.append("</div>")

        day_menus = grouped[(md, weekday)]
        if not day_menus:
            parts.append('<p class="no-menu">등록된 메뉴가 없습니다.</p>')
        else:
            for m in day_menus:
                meal_emoji = "☀️" if m["meal"] == "점심" else "🌙"
                meal_class = "lunch" if m["meal"] == "점심" else "dinner"
                parts.append(f'<article class="meal-card {meal_class}" data-date="{esc(md)}">')
                parts.append('<div class="meal-card-header">')
                parts.append('<div class="meal-type">')
                parts.append(f'<span class="emoji">{meal_emoji}</span>')
                parts.append(f'<span class="label">{esc(m["meal"])}</span>')
                parts.append('</div>')  # .meal-type

                info = (m.get("info") or "").strip()
                if info and info != "-":
                    parts.append(f'<div class="meal-info">{esc(info)}</div>')

                parts.append('</div>')  # .meal-card-header

                # 메인디쉬 + 나머지 메뉴 하나 리스트에 넣기
                title = (m.get("title") or "").strip()
                items = m.get("items") or []

                full_items = []
                if title and title != "-":
                    full_items.append(title)
                full_items.extend(items)

                if full_items:
                    parts.append('<ul class="meal-items">')
                    for item in full_items:
                        parts.append(f"<li>{esc(item)}</li>")
                    parts.append("</ul>")
                else:
                    parts.append('<p class="no-menu">세부 메뉴 없음</p>')

                parts.append("</article>")  # .meal-card

        parts.append("</section>")  # .day-panel
    parts.append("</div>")  # .day-panels

    parts.append("</div>")  # .week-layout

    parts.append('<footer>made by 권민관 for Hansae</footer>')

    # JS: 요일 탭 동작 + 오늘 요일 자동 선택
    parts.append(
        r"""
<script>
document.addEventListener('DOMContentLoaded', function() {
    try {
        const tabs = Array.from(document.querySelectorAll('.day-tab'));
        const panels = Array.from(document.querySelectorAll('.day-panel'));
        const summary = document.getElementById('today-summary');

        if (tabs.length === 0 || panels.length === 0) {
            if (summary) {
                summary.textContent = '이번 주 식단 정보가 없습니다.';
            }
            return;
        }

        // KST 기준 오늘 날짜 계산 → "MM.DD"
        const now = new Date();
        const utc = now.getTime() + now.getTimezoneOffset() * 60000;
        const kst = new Date(utc + 9 * 3600 * 1000);
        const month = String(kst.getMonth() + 1).padStart(2, '0');
        const day = String(kst.getDate()).padStart(2, '0');
        const todayMD = `${month}.${day}`;

        function setActive(dateStr) {
            tabs.forEach(tab => {
                tab.classList.toggle('active', tab.dataset.date === dateStr);
            });
            panels.forEach(panel => {
                panel.classList.toggle('active', panel.dataset.date === dateStr);
            });
        }

        // 기본 활성 날짜: 오늘이 있으면 오늘, 없으면 첫 번째
        let activeDate = null;
        const todayTab = document.querySelector(`.day-tab[data-date="${todayMD}"]`);
        if (todayTab) {
            activeDate = todayMD;
        } else {
            activeDate = tabs[0].dataset.date;
        }

        setActive(activeDate);

        // 오늘 요일 탭 표시 + 안내 문구
        if (todayTab) {
            todayTab.classList.add('is-today');
            if (summary) {
                summary.textContent = `오늘은 ${month}월 ${day}일입니다. 해당 요일은 빨간색으로 표시되어 있습니다!`;
            }
        } else if (summary) {
            summary.textContent = '오늘 날짜는 이번 주 식단 범위에 없어서, 첫 번째 요일이 기본으로 선택되었습니다.';
        }

        // 탭 클릭 이벤트
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const dateStr = tab.dataset.date;
                setActive(dateStr);
            });
        });
    } catch (e) {
        console.error('Error initializing tabs:', e);
    }
});
</script>
"""
    )

    parts.append("</body></html>")
    return "\n".join(parts)


# ---------- 4. 엔트리 포인트 ----------

def main():
    html = fetch_html()
    if not html:
        print("[ERROR] No HTML, abort.")
        return

    week_range, menus = parse_html(html)

    os.makedirs("public", exist_ok=True)
    out_path = os.path.join("public", "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(generate_html(week_range, menus))

    print(f"[INFO] Generated {out_path} (week={week_range}, menus={len(menus)})")


if __name__ == "__main__":
    main()
