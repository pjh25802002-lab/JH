# app_file.py
# streamlit cloud 용(api key 관련 코드 수정)

from __future__ import annotations

import io
import os
import datetime as dt
from typing import Tuple

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

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


def _now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _init_cache() -> None:
    if "file_last_filename" not in st.session_state:
        st.session_state.file_last_filename = ""
    if "file_last_text" not in st.session_state:
        st.session_state.file_last_text = ""
    if "file_last_ai_summary" not in st.session_state:
        st.session_state.file_last_ai_summary = ""
    if "file_last_info" not in st.session_state:
        st.session_state.file_last_info = ""


def clear_file_cache() -> None:
    st.session_state.file_last_filename = ""
    st.session_state.file_last_text = ""
    st.session_state.file_last_ai_summary = ""
    st.session_state.file_last_info = ""


def _read_txt_bytes(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            pass
    return data.decode("utf-8", errors="replace")


def _read_pdf_bytes(data: bytes) -> str:
    if PdfReader is None:
        raise RuntimeError(
            "PDF 읽기 기능을 사용하려면 pypdf가 필요합니다.\n"
            "터미널에서 다음 명령을 실행하세요.\n"
            "python -m pip install pypdf"
        )

    reader = PdfReader(io.BytesIO(data))
    chunks = []

    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""

        if text.strip():
            chunks.append(f"\n\n--- [PAGE {i}] ---\n{text}")

    return "\n".join(chunks).strip()


def extract_text_from_upload(uploaded_file) -> Tuple[str, str]:
    if uploaded_file is None:
        return "", ""

    filename = uploaded_file.name or ""
    data = uploaded_file.getvalue()
    lower = filename.lower()

    if lower.endswith(".txt"):
        return filename, _read_txt_bytes(data)

    if lower.endswith(".pdf"):
        return filename, _read_pdf_bytes(data)

    raise ValueError("지원하지 않는 파일 형식입니다. txt 또는 pdf만 업로드하세요.")


def generate_ai_summary(filename: str, text: str) -> str:
    api_key = st.secrets.get(
       "OPENAI_API_KEY",
       os.getenv("OPENAI_API_KEY", "")
    )

    if OpenAI is None:
        return (
            "[AI 오류]\n"
            "openai 패키지가 설치되어 있지 않습니다.\n\n"
            "터미널에서 다음 명령을 실행하세요.\n"
            "python -m pip install openai"
        )

    if not api_key:
        return (
            "[AI 오류]\n"
            "OPENAI_API_KEY가 설정되어 있지 않습니다.\n"
            ".env 파일을 확인하세요."
        )

    client = OpenAI(api_key=api_key)

    system_prompt = """
너는 뉴스 편집에 능한 한국어 기사 편집자다.
입력된 자료를 바탕으로 정확하고 읽기 쉬운 요약문을 작성한다.
원문에 없는 사실은 추측하지 않는다.
날짜, 인물, 기관, 수치, 국가명은 원문에 근거해 정확히 쓴다.
""".strip()

    user_prompt = f"""
다음 파일에서 추출한 기사 또는 자료를 요약해줘.

[파일명]
{filename}

[원문]
{text}

[작성 요구]
1. 핵심 내용을 5개 안팎의 불릿으로 정리
2. 중요한 날짜, 기관, 인물, 수치를 빠뜨리지 말 것
3. 마지막에 '기사화 포인트'를 3개 제시
4. 원문에 없는 내용은 쓰지 말 것
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


def render_file_uploader(
    label: str = "기사 파일 업로드 (txt / pdf)",
    key: str = "article_file",
    show_preview: bool = True,
    preview_height: int = 300,
) -> Tuple[str, str, str]:
    _init_cache()

    st.subheader("📄 파일 업로드")

    uploaded = st.file_uploader(label, type=["txt", "pdf"], key=key)

    col1, col2 = st.columns(2)

    with col1:
        do_ai_summary = st.button(
            "AI 요약 실행",
            use_container_width=True,
            key=f"{key}_ai_summary",
        )

    with col2:
        if st.button(
            "파일 캐시 비우기",
            use_container_width=True,
            key=f"{key}_clear_cache",
        ):
            clear_file_cache()
            st.success("파일 캐시를 비웠습니다.")
            st.rerun()

    filename = ""
    extracted_text = ""

    if uploaded is not None:
        try:
            filename, extracted_text = extract_text_from_upload(uploaded)

            if not extracted_text.strip():
                st.warning(
                    f"'{filename}'에서 텍스트를 추출하지 못했습니다. "
                    "스캔 PDF는 텍스트가 없을 수 있습니다."
                )
                return filename, "", st.session_state.file_last_ai_summary

            st.session_state.file_last_filename = filename
            st.session_state.file_last_text = extracted_text

        except Exception as e:
            st.error(f"파일 처리 오류: {e}")
            return "", "", st.session_state.file_last_ai_summary

    if st.session_state.file_last_text:
        filename = st.session_state.file_last_filename
        extracted_text = st.session_state.file_last_text

        st.caption(
            f"업로드 파일: {filename} / 추출 길이: {len(extracted_text):,}자"
        )

        if show_preview:
            edited_text = st.text_area(
                "추출된 원문 또는 편집된 원문",
                value=extracted_text,
                height=preview_height,
                key=f"{key}_preview",
            )
            st.session_state.file_last_text = edited_text
            extracted_text = edited_text

    if do_ai_summary:
        if not st.session_state.file_last_text.strip():
            st.warning("요약할 원문이 비어 있습니다.")
        else:
            with st.spinner("AI 요약 생성 중..."):
                summary = generate_ai_summary(
                    st.session_state.file_last_filename,
                    st.session_state.file_last_text,
                )

            st.session_state.file_last_ai_summary = summary
            st.session_state.file_last_info = f"AI 요약 생성 완료: {_now_iso()}"

    if st.session_state.file_last_info:
        st.success(st.session_state.file_last_info)

    if st.session_state.file_last_ai_summary:
        st.markdown("### AI 요약 결과 미리보기")
        st.text_area(
            "요약 결과",
            value=st.session_state.file_last_ai_summary,
            height=300,
            key=f"{key}_summary_preview",
        )

    return (
        st.session_state.file_last_filename,
        st.session_state.file_last_text,
        st.session_state.file_last_ai_summary,
    )