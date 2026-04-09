import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import re
from datetime import datetime

# ============================================================
# 페이지 설정
# ============================================================
st.set_page_config(
    page_title="유튜브 댓글 수집기",
    page_icon="🎬",
    layout="wide"
)

# ============================================================
# 스타일
# ============================================================
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        color: #FF0000;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        text-align: center;
        color: #666;
        margin-bottom: 2rem;
    }
    .comment-box {
        background-color: #f9f9f9;
        border-left: 4px solid #FF0000;
        padding: 12px 16px;
        margin-bottom: 10px;
        border-radius: 0 8px 8px 0;
    }
    .comment-author {
        font-weight: bold;
        color: #333;
        font-size: 0.95rem;
    }
    .comment-date {
        color: #999;
        font-size: 0.8rem;
    }
    .comment-text {
        margin-top: 6px;
        color: #444;
        line-height: 1.5;
    }
    .comment-likes {
        color: #FF0000;
        font-size: 0.85rem;
        margin-top: 4px;
    }
    .stat-card {
        background: linear-gradient(135deg, #FF0000, #cc0000);
        color: white;
        padding: 20px;
        border-radius: 12px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 헤더
# ============================================================
st.markdown('<div class="main-header">🎬 유튜브 댓글 수집기</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">유튜브 영상 링크를 입력하면 댓글을 수집하여 보여줍니다</div>', unsafe_allow_html=True)


# ============================================================
# 유틸리티 함수들
# ============================================================
def extract_video_id(url: str) -> str | None:
    """유튜브 URL에서 영상 ID를 추출합니다."""
    patterns = [
        r'(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_youtube_service():
    """YouTube API 서비스 객체를 생성합니다."""
    api_key = st.secrets.get("YOUTUBE_API_KEY", None)
    if not api_key:
        return None
    return build("youtube", "v3", developerKey=api_key)


def get_video_info(youtube, video_id: str) -> dict | None:
    """영상 기본 정보를 가져옵니다."""
    try:
        request = youtube.videos().list(
            part="snippet,statistics",
            id=video_id
        )
        response = request.execute()
        if response["items"]:
            item = response["items"][0]
            snippet = item["snippet"]
            stats = item["statistics"]
            return {
                "title": snippet.get("title", "제목 없음"),
                "channel": snippet.get("channelTitle", "채널 없음"),
                "published": snippet.get("publishedAt", "")[:10],
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "comment_count": int(stats.get("commentCount", 0)),
            }
        return None
    except HttpError:
        return None


def get_comments(youtube, video_id: str, max_comments: int = 100) -> list[dict]:
    """영상의 댓글을 수집합니다."""
    comments = []
    next_page_token = None

    try:
        while len(comments) < max_comments:
            request = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=min(100, max_comments - len(comments)),
                pageToken=next_page_token,
                order="relevance",
                textFormat="plainText"
            )
            response = request.execute()

            for item in response.get("items", []):
                top = item["snippet"]["topLevelComment"]["snippet"]
                comments.append({
                    "작성자": top.get("authorDisplayName", "알 수 없음"),
                    "댓글": top.get("textDisplay", ""),
                    "좋아요": top.get("likeCount", 0),
                    "작성일": top.get("publishedAt", "")[:10],
                    "수정일": top.get("updatedAt", "")[:10],
                })

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

    except HttpError as e:
        if "commentsDisabled" in str(e):
            st.error("❌ 이 영상은 댓글이 비활성화되어 있습니다.")
        else:
            st.error(f"❌ API 오류가 발생했습니다: {e}")
        return []

    return comments


def format_number(n: int) -> str:
    """숫자를 읽기 쉽게 포맷합니다."""
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}억"
    elif n >= 10_000:
        return f"{n / 10_000:.1f}만"
    elif n >= 1_000:
        return f"{n / 1_000:.1f}천"
    return str(n)


# ============================================================
# 메인 UI
# ============================================================

# --- 사이드바 ---
with st.sidebar:
    st.header("⚙️ 설정")
    max_comments = st.slider(
        "수집할 최대 댓글 수",
        min_value=10,
        max_value=500,
        value=100,
        step=10,
        help="많이 수집할수록 API 할당량을 더 사용합니다."
    )
    st.markdown("---")
    st.markdown("""
    ### 📌 사용법
    1. 유튜브 영상 링크를 입력합니다
    2. **댓글 수집** 버튼을 클릭합니다
    3. 댓글을 확인하고 CSV로 다운로드합니다
    
    ### 🔗 지원하는 링크 형식
    - `https://www.youtube.com/watch?v=XXXXX`
    - `https://youtu.be/XXXXX`
    - `https://www.youtube.com/shorts/XXXXX`
    - 영상 ID만 입력해도 됩니다
    """)
    st.markdown("---")
    st.markdown("""
    ### 🔑 API 키 발급 방법
    1. [Google Cloud Console](https://console.cloud.google.com/) 접속
    2. 새 프로젝트 생성
    3. **YouTube Data API v3** 활성화
    4. **사용자 인증 정보** → API 키 생성
    5. Streamlit Cloud **Secrets**에 등록
    """)

# --- 입력 영역 ---
col_input, col_button = st.columns([4, 1])
with col_input:
    url_input = st.text_input(
        "🔗 유튜브 영상 링크를 입력하세요",
        placeholder="https://www.youtube.com/watch?v=...",
        label_visibility="collapsed"
    )
with col_button:
    search_clicked = st.button("🔍 댓글 수집", type="primary", use_container_width=True)

# --- 수집 로직 ---
if search_clicked and url_input:
    video_id = extract_video_id(url_input.strip())

    if not video_id:
        st.error("❌ 올바른 유튜브 링크를 입력해주세요.")
    else:
        youtube = get_youtube_service()
        if not youtube:
            st.error("❌ YouTube API 키가 설정되지 않았습니다. Secrets에 `YOUTUBE_API_KEY`를 등록해주세요.")
        else:
            # 영상 정보 로딩
            with st.spinner("📡 영상 정보를 불러오는 중..."):
                video_info = get_video_info(youtube, video_id)

            if not video_info:
                st.error("❌ 영상 정보를 가져올 수 없습니다. 링크를 확인해주세요.")
            else:
                # ---- 영상 정보 표시 ----
                st.markdown("---")
                col_thumb, col_info = st.columns([1, 2])
                with col_thumb:
                    if video_info["thumbnail"]:
                        st.image(video_info["thumbnail"], use_container_width=True)
                with col_info:
                    st.subheader(video_info["title"])
                    st.caption(f"📺 {video_info['channel']}  |  📅 {video_info['published']}")

                    stat1, stat2, stat3 = st.columns(3)
                    with stat1:
                        st.metric("👁️ 조회수", format_number(video_info["view_count"]))
                    with stat2:
                        st.metric("👍 좋아요", format_number(video_info["like_count"]))
                    with stat3:
                        st.metric("💬 댓글 수", format_number(video_info["comment_count"]))

                # ---- 댓글 수집 ----
                st.markdown("---")
                with st.spinner(f"💬 댓글을 수집하는 중... (최대 {max_comments}개)"):
                    comments = get_comments(youtube, video_id, max_comments)

                if comments:
                    st.success(f"✅ 총 **{len(comments)}개**의 댓글을 수집했습니다!")

                    # 데이터프레임 생성
                    df = pd.DataFrame(comments)
                    df = df.sort_values(by="좋아요", ascending=False).reset_index(drop=True)
                    df.index = df.index + 1  # 1번부터 시작

                    # 탭 구성
                    tab1, tab2 = st.tabs(["📋 카드 보기", "📊 테이블 보기"])

                    with tab1:
                        # 정렬 옵션
                        sort_option = st.selectbox(
                            "정렬 기준",
                            ["좋아요 많은 순", "최신순", "오래된 순"],
                            index=0
                        )
                        if sort_option == "좋아요 많은 순":
                            display_df = df.sort_values(by="좋아요", ascending=False)
                        elif sort_option == "최신순":
                            display_df = df.sort_values(by="작성일", ascending=False)
                        else:
                            display_df = df.sort_values(by="작성일", ascending=True)

                        # 댓글 카드 표시
                        for _, row in display_df.iterrows():
                            st.markdown(f"""
                            <div class="comment-box">
                                <div class="comment-author">{row['작성자']}</div>
                                <div class="comment-date">📅 {row['작성일']}</div>
                                <div class="comment-text">{row['댓글']}</div>
                                <div class="comment-likes">❤️ 좋아요 {row['좋아요']}개</div>
                            </div>
                            """, unsafe_allow_html=True)

                    with tab2:
                        st.dataframe(df, use_container_width=True, height=500)

                    # CSV 다운로드
                    st.markdown("---")
                    csv_data = df.to_csv(index=False, encoding="utf-8-sig")
                    st.download_button(
                        label="📥 CSV 파일 다운로드",
                        data=csv_data,
                        file_name=f"youtube_comments_{video_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        type="primary",
                        use_container_width=True
                    )
                else:
                    st.warning("⚠️ 수집된 댓글이 없습니다.")

elif search_clicked and not url_input:
    st.warning("⚠️ 유튜브 링크를 입력해주세요.")

# --- 푸터 ---
st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:#999; font-size:0.85rem;'>"
    "당곡고등학교 학습용 유튜브 댓글 수집기 🎓"
    "</div>",
    unsafe_allow_html=True
)
