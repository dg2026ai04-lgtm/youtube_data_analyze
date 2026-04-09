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


# ============================================================
# 한글 폰트 설정
# ============================================================
def get_font_path():
    paths = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "/Library/Fonts/AppleGothic.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
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
# CSS 스타일
# ============================================================
st.markdown("""
<style>
.main-header{font-size:2.5rem;font-weight:bold;text-align:center;color:#FF0000;margin-bottom:.3rem}
.sub-header{font-size:1.1rem;text-align:center;color:#666;margin-bottom:2rem}
.comment-box{background:#f9f9f9;border-left:4px solid #FF0000;padding:12px 16px;margin-bottom:10px;border-radius:0 8px 8px 0}
.comment-author{font-weight:bold;color:#333;font-size:.95rem}
.comment-date{color:#999;font-size:.8rem}
.comment-text{margin-top:6px;color:#444;line-height:1.6}
.comment-likes{color:#FF0000;font-size:.85rem;margin-top:4px}
.keyword-highlight{background:#FFEB3B;padding:1px 4px;border-radius:3px;font-weight:bold}
.stat-box{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:18px;border-radius:12px;text-align:center;margin-bottom:10px}
.stat-box h3{margin:0;font-size:1.8rem;color:#fff}
.stat-box p{margin:5px 0 0;font-size:.9rem;opacity:.9}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">🎬 유튜브 댓글 분석기</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">유튜브 영상의 댓글을 수집하고 분석합니다</div>', unsafe_allow_html=True)


# ============================================================
# 함수 모음
# ============================================================
def extract_video_id(url):
    patterns = [
        r'(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def get_youtube_service():
    key = st.secrets.get("YOUTUBE_API_KEY", None)
    if not key:
        return None
    return build("youtube", "v3", developerKey=key)


def get_video_info(yt, vid):
    try:
        res = yt.videos().list(part="snippet,statistics", id=vid).execute()
        if res["items"]:
            s = res["items"][0]["snippet"]
            t = res["items"][0]["statistics"]
            return {
                "title": s.get("title", ""),
                "channel": s.get("channelTitle", ""),
                "published": s.get("publishedAt", "")[:10],
                "thumbnail": s.get("thumbnails", {}).get("high", {}).get("url", ""),
                "view_count": int(t.get("viewCount", 0)),
                "like_count": int(t.get("likeCount", 0)),
                "comment_count": int(t.get("commentCount", 0)),
            }
    except HttpError:
        pass
    return None


def get_comments(yt, vid, max_c=100):
    comments = []
    npt = None
    try:
        while len(comments) < max_c:
            res = yt.commentThreads().list(
                part="snippet",
                videoId=vid,
                maxResults=min(100, max_c - len(comments)),
                pageToken=npt,
                order="relevance",
                textFormat="plainText"
            ).execute()
            for item in res.get("items", []):
                top = item["snippet"]["topLevelComment"]["snippet"]
                comments.append({
                    "작성자": top.get("authorDisplayName", ""),
                    "댓글": top.get("textDisplay", ""),
                    "좋아요": top.get("likeCount", 0),
                    "작성일": top.get("publishedAt", "")[:10],
                })
            npt = res.get("nextPageToken")
            if not npt:
                break
    except HttpError as e:
        if "commentsDisabled" in str(e):
            st.error("이 영상은 댓글이 비활성화되어 있습니다.")
        else:
            st.error(f"API 오류: {e}")
        return []
    return comments


def fmt(n):
    if n >= 1e8:
        return f"{n / 1e8:.1f}억"
    if n >= 1e4:
        return f"{n / 1e4:.1f}만"
    if n >= 1e3:
        return f"{n / 1e3:.1f}천"
    return str(n)


def get_stopwords():
    return {
        "진짜", "정말", "너무", "그냥", "이거", "저거", "거기",
        "하는", "되는", "있는", "없는", "같은", "라는",
        "근데", "그런", "이런", "저런", "대박",
        "합니다", "입니다", "습니다", "됩니다", "있습", "없습",
        "것이", "하고", "에서", "으로", "까지", "부터",
        "그리고", "그래서", "했는데", "인데", "는데",
        "the", "is", "at", "it", "to", "and", "or", "of",
        "for", "in", "on", "be", "this", "that", "with",
    }


def extract_words(texts):
    all_text = " ".join(texts)
    words = re.findall(r'[가-힣a-zA-Z]{2,}', all_text)
    sw = get_stopwords()
    return [w for w in words if w not in sw]


def highlight_keyword(text, kw):
    if not kw:
        return text
    return re.compile(re.escape(kw), re.IGNORECASE).sub(
        f'<span class="keyword-highlight">{kw}</span>', text
    )


# ============================================================
# 사이드바
# ============================================================
with st.sidebar:
    st.header("설정")
    max_comments = st.slider("수집할 최대 댓글 수", 10, 500, 100, 10)
    st.markdown("---")
    st.markdown("""
### 사용법
1. 유튜브 영상 링크 입력
2. 댓글 수집 버튼 클릭
3. 탭에서 분석 결과 확인
4. CSV 다운로드 가능

### 지원 링크
- `youtube.com/watch?v=...`
- `youtu.be/...`
- `youtube.com/shorts/...`
- 영상 ID만 입력도 OK
    """)


# ============================================================
# 입력 영역
# ============================================================
col_in, col_btn = st.columns([4, 1])
with col_in:
    url_input = st.text_input(
        "링크",
        placeholder="https://www.youtube.com/watch?v=...",
        label_visibility="collapsed"
    )
with col_btn:
    clicked = st.button("🔍 댓글 수집", type="primary", use_container_width=True)


# ============================================================
# 세션 상태
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
if clicked and url_input:
    vid = extract_video_id(url_input.strip())
    if not vid:
        st.error("올바른 유튜브 링크를 입력해주세요.")
    else:
        yt = get_youtube_service()
        if not yt:
            st.error("API 키가 없습니다. Secrets에 YOUTUBE_API_KEY를 등록하세요.")
        else:
            with st.spinner("영상 정보를 불러오는 중..."):
                vi = get_video_info(yt, vid)
            if not vi:
                st.error("영상 정보를 가져올 수 없습니다.")
            else:
                with st.spinner(f"댓글 수집 중... (최대 {max_comments}개)"):
                    cm = get_comments(yt, vid, max_comments)
                if cm:
                    st.session_state.comments_data = cm
                    st.session_state.video_info = vi
                    st.session_state.video_id = vid
                    st.success(f"총 {len(cm)}개 댓글 수집 완료!")
                else:
                    st.warning("수집된 댓글이 없습니다.")
elif clicked:
    st.warning("링크를 입력해주세요.")


# ============================================================
# 메인 대시보드 (데이터가 있을 때만 표시)
# ============================================================
if st.session_state.comments_data and st.session_state.video_info:
    comments = st.session_state.comments_data
    video_info = st.session_state.video_info
    video_id = st.session_state.video_id
    df = pd.DataFrame(comments)

    # ── 영상 정보 표시 ──
    st.markdown("---")
    col_thumb, col_info = st.columns([1, 2])
    with col_thumb:
        if video_info["thumbnail"]:
            st.image(video_info["thumbnail"], use_container_width=True)
    with col_info:
        st.subheader(video_info["title"])
        st.caption(f"📺 {video_info['channel']}  |  📅 {video_info['published']}")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("👁️ 조회수", fmt(video_info["view_count"]))
        m2.metric("👍 좋아요", fmt(video_info["like_count"]))
        m3.metric("💬 총 댓글", fmt(video_info["comment_count"]))
        m4.metric("📥 수집", f"{len(comments)}개")

    st.markdown("---")

    # ── 4개 탭 ──
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 대시보드",
        "💬 댓글 목록",
        "🔍 키워드 검색",
        "☁️ 워드클라우드"
    ])

    # ==========================================================
    # 탭1: 대시보드
    # ==========================================================
    with tab1:
        st.subheader("📊 댓글 분석 대시보드")

        avg_likes = df["좋아요"].mean()
        max_likes = df["좋아요"].max()
        avg_len = df["댓글"].str.len().mean()
        uniq = df["작성자"].nunique()

        s1, s2, s3, s4 = st.columns(4)
        s1.markdown(
            f'<div class="stat-box"><h3>{avg_likes:.1f}</h3><p>평균 좋아요</p></div>',
            unsafe_allow_html=True
        )
        s2.markdown(
            f'<div class="stat-box"><h3>{max_likes}</h3><p>최대 좋아요</p></div>',
            unsafe_allow_html=True
        )
        s3.markdown(
            f'<div class="stat-box"><h3>{avg_len:.0f}자</h3><p>평균 댓글 길이</p></div>',
            unsafe_allow_html=True
        )
        s4.markdown(
            f'<div class="stat-box"><h3>{uniq}명</h3><p>작성자 수</p></div>',
            unsafe_allow_html=True
        )

        st.markdown("")
        ch1, ch2 = st.columns(2)

        with ch1:
            st.markdown("#### ❤️ 좋아요 TOP 10")
            top10 = df.nlargest(10, "좋아요")[["작성자", "좋아요"]].reset_index(drop=True)
            fig1, ax1 = plt.subplots(figsize=(7, 4))
            colors = [
                "#FF0000" if i == 0 else "#FF6666" if i < 3 else "#FFAAAA"
                for i in range(len(top10))
            ]
            bars = ax1.barh(range(len(top10)), top10["좋아요"], color=colors)
            labels = [
                n[:8] + "..." if len(n) > 8 else n
                for n in top10["작성자"]
            ]
            ax1.set_yticks(range(len(top10)))
            ax1.set_yticklabels(labels)
            ax1.invert_yaxis()
            ax1.set_xlabel("좋아요 수")
            for b, v in zip(bars, top10["좋아요"]):
                ax1.text(
                    b.get_width() + 0.3,
                    b.get_y() + b.get_height() / 2,
                    str(v), va="center", fontsize=9
                )
            plt.tight_layout()
            st.pyplot(fig1)
            plt.close(fig1)

        with ch2:
            st.markdown("#### 📅 날짜별 댓글 수")
            dfd = df.copy()
            dfd["작성일"] = pd.to_datetime(dfd["작성일"], errors="coerce")
            dc = dfd.groupby(dfd["작성일"].dt.date).size().reset_index(name="댓글수")
            dc.columns = ["날짜", "댓글수"]
            dc = dc.sort_values("날짜")
            if len(dc) > 1:
                fig2, ax2 = plt.subplots(figsize=(7, 4))
                ax2.fill_between(dc["날짜"], dc["댓글수"], alpha=0.3, color="#FF0000")
                ax2.plot(
                    dc["날짜"], dc["댓글수"],
                    color="#FF0000", linewidth=2, marker="o", markersize=4
                )
                ax2.set_xlabel("날짜")
                ax2.set_ylabel("댓글 수")
                plt.xticks(rotation=45)
                plt.tight_layout()
                st.pyplot(fig2)
                plt.close(fig2)
            else:
                st.info("날짜 데이터가 부족합니다.")

        ch3, ch4 = st.columns(2)

        with ch3:
            st.markdown("#### 📏 댓글 길이 분포")
            lens = df["댓글"].str.len()
            fig3, ax3 = plt.subplots(figsize=(7, 4))
            ax3.hist(lens, bins=30, color="#FF6666", edgecolor="white", alpha=0.8)
            ax3.axvline(
                lens.mean(), color="#FF0000", linestyle="--",
                linewidth=2, label=f"평균 {lens.mean():.0f}자"
            )
            ax3.set_xlabel("글자 수")
            ax3.set_ylabel("댓글 수")
            ax3.legend()
            plt.tight_layout()
            st.pyplot(fig3)
            plt.close(fig3)

        with ch4:
            st.markdown("#### 👤 활발한 댓글러 TOP 10")
            ac = df["작성자"].value_counts().head(10)
            fig4, ax4 = plt.subplots(figsize=(7, 4))
            colors4 = plt.cm.Reds([0.9 - i * 0.07 for i in range(len(ac))])
            bars4 = ax4.barh(range(len(ac)), ac.values, color=colors4)
            labels4 = [
                n[:10] + "..." if len(n) > 10 else n
                for n in ac.index
            ]
            ax4.set_yticks(range(len(ac)))
            ax4.set_yticklabels(labels4)
            ax4.invert_yaxis()
            ax4.set_xlabel("댓글 수")
            for b, v in zip(bars4, ac.values):
                ax4.text(
                    b.get_width() + 0.1,
                    b.get_y() + b.get_height() / 2,
                    str(v), va="center", fontsize=9
                )
            plt.tight_layout()
            st.pyplot(fig4)
            plt.close(fig4)

    # ==========================================================
    # 탭2: 댓글 목록
    # ==========================================================
    with tab2:
        st.subheader("💬 수집된 댓글 목록")

        sort_opt = st.selectbox(
            "정렬",
            ["좋아요 많은 순", "좋아요 적은 순", "최신순", "오래된 순"],
            key="t2_sort"
        )
        dfs = df.copy()
        if sort_opt == "좋아요 많은 순":
            dfs = dfs.sort_values("좋아요", ascending=False)
        elif sort_opt == "좋아요 적은 순":
            dfs = dfs.sort_values("좋아요", ascending=True)
        elif sort_opt == "최신순":
            dfs = dfs.sort_values("작성일", ascending=False)
        else:
            dfs = dfs.sort_values("작성일", ascending=True)
        dfs = dfs.reset_index(drop=True)

        view = st.radio("보기 방식", ["카드", "테이블"], horizontal=True, key="t2_view")

        if view == "카드":
            per = 20
            total_p = max(1, (len(dfs) - 1) // per + 1)
            pg = st.number_input("페이지", 1, total_p, 1, key="t2_pg")
            st.caption(f"📄 {pg}/{total_p} 페이지  |  총 {len(dfs)}개")
            start = (pg - 1) * per
            end = pg * per
            for _, r in dfs.iloc[start:end].iterrows():
                st.markdown(f"""
                <div class="comment-box">
                    <div class="comment-author">{r['작성자']}</div>
                    <div class="comment-date">📅 {r['작성일']}</div>
                    <div class="comment-text">{r['댓글']}</div>
                    <div class="comment-likes">❤️ 좋아요 {r['좋아요']}개</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            tbl = dfs.copy()
            tbl.index = range(1, len(tbl) + 1)
            st.dataframe(tbl, use_container_width=True, height=500)

    # ==========================================================
    # 탭3: 키워드 검색
    # ==========================================================
    with tab3:
        st.subheader("🔍 댓글 키워드 검색")

        keyword = st.text_input(
            "검색 키워드",
            placeholder="예: 재밌다, 감동, 최고...",
            key="kw_in"
        )

        if keyword:
            mask = df["댓글"].str.contains(keyword, case=False, na=False)
            filt = df[mask].reset_index(drop=True)
            pct = len(filt) / len(df) * 100 if len(df) > 0 else 0
            avg_l = filt["좋아요"].mean() if len(filt) > 0 else 0

            r1, r2, r3 = st.columns(3)
            r1.metric("🔎 결과", f"{len(filt)}개")
            r2.metric("📊 비율", f"{pct:.1f}%")
            r3.metric("❤️ 평균 좋아요", f"{avg_l:.1f}")

            if len(filt) > 0:
                st.markdown("---")
                ss = st.selectbox(
                    "정렬",
                    ["좋아요 많은 순", "최신순", "오래된 순"],
                    key="kw_sort"
                )
                if ss == "좋아요 많은 순":
                    filt = filt.sort_values("좋아요", ascending=False)
                elif ss == "최신순":
                    filt = filt.sort_values("작성일", ascending=False)
                else:
                    filt = filt.sort_values("작성일", ascending=True)
                filt = filt.reset_index(drop=True)

                per2 = 20
                tp2 = max(1, (len(filt) - 1) // per2 + 1)
                pg2 = st.number_input("페이지", 1, tp2, 1, key="kw_pg")
                st.caption(f"📄 {pg2}/{tp2} 페이지  |  {len(filt)}개 결과")
                start2 = (pg2 - 1) * per2
                end2 = pg2 * per2
                for _, r in filt.iloc[start2:end2].iterrows():
                    hl = highlight_keyword(r["댓글"], keyword)
                    st.markdown(f"""
                    <div class="comment-box">
                        <div class="comment-author">{r['작성자']}</div>
                        <div class="comment-date">📅 {r['작성일']}</div>
                        <div class="comment-text">{hl}</div>
                        <div class="comment-likes">❤️ 좋아요 {r['좋아요']}개</div>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("---")
                csv_f = filt.to_csv(index=False, encoding="utf-8-sig")
                st.download_button(
                    "📥 검색 결과 CSV 다운로드",
                    csv_f,
                    f"search_{keyword}.csv",
                    "text/csv",
                    use_container_width=True
                )
            else:
                st.info(f'"{keyword}"가 포함된 댓글이 없습니다.')
        else:
            st.info("위에 키워드를 입력하면 해당 키워드가 포함된 댓글을 찾아줍니다.")

    # ==========================================================
    # 탭4: 워드클라우드
    # ==========================================================
    with tab4:
        st.subheader("☁️ 워드클라우드")

        words = extract_words(df["댓글"].tolist())
        word_counts = Counter(words)

        if word_counts and FONT_PATH:
            wc = WordCloud(
                font_path=FONT_PATH,
                width=1000,
                height=500,
                background_color="white",
                max_words=80,
                colormap="Reds",
            ).generate_from_frequencies(word_counts)

            fig_wc, ax_wc = plt.subplots(figsize=(12, 6))
            ax_wc.imshow(wc, interpolation="bilinear")
            ax_wc.axis("off")
            plt.tight_layout()
            st.pyplot(fig_wc)
            plt.close(fig_wc)

            st.markdown("---")
            st.markdown("#### 📋 자주 등장하는 단어 TOP 30")
            top30 = word_counts.most_common(30)
            wdf = pd.DataFrame(top30, columns=["단어", "빈도"])
            wdf.index = range(1, len(wdf) + 1)

            wc1, wc2 = st.columns(2)
            with wc1:
                st.dataframe(wdf, use_container_width=True)
            with wc2:
                top20 = wdf.head(20)
                fig_b, ax_b = plt.subplots(figsize=(7, 6))
                colors_b = plt.cm.Reds(
                    [0.4 + 0.6 * i / len(top20) for i in range(len(top20))]
                )[::-1]
                ax_b.barh(range(len(top20)), top20["빈도"], color=colors_b)
                ax_b.set_yticks(range(len(top20)))
                ax_b.set_yticklabels(top20["단어"])
                ax_b.invert_yaxis()
                ax_b.set_xlabel("빈도")
                ax_b.set_title("자주 등장하는 단어 TOP 20")
                plt.tight_layout()
                st.pyplot(fig_b)
                plt.close(fig_b)
        elif not FONT_PATH:
            st.warning("한글 폰트를 찾을 수 없어 워드클라우드를 생성할 수 없습니다.")
        else:
            st.warning("단어를 추출할 수 없습니다.")

    # ── 전체 CSV 다운로드 ──
    st.markdown("---")
    csv_all = df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "📥 전체 댓글 CSV 다운로드",
        csv_all,
        f"comments_{video_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        "text/csv",
        type="primary",
        use_container_width=True,
    )


# ── 푸터 ──
st.markdown("---")
st.markdown(
    '<div style="text-align:center;color:#999;font-size:.85rem">'
    '당곡고등학교 학습용 유튜브 댓글 분석기 🎓'
    '</div>',
    unsafe_allow_html=True
)
