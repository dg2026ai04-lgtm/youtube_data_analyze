import streamlit as st
import pandas as pd
import re
import os
from datetime import datetime
from collections import Counter

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from wordcloud import WordCloud

# ── KoNLPy는 설치 실패할 수 있으므로 예외 처리 ──
try:
    from konlpy.tag import Okt
    OKT_AVAILABLE = True
except ImportError:
    OKT_AVAILABLE = False

# ============================================================
# 한글 폰트 설정 (Streamlit Cloud + 로컬 모두 지원)
# ============================================================
def get_font_path():
    """나눔고딕 폰트 경로를 찾습니다."""
    # Streamlit Cloud (packages.txt로 설치)
    cloud_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
    if os.path.exists(cloud_path):
        return cloud_path
    # 로컬 Windows
    win_path = "C:/Windows/Fonts/malgun.ttf"
    if os.path.exists(win_path):
        return win_path
    # 로컬 Mac
    mac_path = "/Library/Fonts/AppleGothic.ttf"
    if os.path.exists(mac_path):
        return mac_path
    return None

FONT_PATH = get_font_path()
if FONT_PATH:
    font_prop = fm.FontProperties(fname=FONT_PATH)
    plt.rcParams["font.family"] = font_prop.get_name()
    plt.rcParams["axes.unicode_minus"] = False

# ============================================================
# 페이지 설정
# ============================================================
st.set_page_config(
    page_title="유튜브 댓글 분석기",
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
        margin-bottom: 0.3rem;
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
        line-height: 1.6;
    }
    .comment-likes {
        color: #FF0000;
        font-size: 0.85rem;
        margin-top: 4px;
    }
    .keyword-highlight {
        background-color: #FFEB3B;
        padding: 1px 4px;
        border-radius: 3px;
        font-weight: bold;
    }
    .stat-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 18px;
        border-radius: 12px;
        text-align: center;
        margin-bottom: 10px;
    }
    .stat-box h3 {
        margin: 0;
        font-size: 1.8rem;
        color: white;
    }
    .stat-box p {
        margin: 5px 0 0 0;
        font-size: 0.9rem;
        opacity: 0.9;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 헤더
# ============================================================
st.markdown('<div class="main-header">🎬 유튜브 댓글 분석기</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">유튜브 영상의 댓글을 수집하고 분석합니다</div>', unsafe_allow_html=True)

# ============================================================
# 유틸리티 함수들
# ============================================================
def extract_video_id(url: str):
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


def get_video_info(youtube, video_id: str):
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


def get_comments(youtube, video_id: str, max_comments: int = 100):
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


def extract_nouns(text_list):
    """텍스트 리스트에서 명사를 추출합니다."""
    all_text = " ".join(text_list)

    if OKT_AVAILABLE:
        okt = Okt()
        nouns = okt.nouns(all_text)
        # 1글자 제거
        nouns = [n for n in nouns if len(n) > 1]
        return nouns
    else:
        # KoNLPy 없을 때: 간단한 공백 기반 분리
        words = re.findall(r'[가-힣a-zA-Z]{2,}', all_text)
        return words


def get_stopwords():
    """불용어 리스트를 반환합니다."""
    return {
        "ㅋㅋ", "ㅎㅎ", "ㅠㅠ", "ㅜㅜ", "ㄹㅇ", "ㅇㅇ",
        "진짜", "정말", "너무", "그냥", "이거", "저거", "거기",
        "하는", "되는", "있는", "없는", "같은", "라는",
        "근데", "그런", "이런", "저런", "대박", "마이",
        "합니다", "입니다", "습니다", "됩니다", "있습", "없습",
        "것이", "하고", "에서", "으로", "까지", "부터",
        "the", "is", "at", "it", "to", "and", "or", "of",
        "for", "in", "on", "be", "this", "that", "with",
    }


def highlight_keyword(text, keyword):
    """텍스트에서 키워드를 하이라이트합니다."""
    if not keyword:
        return text
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    highlighted = pattern.sub(
        f'<span class="keyword-highlight">{keyword}</span>',
        text
    )
    return highlighted


# ============================================================
# 사이드바
# ============================================================
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
    1. 유튜브 영상 링크 입력
    2. **댓글 수집** 버튼 클릭
    3. 다양한 탭에서 분석 결과 확인
    4. CSV로 다운로드 가능
    
    ### 🔗 지원하는 링크 형식
    - `youtube.com/watch?v=...`
    - `youtu.be/...`
    - `youtube.com/shorts/...`
    - 영상 ID만 입력도 가능
    """)

# ============================================================
# 메인 입력 영역
# ============================================================
col_input, col_button = st.columns([4, 1])
with col_input:
    url_input = st.text_input(
        "🔗 유튜브 영상 링크를 입력하세요",
        placeholder="https://www.youtube.com/watch?v=...",
        label_visibility="collapsed"
    )
with col_button:
    search_clicked = st.button("🔍 댓글 수집", type="primary", use_container_width=True)

# ============================================================
# 세션 상태 관리 (댓글 데이터 유지)
# ============================================================
if "comments_data" not in st.session_state:
    st.session_state.comments_data = None
if "video_info" not in st.session_state:
    st.session_state.video_info = None
if "video_id" not in st.session_state:
    st.session_state.video_id = None

# ============================================================
# 수집 로직
# ============================================================
if search_clicked and url_input:
    video_id = extract_video_id(url_input.strip())

    if not video_id:
        st.error("❌ 올바른 유튜브 링크를 입력해주세요.")
    else:
        youtube = get_youtube_service()
        if not youtube:
            st.error("❌ YouTube API 키가 설정되지 않았습니다. Secrets에 `YOUTUBE_API_KEY`를 등록해주세요.")
        else:
            with st.spinner("📡 영상 정보를 불러오는 중..."):
                video_info = get_video_info(youtube, video_id)

            if not video_info:
                st.error("❌ 영상 정보를 가져올 수 없습니다. 링크를 확인해주세요.")
            else:
                with st.spinner(f"💬 댓글을 수집하는 중... (최대 {max_comments}개)"):
                    comments = get_comments(youtube, video_id, max_comments)

                if comments:
                    st.session_state.comments_data = comments
                    st.session_state.video_info = video_info
                    st.session_state.video_id = video_id
                    st.success(f"✅ 총 **{len(comments)}개**의 댓글을 수집했습니다!")
                else:
                    st.warning("⚠️ 수집된 댓글이 없습니다.")

elif search_clicked and not url_input:
    st.warning("⚠️ 유튜브 링크를 입력해주세요.")

# ============================================================
# 데이터가 있을 때 대시보드 표시
# ============================================================
if st.session_state.comments_data and st.session_state.video_info:

    comments = st.session_state.comments_data
    video_info = st.session_state.video_info
    video_id = st.session_state.video_id
    df = pd.DataFrame(comments)

    # ── 영상 정보 ──
    st.markdown("---")
    col_thumb, col_info = st.columns([1, 2])
    with col_thumb:
        if video_info["thumbnail"]:
            st.image(video_info["thumbnail"], use_container_width=True)
    with col_info:
        st.subheader(video_info["title"])
        st.caption(f"📺 {video_info['channel']}  |  📅 {video_info['published']}")

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("👁️ 조회수", format_number(video_info["view_count"]))
        with m2:
            st.metric("👍 좋아요", format_number(video_info["like_count"]))
        with m3:
            st.metric("💬 총 댓글", format_number(video_info["comment_count"]))
        with m4:
            st.metric("📥 수집 댓글", f"{len(comments)}개")

    st.markdown("---")

    # ============================================================
    # 탭 구성: 대시보드 / 댓글 목록 / 키워드 검색 / 워드클라우드
    # ============================================================
    tab_dashboard, tab_comments, tab_search, tab_wordcloud = st.tabs([
        "📊 대시보드", "💬 댓글 목록", "🔍 키워드 검색", "☁️ 워드클라우드"
    ])

    # ================================================================
    # 📊 탭 1: 대시보드
    # ================================================================
    with tab_dashboard:
        st.subheader("📊 댓글 분석 대시보드")

        # ── 기본 통계 카드 ──
        avg_likes = df["좋아요"].mean()
        max_likes = df["좋아요"].max()
        avg_length = df["댓글"].str.len().mean()
        unique_authors = df["작성자"].nunique()

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f"""
            <div class="stat-box">
                <h3>{avg_likes:.1f}</h3>
                <p>평균 좋아요 수</p>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown(f"""
            <div class="stat-box">
                <h3>{max_likes}</h3>
                <p>최대 좋아요 수</p>
            </div>
            """, unsafe_allow_html=True)
        with c3:
            st.markdown(f"""
            <div class="stat-box">
                <h3>{avg_length:.0f}자</h3>
                <p>평균 댓글 길이</p>
            </div>
            """, unsafe_allow_html=True)
        with c4:
            st.markdown(f"""
            <div class="stat-box">
                <h3>{unique_authors}명</h3>
                <p>댓글 작성자 수</p>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("")

        # ── 차트 영역 ──
        chart_col1, chart_col2 = st.columns(2)

        # 좋아요 TOP 10
        with chart_col1:
            st.markdown("#### ❤️ 좋아요 TOP 10 댓글")
            top10 = df.nlargest(10, "좋아요")[["작성자", "댓글", "좋아요"]].reset_index(drop=True)
            top10.index = top10.index + 1

            fig1, ax1 = plt.subplots(figsize=(8, 5))
            bars = ax1.barh(
                range(len(top10)),
                top10["좋아요"],
                color=["#FF0000" if i == 0 else "#FF6666" if i < 3 else "#FFAAAA" for i in range(len(top10))]
            )
            ax1.set_yticks(range(len(top10)))
            labels = [f"{row['작성자'][:8]}..." if len(row['작성자']) > 8 else row['작성자'] for _, row in top10.iterrows()]
            ax1.set_yticklabels(labels)
            ax1.invert_yaxis()
            ax1.set_xlabel("좋아요 수")
            ax1.set_title("좋아요 많은 댓글 TOP 10")

            for bar, val in zip(bars, top10["좋아요"]):
                ax1.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                         str(val), va="center", fontsize=9)

            plt.tight_layout()
            st.pyplot(fig1)
            plt.close(fig1)

        # 날짜별 댓글 수
        with chart_col2:
            st.markdown("#### 📅 날짜별 댓글 수 추이")
            df_date = df.copy()
            df_date["작성일"] = pd.to_datetime(df_date["작성일"], errors="coerce")
            date_counts = df_date.groupby(df_date["작성일"].dt.date).size().reset_index(name="댓글수")
            date_counts.columns = ["날짜", "댓글수"]
            date_counts = date_counts.sort_values("날짜")

            if len(date_counts) > 1:
                fig2, ax2 = plt.subplots(figsize=(8, 5))
                ax2.fill_between(date_counts["날짜"], date_counts["댓글수"], alpha=0.3, color="#FF0000")
                ax2.plot(date_counts["날짜"], date_counts["댓글수"], color="#FF0000", linewidth=2, marker="o", markersize=4)
                ax2.set_xlabel("날짜")
                ax2.set_ylabel("댓글 수")
                ax2.set_title("날짜별 댓글 수 변화")
                plt.xticks(rotation=45)
                plt.tight_layout()
                st.pyplot(fig2)
                plt.close(fig2)
            else:
                st.info("날짜별 추이를 그리기에 데이터가 부족합니다.")

        # ── 댓글 길이 분포 + 활발한 댓글러 ──
        chart_col3, chart_col4 = st.columns(2)

        with chart_col3:
            st.markdown("#### 📏 댓글 길이 분포")
            df_len = df["댓글"].str.len()

            fig3, ax3 = plt.subplots(figsize=(8, 5))
            ax3.hist(df_len, bins=30, color="#FF6666", edgecolor="white", alpha=0.8)
            ax3.axvline(df_len.mean(), color="#FF0000", linestyle="--", linewidth=2, label=f"평균: {df_len.mean():.0f}자")
            ax3.set_xlabel("댓글 길이 (글자 수)")
            ax3.set_ylabel("댓글 수")
            ax3.set_title("댓글 길이 분포")
            ax3.legend()
            plt.tight_layout()
            st.pyplot(fig3)
            plt.close(fig3)

        with chart_col4:
            st.markdown("#### 👤 활발한 댓글러 TOP 10")
            author_counts = df["작성자"].value_counts().head(10)

            if len(author_counts) > 0:
                fig4, ax4 = plt.subplots(figsize=(8, 5))
                colors = plt.cm.Reds(
                    [0.9 - i * 0.07 for i in range(len(author_counts))]
                )
                bars = ax4.barh(range(len(author_counts)), author_counts.values, color=colors)
                labels = [n[:10] + "..." if len(n) > 10 else n for n in author_counts.index]
                ax4.set_yticks(range(len(author_counts)))
                ax4.set_yticklabels(labels)
                ax4.invert_yaxis()
                ax4.set_xlabel("댓글 수")
                ax4.set_title("가장 많이 댓글 단 사용자")

                for bar, val in zip(bars, author_counts.values):
                    ax4.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                             str(val), va="center", fontsize=9)

                plt.tight_layout()
                st.pyplot(fig4)
                plt.close(fig4)

    # ================================================================
    # 💬 탭 2: 댓글 목록
    # ================================================================
    with tab_comments:
        st.subheader("💬 수집된 댓글 목록")

        # 정렬 옵션
        sort_option = st.selectbox(
            "정렬 기준",
            ["좋아요 많은 순", "좋아요 적은 순", "최신순", "오래된 순", "댓글 긴 순", "댓글 짧은 순"],
            index=0,
            key="comment_sort"
        )

        display_df = df.copy()
        if sort_option == "좋아요 많은 순":
            display_df = display_df.sort_values("좋아요", ascending=False)
        elif sort_option == "좋아요 적은 순":
            display_df = display_df.sort_values("좋아요", ascending=True)
        elif sort_option == "최신순":
            display_df = display_df.sort_values("작성일", ascending=False)
        elif sort_option == "오래된 순":
            display_df = display_df.sort_values("작성일", ascending=True)
        elif sort_option == "댓글 긴 순":
            display_df["_len"] = display_df["댓글"].str.len()
            display_df = display_df.sort_values("_len", ascending=False).drop(columns=["_len"])
        elif sort_option == "댓글 짧은 순":
            display_df["_len"] = display_df["댓글"].str.len()
            display_df = display_df.sort_values("_len", ascending=True).drop(columns=["_len"])

        display_df = display_df.reset_index(drop=True)

        # 보기 방식 선택
        view_mode = st.radio("보기 방식", ["카드 보기", "테이블 보기"], horizontal=True, key="view_mode")

        if view_mode == "카드 보기":
            # 페이지네이션
            items_per_page = 20
            total_pages = max(1, (len(display_df) - 1) // items_per_page + 1)
            page = st.number_input("페이지", min_value=1, max_value=total_pages, value=1, key="page_comments")
            start_idx = (page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            st.caption(f"📄 {page}/{total_pages} 페이지  |  총 {len(display_df)}개 댓글")

            for _, row in display_df.iloc[start_idx:end_idx].iterrows():
                st.markdown(f"""
                <div class="comment-box">
                    <div class="comment-author">{row['작성자']}</div>
                    <div class="comment-date">📅 {row['작성일']}</div>
                    <div class="comment-text">{row['댓글']}</div>
                    <div class="comment-likes">❤️ 좋아요 {row['좋아요']}개</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            table_df = display_df.copy().reset_index(drop=True)
            table_df.index = table_df.index + 1
            st.dataframe(table_df, use_container_width=True, height=500)

    # ================================================================
    # 🔍 탭 3: 키워드 검색
    # ================================================================
    with tab_search:
        st.subheader("🔍 댓글 키워드 검색")

        search_col1, search_col2 = st.columns([3, 1])
        with search_col1:
            keyword = st.text_input(
                "검색할 키워드를 입력하세요",
                placeholder="예: 재밌다, 감동, 최고...",
                key="keyword_input"
            )
        with search_col2:
            case_sensitive = st.checkbox("대소문자 구분", value=False)

        if keyword:
            if case_sensitive:
                mask = df["댓글"].str.contains(keyword, na=False)
            else:
                mask = df["댓글"].str.contains(keyword, case=False, na=False)

            filtered = df[mask].reset_index(drop=True)

            # 검색 결과 통계
            result_pct = (len(filtered) / len(df) * 100) if len(df) > 0 else 0

            rc1, rc2, rc3 = st.columns(3)
            with rc1:
                st.metric("🔎 검색 결과", f"{len(filtered)}개")
            with rc2:
                st.metric("📊 전체 대비", f"{result_pct:.1f}%")
            with rc3:
                avg_likes_filtered = filtered["좋아요"].mean() if len(filtered) > 0 else 0
                st.metric("❤️ 평균 좋아요", f"{avg_likes_filtered:.1f}")

            if len(filtered) > 0:
                st.markdown("---")

                # 정렬
                search_sort = st.selectbox(
                    "정렬",
                    ["좋아요 많은 순", "최신순", "오래된 순"],
                    key="search_sort"
                )
                if search_sort == "좋아요 많은 순":
                    filtered = filtered.sort_values("좋아요", ascending=False)
                elif search_sort == "최신순":
                    filtered = filtered.sort_values("작성일", ascending=False)
                else:
