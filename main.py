import os
import json
import re
import smtplib
import urllib.parse
import html
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import feedparser
import time
import calendar

# ---------------------------------------------------------
# 1. 설정 부분
# ---------------------------------------------------------
# 감지할 키워드 목록
# (※ "장애인" 키워드가 너무 많은 기사를 가져온다면 목록에서 "장애인"을 빼주시면 수어/농인 집중 모드가 됩니다.)
KEYWORDS = ["수어", "농인", "농아인", "수화", "농아인협회", "수어통역센터", "장애인"]

# 중복 발송 방지를 위한 기록 파일
LOG_FILE = "sent_articles.json"

# 최근 며칠 이내의 기사만 가져올지 설정 (2 = 최근 48시간 이내 기사만)
LIMIT_DAYS = 2
LIMIT_SECONDS = LIMIT_DAYS * 24 * 60 * 60

# 언론사별 전체기사 RSS 피드 주소
ABLE_NEWS_RSS = "https://www.ablenews.co.kr/rss/allArticle.xml"
BEMINOR_RSS = "https://www.beminor.com/rss/allArticle.xml"
WELFARE_NEWS_RSS = "https://www.welfarenews.net/rss/allArticle.xml"
SOCIAL_FOCUS_RSS = "https://www.socialfocus.co.kr/rss/allArticle.xml"

# 구글 뉴스(인터넷 종합 뉴스) 키워드 검색 RSS 피드
search_query = " OR ".join(KEYWORDS)
encoded_query = urllib.parse.quote(search_query)
GOOGLE_NEWS_RSS = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"

# 검사할 전체 피드 목록
RSS_FEEDS = [
    ABLE_NEWS_RSS, 
    BEMINOR_RSS, 
    WELFARE_NEWS_RSS, 
    SOCIAL_FOCUS_RSS, 
    GOOGLE_NEWS_RSS
]

# 출처(언론사) 명칭 매핑
FEED_NAMES = {
    ABLE_NEWS_RSS: "에이블뉴스",
    BEMINOR_RSS: "비마이너",
    WELFARE_NEWS_RSS: "웰페어뉴스",
    SOCIAL_FOCUS_RSS: "소셜포커스"
}


# ---------------------------------------------------------
# 2. 기능 구현 부분
# ---------------------------------------------------------
def clean_text(raw_html):
    """HTML 태그 제거 및 특수문자 변환"""
    if not raw_html:
        return ""
    clean_r = re.compile('<.*?>')
    clean_text = re.sub(clean_r, '', raw_html)
    return html.unescape(clean_text).strip()


def normalize_title(title):
    """중복 기사 방지를 위해 제목에서 특수문자와 공백을 제거한 기준값 생성"""
    return re.sub(r'[\W_]+', '', title)


def load_sent_articles():
    """이미 발송한 기사 식별자(링크 및 정규화된 제목) 불러오기"""
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"로그 파일 로드 실패: {e}")
            return set()
    return set()


def save_sent_articles(sent_list):
    """발송한 기사 식별자 저장 (최대 1500개 유지)"""
    trimmed_list = list(sent_list)[-1500:]
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed_list, f, ensure_ascii=False, indent=2)


def send_email(new_articles):
    """네이버 SMTP를 사용하여 등록된 모든 수신자에게 개별 발송"""
    naver_id = os.environ.get("NAVER_ID")
    naver_password = os.environ.get("NAVER_PASSWORD")
    recipient_email_str = os.environ.get("RECIPIENT_EMAIL")

    if not all([naver_id, naver_password, recipient_email_str]):
        print("이메일 환경변수가 설정되지 않아 메일을 전송할 수 없습니다.")
        return

    recipient_list = [email.strip() for email in recipient_email_str.split(",") if email.strip()]

    if not recipient_list:
        print("수신자 이메일 목록이 비어 있습니다.")
        return

    subject = f"[통합 뉴스 알림] 키워드 관련 새 소식 {len(new_articles)}건"
    
    articles_html = ""
    for idx, article in enumerate(new_articles, 1):
        matched_str = ", ".join(article["matched_keywords"])
        source_name = article.get('source', '인터넷 뉴스')
        
        articles_html += f"""
        <div style="margin-bottom: 20px; padding: 16px; border: 1px solid #e2e8f0; border-radius: 10px; background-color: #ffffff;">
            <div style="font-size: 12px; color: #64748b; margin-bottom: 6px;">
                <span style="background-color: #f1f5f9; padding: 2px 8px; border-radius: 4px; font-weight: bold; color: #475569;">{source_name}</span>
                <span style="margin-left: 6px;">{article.get('published', '날짜 미상')}</span>
            </div>
            <h3 style="margin: 0 0 10px 0; font-size: 17px; line-height: 1.4;">
                <a href="{article['link']}" target="_blank" style="color: #03c75a; text-decoration: none; font-weight: bold;">
                    {idx}. {article['title']}
                </a>
            </h3>
            <p style="margin: 0 0 10px 0; font-size: 13px; color: #475569;">
                <strong>감지 키워드:</strong> <span style="color: #e11d48; font-weight: bold;">{matched_str}</span>
            </p>
            <p style="margin: 0; font-size: 14px; color: #334155; line-height: 1.6; word-break: break-all;">
                {article.get('summary', '')}
            </p>
        </div>
        """

    html_content = f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', Arial, sans-serif; padding: 20px; background-color: #f8fafc; color: #1e293b;">
        <div style="max-width: 680px; margin: 0 auto; background: #ffffff; padding: 24px; border-radius: 12px; border: 1px solid #e2e8f0;">
            <h2 style="color: #0f172a; margin-top: 0; border-bottom: 2px solid #03c75a; padding-bottom: 12px;">📰 뉴스 키워드 맞춤 알림</h2>
            <p style="color: #64748b; font-size: 14px; line-height: 1.5;">
                설정하신 키워드(<strong>{', '.join(KEYWORDS)}</strong>)가 포함된 기사가 총 <strong>{len(new_articles)}건</strong> 수집되었습니다.
            </p>
            <div style="margin-top: 20px;">
                {articles_html}
            </div>
            <div style="margin-top: 30px; font-size: 12px; color: #94a3b8; text-align: center; border-top: 1px solid #f1f5f9; padding-top: 15px;">
                본 메일은 설정된 언론사 및 구글 뉴스의 RSS를 통해 자동 발송되었습니다.
            </div>
        </div>
    </body>
    </html>
    """

    try:
        with smtplib.SMTP_SSL("smtp.naver.com", 465) as server:
            server.login(naver_id, naver_password)
            
            # 각 수신자에게 개별 발송하여 개인정보 보호 및 안정성 확보
            for recipient in recipient_list:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = naver_id
                msg["To"] = recipient
                msg.attach(MIMEText(html_content, "html", "utf-8"))
                server.sendmail(naver_id, [recipient], msg.as_string())
                
        print(f"총 {len(recipient_list)}명에게 {len(new_articles)}건의 기사 알림 메일 개별 발송 완료.")
    except Exception as e:
        print(f"메일 발송 중 오류 발생: {e}")


def main():
    sent_articles = load_sent_articles()
    new_matched_articles = []
    
    # 이번 회차에서 추가된 제목들을 임시 기억하여 서로 다른 피드 간 중복도 즉시 방지
    current_run_titles = set()
    now_ts = time.time()

    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)

        if feed.bozo:
            print(f"RSS 피드를 파싱하는 중 문제가 발생했습니다: {feed_url}")
            continue

        for entry in feed.entries:
            link = entry.get("link")
            raw_title = entry.get("title", "")
            title = clean_text(raw_title)
            norm_title = normalize_title(title)

            # 링크나 제목이 이미 보낸 기록에 있거나 이번 실행에서 이미 추가되었다면 제외
            if not link or link in sent_articles or norm_title in sent_articles or norm_title in current_run_titles:
                continue

            # 날짜 검사: 설정한 기간보다 오래된 기사는 무시
            published_parsed = entry.get("published_parsed")
            if published_parsed:
                pub_ts = calendar.timegm(published_parsed)
                if now_ts - pub_ts > LIMIT_SECONDS:
                    continue

            raw_summary = entry.get("summary", "") or entry.get("description", "")
            summary = clean_text(raw_summary)
            content = f"{title} {summary}"

            # 설정된 전체 키워드 매칭 검사
            matched = [kw for kw in KEYWORDS if kw in content]
            if matched:
                source = FEED_NAMES.get(feed_url, entry.get("source", {}).get("title", "구글 뉴스"))
                
                # 구글 뉴스 제목 뒤에 붙는 ' - 언론사' 문구 깔끔하게 분리
                if feed_url == GOOGLE_NEWS_RSS and " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0]
                    source = parts[1]

                new_matched_articles.append({
                    "title": title,
                    "link": link,
                    "summary": summary[:200] + ("..." if len(summary) > 200 else ""),
                    "published": entry.get("published", ""),
                    "matched_keywords": matched,
                    "source": source
                })
                
                # 링크와 제목 모두 저장 목록에 등록
                sent_articles.add(link)
                sent_articles.add(norm_title)
                current_run_titles.add(norm_title)

    if new_matched_articles:
        print(f"총 {len(new_matched_articles)}개의 새 기사를 찾았습니다.")
        send_email(new_matched_articles)
        save_sent_articles(sent_articles)
    else:
        print("새로 등록된 키워드 관련 기사가 없습니다.")


if __name__ == "__main__":
    main()
