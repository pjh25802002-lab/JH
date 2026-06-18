# app_text.py
# streamlit cloud 용(api key 관련 코드 수정)

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import datetime as dt
import os
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

def _now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _init_cache() -> None:
    if "text_title" not in st.session_state:
        st.session_state.text_title = ""
    if "text_body" not in st.session_state:
        st.session_state.text_body = ""
    if "text_last_buffer" not in st.session_state:
        st.session_state.text_last_buffer = []
    if "text_last_ai_draft" not in st.session_state:
        st.session_state.text_last_ai_draft = ""
    if "text_last_info" not in st.session_state:
        st.session_state.text_last_info = ""

def clear_text_cache() -> None:
    st.session_state.text_last_buffer = []
    st.session_state.text_last_ai_draft = ""
    st.session_state.text_last_info = ""

def make_buffer_item(title: str, body: str) -> Dict:
    ts = _now_iso()
    title = (title or "").strip() or "텍스트 입력"
    body = (body or "").strip()

    return {
        "type": "text_input",
        "title": title,
        "text": body,
        "meta": {
            "source": "text",
            "created_at": ts,
            "char_len": len(body),
        },
    }

def generate_ai_draft(title: str, body: str) -> str:
    api_key = st.secrets.get(
        "OPENAI_API_KEY",
        os.getenv("OPENAI_API_KEY", "")
    )

    if OpenAI is None:
        return "[AI 오류]\nopenai 패키지가 설치되어 있지 않습니다.\n\n터미널에서 다음 명령을 실행하세요.\npython -m pip install openai"

    if not api_key:
        return "[AI 오류]\nOPENAI_API_KEY가 설정되어 있지 않습니다.\n.env 파일을 확인하세요."

    client = OpenAI(api_key=api_key)

    title = (title or "").strip()
    body = (body or "").strip()

    system_prompt = """
너는 한국어 뉴스 편집자다.
입력된 자료를 바탕으로 기사 초안을 작성한다.
원문에 없는 사실은 단정하지 않는다.
날짜, 인물, 기관, 수치는 원문에 근거해 정확히 쓴다.
출력은 제목, 핵심요약, 기사본문 순서로 작성한다.
""".strip()

    user_prompt = f"""
다음 자료를 바탕으로 한국어 기사 초안을 작성해줘.

[제목]
{title if title else "제목 없음"}

[자료]
{body}

[작성 요구]
1. 첫 줄은 "제목: ..." 형식으로 작성
2. 핵심요약은 3~5개 불릿으로 작성
3. 기사본문은 스트레이트 기사체로 작성
4. 추측하지 말고 자료에 있는 내용 중심으로 작성
""".strip()

    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            temperature=0.3,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        return response.choices[0].message.content or ""

    except Exception as e:
        return f"[AI 오류]\n{e}"


def render_text_panel() -> Tuple[List[Dict], str]:
    _init_cache()

    st.subheader("📝 텍스트 입력")

    title = st.text_input("제목(선택)", key="text_title")

    body = st.text_area(
        "텍스트 본문(붙여넣기/직접 입력)",
        key="text_body",
        height=260,
    )

    col1, col2 = st.columns(2)

    with col1:
        do_generate = st.button(
            "AI Draft 생성",
            use_container_width=True,
            key="text_generate_ai",
        )

    with col2:
        if st.button(
            "텍스트 캐시 비우기",
            use_container_width=True,
            key="text_clear_cache",
        ):
            clear_text_cache()
            st.success("텍스트 캐시를 비웠습니다.")
            st.rerun()

    if do_generate:
        if not (body or "").strip():
            st.error("본문이 비어 있습니다.")
            return st.session_state.text_last_buffer, st.session_state.text_last_ai_draft

        buffer_item = make_buffer_item(title, body)
        ai_draft = generate_ai_draft(title, body)

        st.session_state.text_last_buffer = [buffer_item]
        st.session_state.text_last_ai_draft = ai_draft
        st.session_state.text_last_info = f"AI Draft 생성 완료: {_now_iso()}"

    if st.session_state.text_last_info:
        st.success(st.session_state.text_last_info)

    if st.session_state.text_last_ai_draft:
        st.markdown("### AI Draft 미리보기")
        st.text_area(
            "생성 결과",
            value=st.session_state.text_last_ai_draft,
            height=300,
            key="text_ai_preview",
        )

    return st.session_state.text_last_buffer, st.session_state.text_last_ai_draft
