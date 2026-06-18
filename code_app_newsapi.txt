# app_newsapi.py
# streamlit cloud 용(api key 관련 코드 수정)

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
import datetime as dt
import re
import os

import streamlit as st

try:
    import requests
except Exception:
    requests = None


NEWSAPI_BASE = "https://newsapi.org/v2"


@dataclass
class NewsApiItem:
    title: str
    url: str
    published: str
    source: str
    author: str
    description: str
    content: str
    fetched_at: str
    query_info: Dict


def _now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def _require_requests() -> None:
    if requests is None:
        raise RuntimeError("requests가 설치되어 있지 않습니다. pip install requests")


def get_newsapi_key(passed_key: Optional[str] = None) -> str:
    """
    NewsAPI 키를 안전하게 읽는다.

    우선순위:
    1. render_newsapi_panel(newsapi_key)로 전달된 값
    2. Streamlit Cloud Secrets의 NEWSAPI_KEY
    3. 로컬 .env / 환경변수의 NEWSAPI_KEY
    """
    try:
        secret_key = str(st.secrets.get("NEWSAPI_KEY", "")).strip()
    except Exception:
        secret_key = ""

    return (
        (passed_key or "").strip()
        or secret_key
        or os.getenv("NEWSAPI_KEY", "").strip()
    )


def fetch_newsapi_json(api_key: str, params: Dict, timeout: int = 15) -> Dict:
    """
    Everything 전용 호출:
    GET https://newsapi.org/v2/everything
    """
    _require_requests()

    api_key = get_newsapi_key(api_key)

    if not api_key:
        raise ValueError("NEWSAPI_KEY가 비어 있습니다.")

    url = f"{NEWSAPI_BASE}/everything"
    headers = {"X-Api-Key": api_key}

    resp = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=timeout,
    )

    resp.raise_for_status()
    return resp.json()


def normalize_articles(payload: Dict, query_info: Dict, limit: int) -> List[NewsApiItem]:
    fetched_at = _now_iso()
    articles = payload.get("articles") or []
    out: List[NewsApiItem] = []

    for a in articles[:limit]:
        src = a.get("source") or {}

        out.append(
            NewsApiItem(
                title=_clean(a.get("title") or ""),
                url=_clean(a.get("url") or ""),
                published=_clean(a.get("publishedAt") or ""),
                source=_clean(src.get("name") or ""),
                author=_clean(a.get("author") or ""),
                description=_clean(a.get("description") or ""),
                content=_clean(a.get("content") or ""),
                fetched_at=fetched_at,
                query_info=query_info,
            )
        )

    return out


def items_to_workspace_text(items: List[NewsApiItem], heading: str) -> str:
    lines: List[str] = []

    lines.append(f"# {heading}")
    lines.append(f"- 생성시각: {items[0].fetched_at if items else _now_iso()}")
    lines.append("")

    for i, it in enumerate(items, start=1):
        lines.append(f"## {i}. {it.title}")

        if it.published:
            lines.append(f"- 일시: {it.published}")
        if it.source:
            lines.append(f"- 출처: {it.source}")
        if it.url:
            lines.append(f"- 링크: {it.url}")

        if it.description:
            lines.append("")
            lines.append(it.description)

        if it.content:
            lines.append("")
            lines.append(it.content)

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def items_to_buffer(items: List[NewsApiItem]) -> List[Dict]:
    out: List[Dict] = []

    for it in items:
        parts: List[str] = []

        if it.description:
            parts.append(it.description)

        if it.content and it.content not in parts:
            parts.append(it.content)

        text = "\n\n".join(parts).strip()

        out.append(
            {
                "type": "newsapi_item",
                "title": it.title,
                "text": text,
                "meta": {
                    "source": it.source,
                    "author": it.author,
                    "published": it.published,
                    "url": it.url,
                    "fetched_at": it.fetched_at,
                    "query_info": it.query_info,
                    "raw": asdict(it),
                },
            }
        )

    return out


def _init_cache() -> None:
    if "newsapi_last_ws_text" not in st.session_state:
        st.session_state.newsapi_last_ws_text = None

    if "newsapi_last_buffer" not in st.session_state:
        st.session_state.newsapi_last_buffer = []

    if "newsapi_last_info" not in st.session_state:
        st.session_state.newsapi_last_info = ""

    if "newsapi_last_items_preview" not in st.session_state:
        st.session_state.newsapi_last_items_preview = []


def clear_newsapi_cache() -> None:
    st.session_state.newsapi_last_ws_text = None
    st.session_state.newsapi_last_buffer = []
    st.session_state.newsapi_last_info = ""
    st.session_state.newsapi_last_items_preview = []


def render_newsapi_panel(newsapi_key: str = "") -> Tuple[Optional[str], List[Dict]]:
    """
    반환:
    - workspace_text_or_none: Workspace에 추가할 텍스트
    - buffer_items: Buffer에 추가할 항목 list[dict]
    """
    st.subheader("🧩 NewsAPI 수집 (Everything: 검색 전용)")

    _init_cache()

    newsapi_key = get_newsapi_key(newsapi_key)

    if not newsapi_key:
        st.warning("NEWSAPI_KEY가 없습니다. Streamlit Secrets 또는 .env에 NEWSAPI_KEY를 설정하세요.")
        return st.session_state.newsapi_last_ws_text, st.session_state.newsapi_last_buffer

    row1 = st.columns([3, 2, 2, 1])

    with row1[0]:
        q = st.text_input(
            "검색어(q) *필수",
            value="",
            key="newsapi_q",
            help="예: 정치, 경제 OR 금융, 국제 OR 외교 OR 해외",
        )

    with row1[1]:
        language = st.selectbox(
            "언어",
            ["", "ko", "en", "ja", "zh", "de", "fr"],
            index=1,
            key="newsapi_language",
        )

    with row1[2]:
        sort_by = st.selectbox(
            "정렬",
            ["relevancy", "publishedAt", "popularity"],
            index=0,
            key="newsapi_sort_by",
        )

    with row1[3]:
        limit = st.number_input(
            "개수",
            min_value=5,
            max_value=50,
            value=10,
            step=5,
            key="newsapi_limit",
        )

    row2 = st.columns([1, 1, 2])

    with row2[0]:
        do_fetch = st.button(
            "NewsAPI 불러오기",
            use_container_width=True,
            key="newsapi_fetch",
        )

    with row2[1]:
        if st.button(
            "캐시 비우기",
            use_container_width=True,
            key="newsapi_clear_cache",
        ):
            clear_newsapi_cache()
            st.success("NewsAPI 캐시를 비웠습니다.")
            st.rerun()

    with row2[2]:
        st.caption("Everything(검색) 기반 수집입니다. 카테고리/국가 개념을 쓰지 않습니다.")

    with st.expander("기간/도메인/소스(옵션)"):
        if "newsapi_from_dt" not in st.session_state:
            st.session_state.newsapi_from_dt = None

        if "newsapi_to_dt" not in st.session_state:
            st.session_state.newsapi_to_dt = None

        b1, b2, b3, b4 = st.columns([1, 1, 1, 1.2])

        def _set_range(days_back: int) -> None:
            today = dt.date.today()
            st.session_state.newsapi_from_dt = today - dt.timedelta(days=days_back)
            st.session_state.newsapi_to_dt = today
            st.rerun()

        with b1:
            if st.button("최근 24시간", use_container_width=True, key="newsapi_btn_24h"):
                _set_range(1)

        with b2:
            if st.button("최근 3일", use_container_width=True, key="newsapi_btn_3d"):
                _set_range(3)

        with b3:
            if st.button("최근 7일", use_container_width=True, key="newsapi_btn_7d"):
                _set_range(7)

        with b4:
            if st.button("기간 해제", use_container_width=True, key="newsapi_btn_clear_range"):
                st.session_state.newsapi_from_dt = None
                st.session_state.newsapi_to_dt = None
                st.rerun()

        st.caption("※ 기간은 캘린더로 직접 선택할 수 있습니다. from ≤ to 권장")

        cA, cB = st.columns(2)

        with cA:
            from_dt = st.date_input(
                "from (캘린더)",
                value=st.session_state.newsapi_from_dt,
                key="newsapi_from_dt",
            )

            domains = st.text_input(
                "domains (콤마구분)",
                value="",
                key="newsapi_domains",
                help="예: reuters.com, apnews.com",
            )

        with cB:
            to_dt = st.date_input(
                "to (캘린더)",
                value=st.session_state.newsapi_to_dt,
                key="newsapi_to_dt",
            )

            sources = st.text_input(
                "sources (콤마구분)",
                value="",
                key="newsapi_sources",
                help="NewsAPI 소스 ID. 보통 domains 사용을 권장합니다.",
            )

        if from_dt and to_dt and from_dt > to_dt:
            from_dt, to_dt = to_dt, from_dt
            st.session_state.newsapi_from_dt = from_dt
            st.session_state.newsapi_to_dt = to_dt
            st.info("from/to가 뒤바뀌어 자동으로 교정했습니다.")

        from_date = from_dt.isoformat() if from_dt else ""
        to_date = to_dt.isoformat() if to_dt else ""

    if not do_fetch:
        if st.session_state.newsapi_last_info:
            st.success(st.session_state.newsapi_last_info)
            st.info("수집된 항목은 아래 미리보기로 확인한 뒤, Workspace/Buffer에 반영하세요.")

            with st.expander("미리보기(상위 5개)", expanded=False):
                for it in st.session_state.newsapi_last_items_preview[:5]:
                    st.markdown(f"**{it.get('title', '')}**")

                    if it.get("published"):
                        st.caption(f"일시: {it.get('published')}")

                    if it.get("source"):
                        st.caption(f"출처: {it.get('source')}")

                    if it.get("url"):
                        st.write(it.get("url"))

                    desc = it.get("description") or ""

                    if desc:
                        st.write(desc[:400] + ("..." if len(desc) > 400 else ""))

                    st.divider()

        return st.session_state.newsapi_last_ws_text, st.session_state.newsapi_last_buffer

    try:
        if not q.strip():
            st.error("검색어(q)는 필수입니다.")
            return st.session_state.newsapi_last_ws_text, st.session_state.newsapi_last_buffer

        params: Dict = {
            "q": q.strip(),
            "pageSize": int(limit),
            "sortBy": sort_by,
        }

        query_info: Dict = {
            "mode": "everything",
            "q": q.strip(),
            "sortBy": sort_by,
        }

        if language:
            params["language"] = language
            query_info["language"] = language

        if from_date:
            params["from"] = from_date
            query_info["from"] = from_date

        if to_date:
            params["to"] = to_date
            query_info["to"] = to_date

        if (domains or "").strip():
            params["domains"] = domains.strip()
            query_info["domains"] = domains.strip()

        if (sources or "").strip():
            params["sources"] = sources.strip()
            query_info["sources"] = sources.strip()

        with st.spinner("NewsAPI 호출 중..."):
            payload = fetch_newsapi_json(newsapi_key, params=params)

        if payload.get("status") != "ok":
            st.error(f"NewsAPI 오류: {payload}")
            return st.session_state.newsapi_last_ws_text, st.session_state.newsapi_last_buffer

        items = normalize_articles(
            payload,
            query_info=query_info,
            limit=int(limit),
        )

        if not items:
            st.warning("가져온 항목이 없습니다. 검색어/기간/언어/도메인 조건을 조정해보세요.")
            return st.session_state.newsapi_last_ws_text, st.session_state.newsapi_last_buffer

        st.success(f"{len(items)}건 수집 완료")
        st.info("수집된 항목은 아래 미리보기로 확인한 뒤, Workspace/Buffer에 반영하세요.")

        preview_list: List[Dict] = []

        for it in items:
            preview_list.append(
                {
                    "title": it.title,
                    "published": it.published,
                    "source": it.source,
                    "url": it.url,
                    "description": it.description,
                }
            )

        st.session_state.newsapi_last_items_preview = preview_list

        with st.expander("미리보기(상위 5개)", expanded=True):
            for it in items[:5]:
                st.markdown(f"**{it.title}**")

                if it.published:
                    st.caption(f"일시: {it.published}")

                if it.source:
                    st.caption(f"출처: {it.source}")

                if it.url:
                    st.write(it.url)

                if it.description:
                    st.write(it.description[:400] + ("..." if len(it.description) > 400 else ""))

                st.divider()

        heading = f"NewsAPI 검색 수집: {q.strip()}"
        ws_text = items_to_workspace_text(items, heading=heading)
        buffer_items = items_to_buffer(items)

        st.session_state.newsapi_last_ws_text = ws_text
        st.session_state.newsapi_last_buffer = buffer_items
        st.session_state.newsapi_last_info = (
            f"NewsAPI/Everything - {len(items)}건 "
            f"(q={q.strip()} / 수집: {items[0].fetched_at})"
        )

        return ws_text, buffer_items

    except Exception as e:
        st.error(
            "NewsAPI 수집 실패:\n"
            f"- {e}\n\n"
            "체크 포인트:\n"
            "- NEWSAPI_KEY 유효 여부\n"
            "- Streamlit Secrets 저장 여부\n"
            "- 앱 Reboot 여부\n"
            "- 네트워크/방화벽 환경\n"
            "- 검색어(q)/기간/언어 조건"
        )

        return st.session_state.newsapi_last_ws_text, st.session_state.newsapi_last_buffer