# app_rss.py
# ------------------------------------------------------------
# RSS 수집 모듈 (Streamlit UI 컴포넌트 + RSS 파싱/정규화)
# 핵심: Streamlit rerun 구조 때문에 "RSS 불러오기" 결과를 session_state에 캐시해
#       다음 rerun(Workspace/Buffer 반영 버튼 클릭)에서도 값이 유지되게 함.
# ------------------------------------------------------------

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
import datetime as dt
import re

import streamlit as st

try:
    import requests
except Exception:
    requests = None

try:
    import feedparser
except Exception:
    feedparser = None


# ----------------------------
# 데이터 구조
# ----------------------------
@dataclass
class RssItem:
    title: str
    link: str
    published: str
    summary: str
    source: str
    fetched_at: str


def _now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _clean_text(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _extract_entry_text(entry) -> str:
    """
    feedparser entry에서 summary/content를 최대한 뽑아냄.
    """
    summary = ""
    if hasattr(entry, "summary"):
        summary = entry.summary or ""
    if not summary and hasattr(entry, "description"):
        summary = entry.description or ""

    # content 우선
    if hasattr(entry, "content") and entry.content:
        try:
            summary = entry.content[0].get("value", "") or summary
        except Exception:
            pass
    return _clean_text(summary)

def _extract_published(entry) -> str:
    if hasattr(entry, "published") and entry.published:
        return _clean_text(entry.published)
    if hasattr(entry, "updated") and entry.updated:
        return _clean_text(entry.updated)

    for k in ("published_parsed", "updated_parsed"):
        t = getattr(entry, k, None)
        if t:
            try:
                d = dt.datetime(*t[:6])
                return d.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

    return ""

def fetch_rss_items(feed_url: str, source_name: str, 
                    limit: int = 20, timeout: int = 10) -> List[RssItem]:
    """
    RSS URL을 파싱해 RssItem 리스트로 반환
    """
    if feedparser is None:
        raise RuntimeError("feedparser가 설치되어 있지 않습니다. pip install feedparser")

    fetched_at = _now_iso()

    # requests로 먼저 가져오면 깨지는 RSS가 줄어듦
    if requests is not None:
        resp = requests.get(feed_url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    else:
        parsed = feedparser.parse(feed_url)

    items: List[RssItem] = []
    entries = getattr(parsed, "entries", []) or []
    for e in entries[:limit]:
        title = _clean_text(getattr(e, "title", "") or "")
        link = _clean_text(getattr(e, "link", "") or "")
        published = _extract_published(e)
        summary = _extract_entry_text(e)

        items.append(
            RssItem(
                title=title,
                link=link,
                published=published,
                summary=summary,
                source=source_name,
                fetched_at=fetched_at,
            )
        )
    return items

def _items_to_workspace_text(items: List[RssItem], heading: str) -> str:
    """
    Workspace에 넣기 좋은 텍스트(마크다운 호환)
    """
    lines: List[str] = []
    lines.append(f"# {heading}")
    lines.append(f"- 생성시각: {items[0].fetched_at if items else _now_iso()}")
    lines.append("")

    for i, it in enumerate(items, start=1):
        lines.append(f"## {i}. {it.title}")
        if it.published:
            lines.append(f"- 일시: {it.published}")
        lines.append(f"- 출처: {it.source}")
        if it.link:
            lines.append(f"- 링크: {it.link}")
        if it.summary:
            lines.append("")
            lines.append(it.summary)
        lines.append("\n---\n")

    return "\n".join(lines).strip() + "\n"

def _items_to_buffer(items: List[RssItem]) -> List[Dict]:
    """
    app4.py의 buffer_items 형식으로 변환
    """
    out: List[Dict] = []
    for it in items:
        out.append(
            {
                "type": "rss_item",
                "title": it.title,
                "text": it.summary,  # LLM 입력용 본문(요약/설명/본문)
                "meta": {
                    "source": it.source,
                    "published": it.published,
                    "url": it.link,
                    "fetched_at": it.fetched_at,
                    "raw": asdict(it),
                },
            }
        )
    return out

# ------------------------------------------------------------
# Streamlit UI 컴포넌트
# ------------------------------------------------------------
DEFAULT_FEEDS: Dict[str, Dict[str, str]] = {

   # Google News 일반
    "Google RSS": {
        "한국 주요뉴스": "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko",
        "정치": "https://news.google.com/rss/search?q=정치&hl=ko&gl=KR&ceid=KR:ko",
        "경제": "https://news.google.com/rss/search?q=경제&hl=ko&gl=KR&ceid=KR:ko",
        "국제": "https://news.google.com/rss/search?q=국제&hl=ko&gl=KR&ceid=KR:ko",
        "AI": "https://news.google.com/rss/search?q=AI&hl=ko&gl=KR&ceid=KR:ko",
    },

    "연합뉴스": {
        "전체": "https://www.yna.co.kr/rss/news.xml",
        "정치": "https://www.yna.co.kr/rss/politics.xml",
        "경제": "https://www.yna.co.kr/rss/economy.xml",
        "사회": "https://www.yna.co.kr/rss/society.xml",
        "국제": "https://www.yna.co.kr/rss/international.xml",
        "문화": "https://www.yna.co.kr/rss/culture.xml",
    },

    "KBS World": {
        "국내(Domestic)": "http://world.kbs.co.kr/rss/rss_news.htm?lang=e&id=Dm",
        "국제(International)": "http://world.kbs.co.kr/rss/rss_news.htm?lang=e&id=In",
        "문화(Culture)": "http://world.kbs.co.kr/rss/rss_news.htm?lang=e&id=Cu",
        "경제(Economy)": "http://world.kbs.co.kr/rss/rss_news.htm?lang=e&id=Ec",
    },

    # BBC RSS 추가
    "BBC": {
        "Top": "http://feeds.bbci.co.uk/news/rss.xml",
        "World": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "Business": "http://feeds.bbci.co.uk/news/business/rss.xml",
        "Technology": "http://feeds.bbci.co.uk/news/technology/rss.xml",
    },

    # NHK RSS 추가
    "NHK": {
        "일본 주요뉴스": "https://www3.nhk.or.jp/rss/news/cat0.xml",
        "사회": "https://www3.nhk.or.jp/rss/news/cat1.xml",
        "정치": "https://www3.nhk.or.jp/rss/news/cat4.xml",
        "국제": "https://www3.nhk.or.jp/rss/news/cat6.xml",
        "경제": "https://www3.nhk.or.jp/rss/news/cat5.xml",
    },

    "New York Times": {
        "Home": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
        "World": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "US": "https://rss.nytimes.com/services/xml/rss/nyt/US.xml",
        "Business": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "Technology": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    },

    "The Guardian": {
        "World": "https://www.theguardian.com/world/rss",
        "US": "https://www.theguardian.com/us-news/rss",
        "Politics": "https://www.theguardian.com/politics/rss",
        "Business": "https://www.theguardian.com/business/rss",
        "Technology": "https://www.theguardian.com/technology/rss",
    },

    "Le Monde": {
        "English": "https://www.lemonde.fr/en/rss/une.xml",
        "International": "https://www.lemonde.fr/en/international/rss_full.xml",
        "Politics": "https://www.lemonde.fr/en/politics/rss_full.xml",
        "Economy": "https://www.lemonde.fr/en/economy/rss_full.xml",
    },

    "Reuters (via Google News)": {
        "Top": "https://news.google.com/rss/search?q=site:reuters.com&hl=en-US&gl=US&ceid=US:en",
        "World": "https://news.google.com/rss/search?q=site:reuters.com+world&hl=en-US&gl=US&ceid=US:en",
        "Business": "https://news.google.com/rss/search?q=site:reuters.com+business&hl=en-US&gl=US&ceid=US:en",
        "Tech": "https://news.google.com/rss/search?q=site:reuters.com+technology&hl=en-US&gl=US&ceid=US:en",
        "Korea": "https://news.google.com/rss/search?q=site:reuters.com+korea&hl=en-US&gl=US&ceid=US:en",
    },

    "AP (via Google News)": {
        "Top": "https://news.google.com/rss/search?q=site:apnews.com&hl=en-US&gl=US&ceid=US:en",
        "World": "https://news.google.com/rss/search?q=site:apnews.com+world&hl=en-US&gl=US&ceid=US:en",
        "Politics": "https://news.google.com/rss/search?q=site:apnews.com+politics&hl=en-US&gl=US&ceid=US:en",
        "Business": "https://news.google.com/rss/search?q=site:apnews.com+business&hl=en-US&gl=US&ceid=US:en",
        "Tech": "https://news.google.com/rss/search?q=site:apnews.com+technology&hl=en-US&gl=US&ceid=US:en",
    },

}

def _init_rss_cache() -> None:
    """
    Streamlit rerun 대비: 마지막 RSS 결과를 캐시해둠
    """
    if "rss_last_ws_text" not in st.session_state:
        st.session_state.rss_last_ws_text = None
    if "rss_last_buffer" not in st.session_state:
        st.session_state.rss_last_buffer = []
    if "rss_last_info" not in st.session_state:
        st.session_state.rss_last_info = ""

def clear_rss_cache() -> None:
    st.session_state.rss_last_ws_text = None
    st.session_state.rss_last_buffer = []
    st.session_state.rss_last_info = ""

def render_rss_panel() -> Tuple[Optional[str], List[Dict]]:
    """
    RSS 패널을 렌더링하고,
    - workspace에 추가할 텍스트(str) 1개 (없으면 None)
    - buffer_items(list[dict]) (없으면 [])를 반환

    중요:
    - 'RSS 불러오기' 클릭 후 rerun이 일어나도,
      st.session_state.rss_last_* 캐시를 통해 값이 유지됨.
    """
    st.subheader("📰 RSS 수집")

    _init_rss_cache()

    if feedparser is None:
        st.error("feedparser 미설치: `pip install feedparser`")
        return st.session_state.rss_last_ws_text, st.session_state.rss_last_buffer

    top_row = st.columns([2, 2, 1, 1])
    with top_row[0]:
        provider = st.selectbox("제공처", list(DEFAULT_FEEDS.keys()), index=0)
    with top_row[1]:
        category = st.selectbox("카테고리", list(DEFAULT_FEEDS[provider].keys()), index=0)
    with top_row[2]:
        limit = st.number_input("개수", min_value=5, max_value=50, value=10, step=5)
    with top_row[3]:
        if st.button("RSS 캐시 비우기", use_container_width=True):
            clear_rss_cache()
            st.success("RSS 캐시를 비웠습니다.")
            # 캐시 비운 후 즉시 반영되도록 rerun
            st.rerun()

    feed_url = DEFAULT_FEEDS[provider][category]
    st.caption(f"RSS URL: {feed_url}")

    with st.expander("직접 RSS URL 입력(선택)"):
        custom_url = st.text_input("RSS URL", value="", key="rss_custom_url")
        custom_source = st.text_input("출처명", value="Custom RSS", key="rss_custom_source")
        use_custom = st.checkbox("직접 입력 URL 사용", value=False, key="rss_use_custom")
        if use_custom and custom_url.strip():
            feed_url = custom_url.strip()
            provider = (custom_source.strip() or "Custom RSS")
            category = "Custom"

    do_fetch = st.button("RSS 불러오기", use_container_width=True)
    # 새로 불러오지 않으면 "마지막 캐시"를 그대로 반환
    if not do_fetch:
        # 캐시가 있으면 상태 표시
        if st.session_state.rss_last_info:
            st.success(st.session_state.rss_last_info)
            st.info("수집된 항목은 아래 미리보기로 확인한 뒤, Workspace/Buffer에 반영하세요.")
        return st.session_state.rss_last_ws_text, st.session_state.rss_last_buffer

    # RSS 불러오기 실행
    try:
        with st.spinner("RSS 파싱 중..."):
            items = fetch_rss_items(feed_url, source_name=provider, limit=int(limit))
    except Exception as e:
        st.error(f"RSS 수집 실패: {e}")
        return st.session_state.rss_last_ws_text, st.session_state.rss_last_buffer

    if not items:
        st.warning("가져온 항목이 없습니다.")
        return st.session_state.rss_last_ws_text, st.session_state.rss_last_buffer

    st.success(f"{len(items)}건 수집 완료")
    st.info("수집된 항목은 아래 미리보기로 확인한 뒤, Workspace/Buffer에 반영하세요.")

    # 미리보기(상위 5개)
    with st.expander("미리보기(상위 5개)", expanded=True):
        for it in items[:5]:
            st.markdown(f"**{it.title}**")
            if it.published:
                st.caption(f"일시: {it.published}")
            if it.link:
                st.write(it.link)
            if it.summary:
                st.write(it.summary[:400] + ("..." if len(it.summary) > 400 else ""))
            st.divider()

    heading = f"{provider} RSS 수집({category})"
    ws_text = _items_to_workspace_text(items, heading=heading)
    buffer_items = _items_to_buffer(items)

    # 캐시 저장(핵심)
    st.session_state.rss_last_ws_text = ws_text
    st.session_state.rss_last_buffer = buffer_items
    st.session_state.rss_last_info = f"{provider}/{category} - {len(items)}건 (수집: {items[0].fetched_at})"

    return ws_text, buffer_items
