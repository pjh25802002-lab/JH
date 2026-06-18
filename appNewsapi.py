# appNewsapi.py
# ------------------------------------------------------------
# AI 기사 요약 미니 편집기 v5 - NewsAPI 수업용 단순 UI 버전
# 흐름:
# 1. NewsAPI 수집
# 2. 자료 확인
# 3. AI 초안 생성
# 4. Draft 편집 / 다운로드
# ------------------------------------------------------------

from __future__ import annotations

import os
import json
import datetime as dt
from typing import Any, Dict, List, Optional

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from app_newsapi import render_newsapi_panel


# -------------------------
# 기본 설정
# -------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")

APP_TITLE = "AI 기사 요약 미니 편집기 v5 - NewsAPI 수업용"
st.set_page_config(page_title=APP_TITLE, layout="wide")

st.title(APP_TITLE)
st.info("사용 순서: ① NewsAPI 수집 → ② 자료 확인 → ③ AI 초안 생성 → ④ 편집·다운로드")


# -------------------------
# SessionState 유틸
# -------------------------
def ss(key: str, default: Any) -> None:
    if key not in st.session_state:
        st.session_state[key] = default


def now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# -------------------------
# 상태 초기화
# -------------------------
ss("workspace_text", "")
ss("buffer_items", [])
ss("draft_items", [])
ss("selected_draft_index", 0)

ss(
    "system_prompt",
    "당신은 한국어 기사 요약/정리 편집기입니다. 사실관계 중심으로 간결하게 정리하세요.",
)

ss(
    "user_prompt",
    "아래 자료를 기반으로 핵심 요약 7개, 쟁점 3개, 후속 취재 질문 3개를 작성해줘.",
)

ss("model_name", "gpt-4o-mini")


# -------------------------
# LLM 입력 구성
# -------------------------
def build_llm_input_text(workspace_text: str, buffer_items: List[Dict]) -> str:
    parts: List[str] = []

    if workspace_text.strip():
        parts.append("# Workspace 자료")
        parts.append(workspace_text.strip())
        parts.append("\n---\n")

    if buffer_items:
        parts.append("# Buffer 자료")

        for i, it in enumerate(buffer_items, start=1):
            title = it.get("title", "")
            text = it.get("text", "")
            meta = it.get("meta") or {}

            parts.append(f"## [{i}] {title}")

            if meta.get("published"):
                parts.append(f"- 일시: {meta.get('published')}")
            if meta.get("source"):
                parts.append(f"- 출처: {meta.get('source')}")
            if meta.get("url"):
                parts.append(f"- 링크: {meta.get('url')}")

            parts.append("")
            parts.append(text)
            parts.append("\n---\n")

    return "\n".join(parts).strip()


def build_single_buffer_input(it: Dict) -> str:
    title = it.get("title", "")
    text = it.get("text", "")
    meta = it.get("meta") or {}

    lines = []
    lines.append(f"제목: {title}")

    if meta.get("published"):
        lines.append(f"일시: {meta.get('published')}")
    if meta.get("source"):
        lines.append(f"출처: {meta.get('source')}")
    if meta.get("url"):
        lines.append(f"링크: {meta.get('url')}")

    lines.append("")
    lines.append(text)

    return "\n".join(lines).strip()


def call_openai_generate(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_prompt: str,
    input_text: str,
) -> str:
    if not input_text.strip():
        raise ValueError("AI에 보낼 입력 자료가 없습니다.")

    messages = [
        {"role": "system", "content": system_prompt.strip()},
        {
            "role": "user",
            "content": f"{user_prompt.strip()}\n\n[자료]\n{input_text.strip()}",
        },
    ]

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3,
    )

    return response.choices[0].message.content or ""


def add_draft(title: str, text: str, meta: Optional[Dict] = None) -> None:
    st.session_state.draft_items.append(
        {
            "title": title,
            "text": text,
            "meta": meta or {},
        }
    )
    st.session_state.selected_draft_index = len(st.session_state.draft_items) - 1


# -------------------------
# 사이드바
# -------------------------
with st.sidebar:
    st.header("⚙️ 기본 설정")

    st.text_input("사용 모델", key="model_name")

    with st.expander("프롬프트 설정", expanded=False):
        st.text_area("System Prompt", key="system_prompt", height=130)
        st.text_area("User Prompt", key="user_prompt", height=150)

    st.divider()
    st.header("🔑 API Key 상태")

    if NEWSAPI_KEY.strip():
        st.success("NEWSAPI_KEY 있음")
    else:
        st.warning("NEWSAPI_KEY 없음")

    if OPENAI_API_KEY.strip():
        st.success("OPENAI_API_KEY 있음")
    else:
        st.warning("OPENAI_API_KEY 없음")

    st.divider()
    st.header("🧹 초기화")

    if st.button("Workspace 비우기", use_container_width=True):
        st.session_state.workspace_text = ""
        st.success("Workspace를 비웠습니다.")

    if st.button("Buffer 비우기", use_container_width=True):
        st.session_state.buffer_items = []
        st.success("Buffer를 비웠습니다.")

    if st.button("Draft 전체 비우기", use_container_width=True):
        st.session_state.draft_items = []
        st.session_state.selected_draft_index = 0
        st.success("Draft를 모두 비웠습니다.")


# -------------------------
# 현재 상태 표시
# -------------------------
col_a, col_b, col_c = st.columns(3)

with col_a:
    st.metric("Workspace 글자 수", len(st.session_state.workspace_text))

with col_b:
    st.metric("Buffer 항목 수", len(st.session_state.buffer_items))

with col_c:
    st.metric("Draft 수", len(st.session_state.draft_items))


# -------------------------
# 메인 탭 구조
# -------------------------
tab1, tab2, tab3, tab4 = st.tabs(
    [
        "① NewsAPI 수집",
        "② 자료 확인",
        "③ AI 초안 생성",
        "④ 편집·다운로드",
    ]
)


# ============================================================
# ① NewsAPI 수집
# ============================================================
with tab1:
    st.header("① NewsAPI 수집")
    st.write("검색어를 입력해 NewsAPI에서 기사를 수집한 뒤, Workspace 또는 Buffer에 넣습니다.")

    ws_text_from_newsapi, buffer_from_newsapi = render_newsapi_panel(NEWSAPI_KEY)

    st.divider()

    newsapi_info = st.session_state.get("newsapi_last_info", "")

    if newsapi_info:
        st.success(f"현재 수집 결과: {newsapi_info}")
    else:
        st.warning("아직 NewsAPI를 불러오지 않았습니다.")

    st.subheader("수집 결과 반영")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Workspace에 넣기")
        st.caption("여러 기사를 하나의 긴 텍스트로 모아둡니다.")

        if st.button(
            "NewsAPI 결과를 Workspace에 추가",
            use_container_width=True,
            disabled=(ws_text_from_newsapi is None),
        ):
            if st.session_state.workspace_text.strip():
                st.session_state.workspace_text += "\n\n"

            st.session_state.workspace_text += ws_text_from_newsapi or ""
            st.success("Workspace에 추가했습니다.")

    with col2:
        st.markdown("### Buffer에 넣기")
        st.caption("기사별로 나누어 보관합니다. 수업용으로는 이 방식이 가장 직관적입니다.")

        if st.button(
            "NewsAPI 결과를 Buffer에 추가",
            use_container_width=True,
            disabled=(not buffer_from_newsapi),
        ):
            st.session_state.buffer_items.extend(buffer_from_newsapi)
            st.success(f"Buffer에 {len(buffer_from_newsapi)}개를 추가했습니다.")


# ============================================================
# ② 자료 확인
# ============================================================
with tab2:
    st.header("② 자료 확인")
    st.write("AI에게 보낼 자료를 확인하는 화면입니다.")

    subtab1, subtab2 = st.tabs(["Workspace", "Buffer"])

    with subtab1:
        st.subheader("Workspace")
        st.caption("긴 텍스트 자료를 직접 확인하거나 수정할 수 있습니다.")

        st.text_area(
            "Workspace 내용",
            key="workspace_text",
            height=450,
        )

    with subtab2:
        st.subheader("Buffer")
        st.caption("NewsAPI 기사들이 항목 단위로 저장됩니다.")

        if not st.session_state.buffer_items:
            st.info("Buffer가 비어 있습니다. 먼저 ① NewsAPI 수집 탭에서 결과를 Buffer에 추가하세요.")
        else:
            for i, it in enumerate(st.session_state.buffer_items, start=1):
                meta = it.get("meta") or {}

                with st.expander(
                    f"[{i}] {it.get('title', '(제목 없음)')}",
                    expanded=(i <= 3),
                ):
                    if meta.get("published"):
                        st.write(f"일시: {meta.get('published')}")
                    if meta.get("source"):
                        st.write(f"출처: {meta.get('source')}")
                    if meta.get("url"):
                        st.write(meta.get("url"))

                    st.write(it.get("text", ""))


# ============================================================
# ③ AI 초안 생성
# ============================================================
with tab3:
    st.header("③ AI 초안 생성")
    st.write("Workspace와 Buffer에 담긴 자료를 바탕으로 AI 초안을 만듭니다.")

    gen_mode = st.radio(
        "초안 생성 방식",
        [
            "통합 Draft 1개 생성",
            "Buffer 항목별 Draft 여러 개 생성",
        ],
        horizontal=True,
    )

    buffer_count = len(st.session_state.buffer_items)
    input_text = ""
    selected_count = 0

    if gen_mode == "통합 Draft 1개 생성":
        input_mode = st.radio(
            "AI에 보낼 자료 선택",
            [
                "Buffer만 사용",
                "Workspace만 사용",
                "Workspace + Buffer 모두 사용",
            ],
            horizontal=True,
        )

        if input_mode == "Buffer만 사용":
            input_text = build_llm_input_text("", st.session_state.buffer_items)
        elif input_mode == "Workspace만 사용":
            input_text = build_llm_input_text(st.session_state.workspace_text, [])
        else:
            input_text = build_llm_input_text(
                st.session_state.workspace_text,
                st.session_state.buffer_items,
            )

        with st.expander("AI 입력 미리보기", expanded=False):
            if input_text.strip():
                st.code(
                    input_text[:3000] + ("\n...\n" if len(input_text) > 3000 else ""),
                    language="markdown",
                )
            else:
                st.warning("AI에 보낼 자료가 없습니다.")

    else:
        if buffer_count == 0:
            st.warning("Buffer가 비어 있습니다. 먼저 NewsAPI 결과를 Buffer에 추가하세요.")
        else:
            selected_count = st.number_input(
                "생성할 Draft 개수",
                min_value=1,
                max_value=buffer_count,
                value=min(10, buffer_count),
                step=1,
            )

            st.info(f"Buffer 앞에서부터 {selected_count}개 항목을 각각 Draft로 생성합니다.")

            with st.expander("생성 대상 미리보기", expanded=True):
                for i, it in enumerate(
                    st.session_state.buffer_items[: int(selected_count)],
                    start=1,
                ):
                    st.write(f"{i}. {it.get('title', '(제목 없음)')}")

    st.divider()

    if st.button("AI 초안 생성", type="primary", use_container_width=True):
        if not OPENAI_API_KEY.strip():
            st.error(".env 파일에 OPENAI_API_KEY가 없습니다.")
        else:
            try:
                client = OpenAI(api_key=OPENAI_API_KEY)

                user_prompt = st.session_state.user_prompt.strip()
                user_prompt += "\n\n추가 규칙:"
                user_prompt += "\n- 본문 첫 줄에 제목을 반복하지 마라."
                user_prompt += "\n- 확인되지 않은 사실은 단정하지 마라."

                # ----------------------------------------
                # 1) 통합 Draft 1개 생성
                # ----------------------------------------
                if gen_mode == "통합 Draft 1개 생성":
                    if not input_text.strip():
                        st.error("AI에 보낼 자료가 없습니다.")
                    else:
                        with st.spinner("AI 초안을 생성하는 중입니다..."):
                            draft_text = call_openai_generate(
                                client=client,
                                model=st.session_state.model_name,
                                system_prompt=st.session_state.system_prompt,
                                user_prompt=user_prompt,
                                input_text=input_text,
                            )

                        title = f"AI 초안 - {now_iso()}"

                        add_draft(
                            title=title,
                            text=draft_text,
                            meta={
                                "created_at": now_iso(),
                                "gen_mode": "combined",
                                "original_text": input_text,
                            },
                        )

                        st.success("통합 Draft 1개를 생성했습니다.")

                # ----------------------------------------
                # 2) Buffer 항목별 Draft 여러 개 생성
                # ----------------------------------------
                else:
                    if buffer_count == 0:
                        st.error("Buffer가 비어 있습니다.")
                    else:
                        created = 0
                        items = st.session_state.buffer_items[: int(selected_count)]

                        with st.spinner(f"Draft {len(items)}개를 생성하는 중입니다..."):
                            for i, it in enumerate(items, start=1):
                                single_input = build_single_buffer_input(it)

                                item_prompt = user_prompt
                                item_prompt += "\n- 아래 자료는 단일 기사이다. 이 기사 하나만 대상으로 작성하라."

                                draft_text = call_openai_generate(
                                    client=client,
                                    model=st.session_state.model_name,
                                    system_prompt=st.session_state.system_prompt,
                                    user_prompt=item_prompt,
                                    input_text=single_input,
                                )

                                base_title = it.get("title", f"Buffer 기사 {i}")
                                base_title = base_title[:70] + (
                                    "…" if len(base_title) > 70 else ""
                                )

                                add_draft(
                                    title=f"[{i}] {base_title}",
                                    text=draft_text,
                                    meta={
                                        "created_at": now_iso(),
                                        "gen_mode": "per_buffer_item",
                                        "source_item": it,
                                        "original_text": single_input,
                                    },
                                )

                                created += 1

                        st.success(f"Buffer 항목별 Draft {created}개를 생성했습니다.")

            except Exception as e:
                st.error(f"AI 초안 생성 실패: {e}")


# ============================================================
# ④ 편집·다운로드
# ============================================================
with tab4:
    st.header("④ 편집·다운로드")
    st.write("생성된 Draft를 수정하고 파일로 내려받습니다.")

    drafts = st.session_state.draft_items

    if not drafts:
        st.info("아직 Draft가 없습니다. 먼저 ③ AI 초안 생성 탭에서 초안을 생성하세요.")
    else:
        draft_options = []

        for i, d in enumerate(drafts):
            title = d.get("title", f"Draft #{i + 1}")
            draft_options.append(f"{i + 1}. {title}")

        default_idx = min(
            st.session_state.selected_draft_index,
            len(draft_options) - 1,
        )

        selected_label = st.selectbox(
            "편집할 Draft 선택",
            options=draft_options,
            index=default_idx,
        )

        idx = draft_options.index(selected_label)
        st.session_state.selected_draft_index = idx

        draft = drafts[idx]

        st.subheader(draft.get("title", f"Draft #{idx + 1}"))

        edit_title = st.text_input(
            "Draft 제목",
            value=draft.get("title", ""),
            key=f"edit_title_{idx}",
        )

        edit_text = st.text_area(
            "Draft 본문",
            value=draft.get("text", ""),
            height=450,
            key=f"edit_text_{idx}",
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("편집 내용 저장", use_container_width=True):
                draft["title"] = edit_title
                draft["text"] = edit_text
                draft.setdefault("meta", {})
                draft["meta"]["updated_at"] = now_iso()
                st.success("저장했습니다.")

        with col2:
            if st.button("현재 Draft 삭제", use_container_width=True):
                del st.session_state.draft_items[idx]
                st.session_state.selected_draft_index = 0
                st.warning("삭제했습니다.")
                st.rerun()

        st.divider()

        st.download_button(
            label="TXT 다운로드",
            data=(edit_text or "").encode("utf-8"),
            file_name=f"draft_{idx + 1}.txt",
            mime="text/plain; charset=utf-8",
            use_container_width=True,
        )

        st.download_button(
            label="JSON 다운로드(meta 포함)",
            data=json.dumps(draft, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name=f"draft_{idx + 1}.json",
            mime="application/json; charset=utf-8",
            use_container_width=True,
        )

        with st.expander("Draft meta 보기", expanded=False):
            st.json(draft.get("meta", {}))
