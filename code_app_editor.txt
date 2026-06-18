# app_editor.py
# ------------------------------------------------------------
# streamlit cloud 용(api key 관련 코드 수정)
# AI 취재·정리 작업판 - 통합형
# - Text/File: Workspace 중심
# - RSS/NewsAPI: Buffer 중심
# - Draft 선택: 번호 입력이 아니라 제목 선택 방식
# - SYSTEM_RULES / USER_TEMPLATE 화면 수정 가능
# - ⓪ 수집 / ① 자료 확인 / ② Draft 생성 / ③ Draft 편집 모두 접기·펼치기 방식
# - role(system/user) 값 화면 표출
# - Workspace / Buffer 타입 오류 방어
# - Streamlit Cloud Secrets 지원
# ------------------------------------------------------------

from __future__ import annotations

import os
import re
import json
import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from app_text import render_text_panel
from app_file import render_file_uploader
from app_rss import render_rss_panel
from app_newsapi import render_newsapi_panel

try:
    from openai import OpenAI
    HAS_OPENAI = True
except Exception:
    OpenAI = None
    HAS_OPENAI = False


# ============================================================
# 기본 유틸
# ============================================================
def ss(key: str, default: Any) -> None:
    if key not in st.session_state:
        st.session_state[key] = default


def now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def now_compact() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def normalize_space(s: str) -> str:
    s = str(s or "")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\s+\n", "\n", s)
    return s.strip()


def clamp(s: str, n: int) -> str:
    s = str(s or "")
    return s if len(s) <= n else s[:n] + "…"


def get_secret_or_env(key: str, default: str = "") -> str:
    """
    Streamlit Cloud Secrets 또는 로컬 .env/환경변수에서 값을 읽는다.
    """
    try:
        value = st.secrets.get(key, "")
    except Exception:
        value = ""

    return str(value or os.getenv(key, default) or "").strip()


# ============================================================
# Workspace / Buffer 타입 정규화
# ============================================================
def to_workspace_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, list):
        parts: List[str] = []

        for item in value:
            if item is None:
                continue

            if isinstance(item, str):
                text = item.strip()
                if text:
                    parts.append(text)

            elif isinstance(item, dict):
                title = str(item.get("title") or item.get("headline") or "").strip()
                text = str(
                    item.get("text")
                    or item.get("body")
                    or item.get("summary")
                    or item.get("description")
                    or item.get("content")
                    or ""
                ).strip()

                meta = item.get("meta", {}) or {}
                source = str(meta.get("source") or item.get("source") or "").strip()
                published = str(meta.get("published") or item.get("published") or "").strip()
                url = str(meta.get("url") or item.get("url") or item.get("link") or "").strip()

                lines: List[str] = []

                if title:
                    lines.append(f"# {title}")
                if published:
                    lines.append(f"- 일시: {published}")
                if source:
                    lines.append(f"- 출처: {source}")
                if url:
                    lines.append(f"- 링크: {url}")
                if text:
                    lines.append("")
                    lines.append(text)

                block = "\n".join(lines).strip()

                if block:
                    parts.append(block)

            else:
                text = str(item).strip()
                if text:
                    parts.append(text)

        return "\n\n---\n\n".join(parts).strip()

    if isinstance(value, dict):
        title = str(value.get("title") or value.get("headline") or "").strip()
        text = str(
            value.get("text")
            or value.get("body")
            or value.get("summary")
            or value.get("description")
            or value.get("content")
            or ""
        ).strip()

        meta = value.get("meta", {}) or {}
        source = str(meta.get("source") or value.get("source") or "").strip()
        published = str(meta.get("published") or value.get("published") or "").strip()
        url = str(meta.get("url") or value.get("url") or value.get("link") or "").strip()

        lines: List[str] = []

        if title:
            lines.append(f"# {title}")
        if published:
            lines.append(f"- 일시: {published}")
        if source:
            lines.append(f"- 출처: {source}")
        if url:
            lines.append(f"- 링크: {url}")
        if text:
            lines.append("")
            lines.append(text)

        block = "\n".join(lines).strip()

        if block:
            return block

        return json.dumps(value, ensure_ascii=False, indent=2)

    return str(value).strip()


def normalize_buffer_items(items: Any) -> List[Dict[str, Any]]:
    if items is None:
        return []

    normalized: List[Dict[str, Any]] = []

    if isinstance(items, list):
        for item in items:
            normalized.extend(normalize_buffer_items(item))
        return normalized

    if isinstance(items, dict):
        title = str(items.get("title") or items.get("headline") or "").strip()
        text = str(
            items.get("text")
            or items.get("body")
            or items.get("summary")
            or items.get("description")
            or items.get("content")
            or ""
        ).strip()

        meta = items.get("meta", {}) or {}

        if "source" not in meta and items.get("source"):
            meta["source"] = items.get("source")

        if "published" not in meta and items.get("published"):
            meta["published"] = items.get("published")

        if "url" not in meta and (items.get("url") or items.get("link")):
            meta["url"] = items.get("url") or items.get("link")

        normalized.append(
            {
                "type": items.get("type", "item"),
                "title": title or text[:80] or "(제목 없음)",
                "text": text,
                "meta": meta,
            }
        )

        return normalized

    if isinstance(items, str):
        text = items.strip()

        if not text:
            return []

        return [
            {
                "type": "text",
                "title": text[:80],
                "text": text,
                "meta": {
                    "source": "text",
                    "created_at": now_iso(),
                },
            }
        ]

    text = str(items).strip()

    if not text:
        return []

    return [
        {
            "type": "unknown",
            "title": text[:80],
            "text": text,
            "meta": {
                "source": "unknown",
                "created_at": now_iso(),
            },
        }
    ]


# ============================================================
# Workspace / Buffer 반영
# ============================================================
def append_workspace(block: Any) -> None:
    block_text = to_workspace_text(block)

    if not block_text:
        return

    ws = to_workspace_text(st.session_state.get("workspace_text", ""))

    st.session_state.workspace_text = (
        f"{ws}\n\n{block_text}".strip()
        if ws
        else block_text
    )


def overwrite_workspace(block: Any) -> None:
    st.session_state.workspace_text = to_workspace_text(block)


def add_buffer(items: Any) -> None:
    normalized_items = normalize_buffer_items(items)

    if not normalized_items:
        return

    current_items = normalize_buffer_items(st.session_state.get("buffer_items", []))
    st.session_state.buffer_items = current_items + normalized_items


def commit_controls(
    ws_text: Any,
    buf_items: Any,
    *,
    key_prefix: str,
    set_mode: str,
    after_hint: str,
    ws_policy_key: Optional[str] = None,
) -> None:
    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("Workspace 반영", use_container_width=True, key=f"{key_prefix}_ws"):
            ws_text_safe = to_workspace_text(ws_text)

            if not ws_text_safe:
                st.warning("Workspace로 반영할 텍스트가 없습니다.")
            else:
                policy = "append"

                if ws_policy_key and ws_policy_key in st.session_state:
                    if "덮어쓰기" in str(st.session_state[ws_policy_key]):
                        policy = "overwrite"

                if policy == "overwrite":
                    overwrite_workspace(ws_text_safe)
                else:
                    append_workspace(ws_text_safe)

                st.session_state.active_gen_mode = set_mode
                st.session_state.last_commit_hint = after_hint
                st.success("Workspace에 반영했습니다.")

    with c2:
        if st.button("Buffer 반영", use_container_width=True, key=f"{key_prefix}_buf"):
            normalized_items = normalize_buffer_items(buf_items)

            if not normalized_items:
                st.warning("Buffer로 반영할 항목이 없습니다.")
            else:
                add_buffer(normalized_items)
                st.session_state.active_gen_mode = set_mode
                st.session_state.last_commit_hint = after_hint
                st.success(f"Buffer에 {len(normalized_items)}개 반영했습니다.")

    with c3:
        if st.button("둘 다 반영", use_container_width=True, key=f"{key_prefix}_both"):
            did = False

            ws_text_safe = to_workspace_text(ws_text)
            normalized_items = normalize_buffer_items(buf_items)

            if ws_text_safe:
                append_workspace(ws_text_safe)
                did = True

            if normalized_items:
                add_buffer(normalized_items)
                did = True

            if did:
                st.session_state.active_gen_mode = set_mode
                st.session_state.last_commit_hint = after_hint
                st.success("Workspace / Buffer에 반영했습니다.")
            else:
                st.warning("반영할 자료가 없습니다.")


# ============================================================
# 초기화
# ============================================================
def clear_keys_by_prefix(prefixes: List[str]) -> None:
    for key in list(st.session_state.keys()):
        if any(key.startswith(prefix) for prefix in prefixes):
            st.session_state.pop(key, None)


def reset_workspace() -> None:
    st.session_state.workspace_text = ""
    st.session_state.last_commit_hint = "Workspace를 비웠습니다."


def reset_buffer() -> None:
    st.session_state.buffer_items = []
    st.session_state.active_gen_mode = "버퍼 항목별"
    st.session_state.last_commit_hint = "Buffer를 비웠습니다."

    clear_keys_by_prefix(
        [
            "rss_",
            "newsapi_",
            "buffer_preview_",
        ]
    )


def reset_drafts() -> None:
    st.session_state.draft_items = []
    st.session_state.selected_draft_index = 0
    st.session_state.draft_editor_last_id = None
    st.session_state.draft_editor_dirty = False
    st.session_state.last_commit_hint = "Draft를 비웠습니다."

    clear_keys_by_prefix(
        [
            "draft_edit_",
            "draft_select_",
            "saved_system_role_",
            "saved_user_role_",
            "saved_original_context_",
        ]
    )


def reset_file_panel() -> None:
    clear_keys_by_prefix(
        [
            "file_",
            "article_file",
        ]
    )


def reset_text_panel() -> None:
    clear_keys_by_prefix(
        [
            "text_",
        ]
    )


def reset_all() -> None:
    st.session_state.workspace_text = ""
    st.session_state.buffer_items = []
    st.session_state.draft_items = []

    st.session_state.selected_draft_index = 0
    st.session_state.active_gen_mode = "Workspace 기반"
    st.session_state.last_commit_hint = "전체 초기화 완료"

    st.session_state.draft_editor_last_id = None
    st.session_state.draft_editor_dirty = False

    clear_keys_by_prefix(
        [
            "file_",
            "article_file",
            "text_",
            "rss_",
            "newsapi_",
            "draft_edit_",
            "draft_select_",
            "buffer_preview_",
            "saved_system_role_",
            "saved_user_role_",
            "saved_original_context_",
        ]
    )


# ============================================================
# File 패널
# ============================================================
def make_file_workspace_block(title: str, body: str) -> str:
    return "\n".join(
        [
            f"# {title.strip() or '파일 업로드'}",
            f"- 입력시각: {now_iso()}",
            "",
            body.strip(),
            "",
            "---",
        ]
    )


def render_file_panel_simple() -> Tuple[Optional[str], List[Dict[str, Any]]]:
    ss("file_last_ws_text", None)
    ss("file_last_buffer", [])
    ss("file_last_info", "")

    st.caption("TXT/PDF 파일은 기본적으로 Workspace에 반영합니다.")

    row = st.columns([2, 1])

    with row[0]:
        title = st.text_input("제목", key="file_title")

    with row[1]:
        st.radio(
            "Workspace 반영 방식",
            ["현재 Workspace에 추가", "현재 Workspace를 덮어쓰기"],
            index=0,
            key="file_ws_policy",
        )

    extracted = render_file_uploader(
        label="기사 파일 업로드",
        key="article_file",
        show_preview=True,
    )

    edited_text = to_workspace_text(
        st.session_state.get("article_file_preview", extracted)
    )

    if not st.button("파일 반영 준비", use_container_width=True, key="file_prepare"):
        if st.session_state.file_last_info:
            st.success(st.session_state.file_last_info)

        return st.session_state.file_last_ws_text, st.session_state.file_last_buffer

    if not edited_text.strip():
        st.error("추출된 텍스트가 없습니다.")
        return st.session_state.file_last_ws_text, st.session_state.file_last_buffer

    ws_text = make_file_workspace_block(title, edited_text)

    st.session_state.file_last_ws_text = ws_text
    st.session_state.file_last_buffer = []
    st.session_state.file_last_info = f"파일 준비 완료: {now_iso()}"

    st.success(st.session_state.file_last_info)
    return ws_text, []


# ============================================================
# Draft / LLM
# ============================================================
DEFAULT_SYSTEM_RULES = """당신은 한국어 뉴스 편집자다.
- 원문에 없는 사실을 단정하지 말 것.
- 날짜, 인물, 기관, 수치가 나오면 가능한 한 원문 근거로 정확히 표기할 것.
- 출력은 제목, 핵심요약, 기사 본문, 출처 순서로 정리할 것.
"""

DEFAULT_USER_TEMPLATE = """다음 자료를 바탕으로 한국어 기사 초안을 작성하라.

[자료]
{context}

[요구]
- 첫 줄에 "제목: ..." 형식으로 제목을 제시
- 날짜와 일시는 원문에 있으면 정확히 명기
- 핵심요약 5~10개 불릿
- 기사 본문은 스트레이트 기사 톤
- 원문 링크가 있으면 출처 섹션에 표시
"""


def make_draft(title: str, body: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "id": f"{dt.datetime.now().timestamp()}_{os.urandom(3).hex()}",
        "title": title.strip() or "(제목 없음)",
        "body": body.rstrip(),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "meta": meta or {},
    }


def update_draft(d: Dict[str, Any], title: str, body: str) -> None:
    d["title"] = title.strip() or "(제목 없음)"
    d["body"] = body.rstrip()
    d["updated_at"] = now_iso()


TITLE_RE = re.compile(r"^\s*(?:제목|Title)\s*[:：]\s*(.+?)\s*$", re.IGNORECASE)


def extract_title_and_body(text: str, fallback_title: str) -> Tuple[str, str]:
    text = (text or "").strip()

    if not text:
        return fallback_title, ""

    lines = text.splitlines()
    title = fallback_title
    body_lines = lines[:]

    for i in range(min(5, len(lines))):
        m = TITLE_RE.match(lines[i])
        if m:
            title = m.group(1).strip()
            body_lines = lines[:i] + lines[i + 1:]
            break

    return title, "\n".join(body_lines).strip()


def rule_based_draft(context: str) -> str:
    context = normalize_space(context)

    urls = list(
        dict.fromkeys(
            [u.rstrip(").,]") for u in re.findall(r"https?://\S+", context)]
        )
    )

    out = [
        "제목: 자료 기반 임시 제목",
        "",
        "핵심요약:",
        "- 핵심 내용 1",
        "- 핵심 내용 2",
        "- 핵심 내용 3",
        "",
        "본문:",
        context[:3000] + ("…" if len(context) > 3000 else ""),
        "",
        "출처:",
    ]

    out += [f"- {u}" for u in urls[:30]] if urls else ["- 링크 없음"]

    return "\n".join(out)


def build_user_prompt(user_template: str, context: str) -> str:
    user_template = user_template or DEFAULT_USER_TEMPLATE

    if "{context}" in user_template:
        return user_template.format(context=context)

    return f"{user_template.strip()}\n\n[자료]\n{context}"


def llm_generate(
    context: str,
    system_rules: str,
    user_template: str,
    model: str,
    temperature: float,
) -> str:
    context = normalize_space(context)

    api_key = get_secret_or_env("OPENAI_API_KEY")

    if not HAS_OPENAI or not api_key:
        return rule_based_draft(context)

    client = OpenAI(api_key=api_key)

    try:
        response = client.chat.completions.create(
            model=model,
            temperature=float(temperature),
            messages=[
                {"role": "system", "content": system_rules},
                {
                    "role": "user",
                    "content": build_user_prompt(user_template, context),
                },
            ],
        )

        return response.choices[0].message.content or ""

    except Exception:
        return rule_based_draft(context)


def make_role_meta(system_rules: str, user_template: str) -> Dict[str, str]:
    return {
        "system": system_rules or "",
        "user": user_template or "",
    }


def buffer_to_context_items(buffer_items: Any, per_item: bool) -> List[Dict[str, Any]]:
    buffer_items = normalize_buffer_items(buffer_items)

    if not buffer_items:
        return []

    if per_item:
        out = []

        for it in buffer_items:
            meta = it.get("meta", {}) or {}

            lines = [
                f"[{it.get('type', '')}] {it.get('title', '')}",
            ]

            if meta.get("published"):
                lines.append(f"- 일시: {meta.get('published')}")
            if meta.get("source"):
                lines.append(f"- 출처: {meta.get('source')}")
            if meta.get("url"):
                lines.append(f"- 링크: {meta.get('url')}")

            lines.append("")
            lines.append(it.get("text", "") or it.get("body", "") or "")

            out.append(
                {
                    "fallback_title": it.get("title") or "(제목 없음)",
                    "context": normalize_space("\n".join(lines)),
                    "source_meta": meta,
                }
            )

        return out

    parts = []

    for it in buffer_items:
        parts.append(
            f"[{it.get('type', '')}] {it.get('title', '')}\n"
            f"{it.get('text', '') or it.get('body', '')}"
        )

    return [
        {
            "fallback_title": "Buffer 통합",
            "context": normalize_space("\n\n---\n\n".join(parts)),
            "source_meta": {"mode": "combined", "count": len(buffer_items)},
        }
    ]


# ============================================================
# Draft editor callbacks
# ============================================================
def cb_select_draft_changed() -> None:
    drafts = st.session_state.draft_items or []

    if not drafts:
        return

    idx = int(st.session_state.draft_select_index)
    idx = max(0, min(idx, len(drafts) - 1))

    st.session_state.selected_draft_index = idx

    d = drafts[idx]
    st.session_state.draft_edit_title = d.get("title", "")
    st.session_state.draft_edit_body = d.get("body", "")
    st.session_state.draft_editor_last_id = d.get("id")
    st.session_state.draft_editor_dirty = False


def cb_mark_dirty() -> None:
    st.session_state.draft_editor_dirty = True


def cb_delete_selected_draft() -> None:
    drafts = st.session_state.draft_items or []

    if not drafts:
        return

    idx = int(st.session_state.selected_draft_index)
    idx = max(0, min(idx, len(drafts) - 1))

    drafts.pop(idx)

    st.session_state.draft_items = drafts
    st.session_state.selected_draft_index = max(0, idx - 1)

    st.session_state.pop("draft_edit_title", None)
    st.session_state.pop("draft_edit_body", None)
    st.session_state.pop("draft_select_index", None)

    st.session_state.draft_editor_dirty = False
    st.session_state.draft_editor_last_id = None


# ============================================================
# App 시작
# ============================================================
APP_TITLE = "AI 취재·정리 작업판 - 통합형"
st.set_page_config(page_title=APP_TITLE, layout="wide")
st.title(APP_TITLE)

st.info(
    "사용 흐름: Text/File → Workspace → Workspace 기반 생성 / "
    "RSS·NewsAPI → Buffer → 버퍼 항목별 생성"
)

ss("workspace_text", "")
ss("buffer_items", [])
ss("draft_items", [])
ss("selected_draft_index", 0)
ss("active_gen_mode", "Workspace 기반")
ss("last_commit_hint", "")
ss("draft_editor_last_id", None)
ss("draft_editor_dirty", False)
ss("system_rules", DEFAULT_SYSTEM_RULES)
ss("user_template", DEFAULT_USER_TEMPLATE)

st.session_state.workspace_text = to_workspace_text(st.session_state.workspace_text)
st.session_state.buffer_items = normalize_buffer_items(st.session_state.buffer_items)


# ============================================================
# Sidebar
# ============================================================
with st.sidebar:
    st.subheader("현재 상태")

    st.caption(f"Workspace 글자 수: {len(st.session_state.workspace_text or ''):,}")
    st.caption(f"Buffer 항목 수: {len(st.session_state.buffer_items or []):,}")
    st.caption(f"Draft 수: {len(st.session_state.draft_items or []):,}")

    st.divider()

    with st.expander("API 키 상태", expanded=False):
        openai_loaded = bool(get_secret_or_env("OPENAI_API_KEY"))
        newsapi_loaded = bool(get_secret_or_env("NEWSAPI_KEY"))

        st.caption(f"OPENAI_API_KEY 읽힘: {openai_loaded}")
        st.caption(f"NEWSAPI_KEY 읽힘: {newsapi_loaded}")

    with st.expander("초기화", expanded=False):
        if st.button("전체 비우기", use_container_width=True, key="btn_reset_all"):
            reset_all()
            st.rerun()

        if st.button("Workspace 비우기", use_container_width=True, key="btn_reset_workspace"):
            reset_workspace()
            st.rerun()

        if st.button("Buffer 비우기", use_container_width=True, key="btn_reset_buffer"):
            reset_buffer()
            st.rerun()

        if st.button("Draft 비우기", use_container_width=True, key="btn_reset_drafts"):
            reset_drafts()
            st.rerun()

        if st.button("Text 입력 상태 비우기", use_container_width=True, key="btn_reset_text_panel"):
            reset_text_panel()
            st.rerun()

        if st.button("File 업로드 상태 비우기", use_container_width=True, key="btn_reset_file_panel"):
            reset_file_panel()
            st.rerun()

    with st.expander("Export", expanded=False):
        st.download_button(
            "Workspace TXT 다운로드",
            data=(st.session_state.workspace_text or "").encode("utf-8"),
            file_name=f"workspace_{now_compact()}.txt",
            mime="text/plain",
            use_container_width=True,
        )

        st.download_button(
            "Buffer JSON 다운로드",
            data=json.dumps(
                st.session_state.buffer_items or [],
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
            file_name=f"buffer_{now_compact()}.json",
            mime="application/json",
            use_container_width=True,
        )

        st.download_button(
            "Draft JSON 다운로드",
            data=json.dumps(
                st.session_state.draft_items or [],
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
            file_name=f"drafts_{now_compact()}.json",
            mime="application/json",
            use_container_width=True,
        )


# ============================================================
# ⓪ 수집 패널
# ============================================================
with st.expander("⓪ 수집 패널 열기", expanded=False):
    tabs = st.tabs(["Text", "File", "RSS", "NewsAPI"])

    with tabs[0]:
        st.subheader("Text 입력")
        panel_result = render_text_panel()

        if isinstance(panel_result, tuple):
            ws_text = panel_result[0] if len(panel_result) > 0 else ""
            buf_items = panel_result[1] if len(panel_result) > 1 else []
        else:
            ws_text = panel_result
            buf_items = panel_result

        st.divider()

        commit_controls(
            ws_text,
            buf_items,
            key_prefix="text",
            set_mode="Workspace 기반",
            after_hint="Text를 Workspace로 반영했습니다. Workspace 기반으로 Draft를 생성하세요.",
            ws_policy_key="text_ws_policy",
        )

    with tabs[1]:
        st.subheader("File 업로드")
        ws_text, buf_items = render_file_panel_simple()

        st.divider()

        commit_controls(
            ws_text,
            buf_items,
            key_prefix="file",
            set_mode="Workspace 기반",
            after_hint="File을 Workspace로 반영했습니다. Workspace 기반으로 Draft를 생성하세요.",
            ws_policy_key="file_ws_policy",
        )

    with tabs[2]:
        st.subheader("RSS 수집")
        panel_result = render_rss_panel()

        if isinstance(panel_result, tuple):
            ws_text = panel_result[0] if len(panel_result) > 0 else ""
            buf_items = panel_result[1] if len(panel_result) > 1 else []
        else:
            ws_text = panel_result
            buf_items = panel_result

        st.divider()

        commit_controls(
            ws_text,
            buf_items,
            key_prefix="rss",
            set_mode="버퍼 항목별",
            after_hint="RSS를 Buffer로 반영했습니다. 버퍼 항목별 생성이 기본입니다.",
        )

    with tabs[3]:
        newsapi_key = get_secret_or_env("NEWSAPI_KEY")

        panel_result = render_newsapi_panel(newsapi_key)

        if isinstance(panel_result, tuple):
            ws_text = panel_result[0] if len(panel_result) > 0 else ""
            buf_items = panel_result[1] if len(panel_result) > 1 else []
        else:
            ws_text = panel_result
            buf_items = panel_result

        st.divider()

        commit_controls(
            ws_text,
            buf_items,
            key_prefix="newsapi",
            set_mode="버퍼 항목별",
            after_hint="NewsAPI를 Buffer로 반영했습니다. 버퍼 항목별 생성이 기본입니다.",
        )


st.divider()


# ============================================================
# ① 자료 확인 패널
# ============================================================
with st.expander("① 자료 확인 열기", expanded=False):
    st.subheader("Workspace")
    st.text_area(
        "Workspace 내용",
        key="workspace_text",
        height=260,
    )

    st.subheader("Buffer")
    buf = normalize_buffer_items(st.session_state.buffer_items or [])
    st.session_state.buffer_items = buf

    if not buf:
        st.info("Buffer가 비어 있습니다. RSS 또는 NewsAPI를 수집한 뒤 Buffer에 반영하세요.")
    else:
        for i, it in enumerate(list(reversed(buf))[:12], start=1):
            meta = it.get("meta", {}) or {}

            title = it.get("title", "(제목 없음)")
            source = meta.get("source", "")
            published = meta.get("published", "")

            with st.expander(f"{i}. {title} / {source} / {published}", expanded=False):
                if meta.get("url"):
                    st.write(meta.get("url"))

                st.text_area(
                    "본문",
                    value=clamp(it.get("text", "") or it.get("body", ""), 6000),
                    height=160,
                    disabled=True,
                    key=f"buffer_preview_{i}",
                )


st.divider()


# ============================================================
# ② Draft 생성 패널
# ============================================================
with st.expander("② Draft 생성 열기", expanded=False):
    buf = normalize_buffer_items(st.session_state.buffer_items or [])
    st.session_state.buffer_items = buf

    if st.session_state.last_commit_hint:
        st.success(st.session_state.last_commit_hint)

    model = get_secret_or_env("OPENAI_MODEL", "gpt-4.1-mini") or "gpt-4.1-mini"

    system_rules = st.text_area(
        "SYSTEM_RULES",
        height=170,
        key="system_rules",
        help="AI의 역할과 기본 원칙을 정하는 system 프롬프트입니다.",
    )

    user_template = st.text_area(
        "USER_TEMPLATE",
        height=240,
        key="user_template",
        help="{context} 위치에 Workspace 또는 Buffer 자료가 자동으로 들어갑니다.",
    )

    st.subheader("현재 적용 role 확인")

    role_col1, role_col2 = st.columns(2)

    with role_col1:
        st.markdown("**role: system**")
        st.text_area(
            "system role 내용",
            value=system_rules,
            height=140,
            disabled=True,
            key="role_system_preview",
        )

    with role_col2:
        st.markdown("**role: user**")
        st.text_area(
            "user role 내용",
            value=user_template,
            height=140,
            disabled=True,
            key="role_user_preview",
        )

    if "{context}" not in user_template:
        st.warning("USER_TEMPLATE에 {context}가 없습니다. 생성 시 자료가 프롬프트 맨 아래에 자동으로 붙습니다.")

    temperature = st.slider(
        "temperature",
        0.0,
        1.0,
        0.2,
        0.05,
        key="temperature",
    )

    mode = st.segmented_control(
        "생성 모드",
        options=["버퍼 항목별", "버퍼 통합", "Workspace 기반"],
        key="active_gen_mode",
    )

    if mode is None:
        mode = "Workspace 기반"
        st.session_state.active_gen_mode = mode

    role_meta = make_role_meta(system_rules, user_template)

    if mode == "Workspace 기반":
        if not st.session_state.workspace_text.strip():
            st.warning("Workspace가 비어 있습니다.")

        if st.button("Workspace 1개 생성 → Draft 추가", use_container_width=True):
            context = normalize_space(st.session_state.workspace_text)

            if not context:
                st.error("Workspace가 비어 있어 생성할 수 없습니다.")
            else:
                raw = llm_generate(
                    context,
                    system_rules,
                    user_template,
                    model,
                    temperature,
                )
                title, body = extract_title_and_body(raw, "Workspace 기반")

                draft = make_draft(
                    title,
                    body,
                    meta={
                        "mode": "workspace",
                        "original_context": context,
                        "model": model,
                        "temperature": temperature,
                        "roles": role_meta,
                        "system_rules": system_rules,
                        "user_template": user_template,
                    },
                )

                st.session_state.draft_items.append(draft)
                st.session_state.selected_draft_index = len(st.session_state.draft_items) - 1
                st.session_state.draft_editor_last_id = None

                st.success("Draft 1개를 추가했습니다.")

    elif mode == "버퍼 통합":
        if not buf:
            st.warning("Buffer가 비어 있습니다.")

        if st.button("Buffer 통합 1개 생성 → Draft 추가", use_container_width=True):
            if not buf:
                st.error("Buffer가 비어 있어 생성할 수 없습니다.")
            else:
                item = buffer_to_context_items(buf, per_item=False)[0]

                raw = llm_generate(
                    item["context"],
                    system_rules,
                    user_template,
                    model,
                    temperature,
                )
                title, body = extract_title_and_body(raw, "Buffer 통합")

                draft = make_draft(
                    title,
                    body,
                    meta={
                        "mode": "buffer_combined",
                        "original_context": item["context"],
                        "model": model,
                        "temperature": temperature,
                        "roles": role_meta,
                        "system_rules": system_rules,
                        "user_template": user_template,
                    },
                )

                st.session_state.draft_items.append(draft)
                st.session_state.selected_draft_index = len(st.session_state.draft_items) - 1
                st.session_state.draft_editor_last_id = None

                st.success("통합 Draft 1개를 추가했습니다.")

    else:
        if not buf:
            st.warning("Buffer가 비어 있습니다.")

        n_each = st.slider(
            "항목당 생성 개수",
            1,
            5,
            1,
            1,
            key="per_item_n",
        )

        if st.button("Buffer 항목별 생성 → Draft 추가", use_container_width=True):
            if not buf:
                st.error("Buffer가 비어 있어 생성할 수 없습니다.")
            else:
                ctx_items = buffer_to_context_items(buf, per_item=True)
                new_drafts = []

                for item in ctx_items:
                    for k in range(n_each):
                        raw = llm_generate(
                            item["context"],
                            system_rules,
                            user_template,
                            model,
                            temperature,
                        )

                        title, body = extract_title_and_body(
                            raw,
                            item["fallback_title"],
                        )

                        if n_each > 1:
                            title = f"{title} #{k + 1}"

                        new_drafts.append(
                            make_draft(
                                title,
                                body,
                                meta={
                                    "mode": "buffer_per_item",
                                    "original_context": item["context"],
                                    "source_meta": item["source_meta"],
                                    "model": model,
                                    "temperature": temperature,
                                    "roles": role_meta,
                                    "system_rules": system_rules,
                                    "user_template": user_template,
                                },
                            )
                        )

                st.session_state.draft_items.extend(new_drafts)
                st.session_state.selected_draft_index = len(st.session_state.draft_items) - len(new_drafts)
                st.session_state.draft_editor_last_id = None

                st.success(f"{len(new_drafts)}개 Draft를 추가했습니다.")


st.divider()


# ============================================================
# ③ Draft 편집 패널
# ============================================================
with st.expander("③ Draft 편집 열기", expanded=False):
    drafts = st.session_state.draft_items or []

    if not drafts:
        st.info("Draft가 없습니다. 먼저 Draft를 생성하세요.")
    else:
        options = [
            f"{i + 1}. {d.get('title', '(제목 없음)')} [{d.get('updated_at', '')}]"
            for i, d in enumerate(drafts)
        ]

        current_index = min(
            int(st.session_state.selected_draft_index),
            len(drafts) - 1,
        )

        if "draft_select_index" not in st.session_state:
            st.session_state.draft_select_index = current_index

        st.selectbox(
            "Draft 선택",
            options=list(range(len(options))),
            format_func=lambda i: options[i],
            index=current_index,
            key="draft_select_index",
            on_change=cb_select_draft_changed,
        )

        idx = int(st.session_state.selected_draft_index)
        idx = max(0, min(idx, len(drafts) - 1))

        draft = drafts[idx]

        if (
            "draft_edit_title" not in st.session_state
            or "draft_edit_body" not in st.session_state
            or st.session_state.draft_editor_last_id != draft.get("id")
        ):
            st.session_state.draft_edit_title = draft.get("title", "")
            st.session_state.draft_edit_body = draft.get("body", "")
            st.session_state.draft_editor_last_id = draft.get("id")
            st.session_state.draft_editor_dirty = False

        if st.session_state.draft_editor_dirty:
            st.warning("편집 중인 변경사항이 있습니다. 저장하지 않으면 사라질 수 있습니다.")

        st.text_input(
            "제목",
            key="draft_edit_title",
            on_change=cb_mark_dirty,
        )

        st.text_area(
            "본문",
            key="draft_edit_body",
            height=520,
            on_change=cb_mark_dirty,
        )

        c1, c2, c3 = st.columns(3)

        with c1:
            if st.button("편집 저장", use_container_width=True):
                update_draft(
                    draft,
                    st.session_state.draft_edit_title,
                    st.session_state.draft_edit_body,
                )

                st.session_state.draft_items[idx] = draft
                st.session_state.draft_editor_dirty = False

                st.success("저장했습니다.")

        with c2:
            with st.popover("원문 / role 열람", use_container_width=True):
                meta = draft.get("meta") or {}
                original_context = meta.get("original_context", "")
                roles = meta.get("roles", {}) or {}

                st.markdown("**role: system**")
                st.text_area(
                    "저장된 system role",
                    value=roles.get("system", meta.get("system_rules", "")),
                    height=180,
                    disabled=True,
                    key=f"saved_system_role_{idx}",
                )

                st.markdown("**role: user**")
                st.text_area(
                    "저장된 user role",
                    value=roles.get("user", meta.get("user_template", "")),
                    height=180,
                    disabled=True,
                    key=f"saved_user_role_{idx}",
                )

                st.markdown("**original_context**")
                st.text_area(
                    "original_context",
                    value=original_context,
                    height=300,
                    disabled=True,
                    key=f"saved_original_context_{idx}",
                )

        with c3:
            st.button(
                "이 Draft 삭제",
                use_container_width=True,
                on_click=cb_delete_selected_draft,
            )

        st.divider()
        st.subheader("다운로드")

        title_for_download = st.session_state.draft_edit_title.strip() or "(제목 없음)"
        body_for_download = st.session_state.draft_edit_body or ""

        txt_data = f"{title_for_download}\n\n{body_for_download}".encode("utf-8")

        st.download_button(
            "TXT 다운로드",
            data=txt_data,
            file_name=f"draft_{idx + 1}_{now_compact()}.txt",
            mime="text/plain",
            use_container_width=True,
        )

        st.download_button(
            "JSON 다운로드",
            data=json.dumps(
                st.session_state.draft_items[idx],
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
            file_name=f"draft_{idx + 1}_{now_compact()}.json",
            mime="application/json",
            use_container_width=True,
        )