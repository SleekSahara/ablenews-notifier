import os
import json
import smtplib
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import feedparser

# ---------------------------------------------------------
# 1. 설정 부분
# ---------------------------------------------------------
# 감지할 키워드 목록 (직접 추가하신 확장된 키워드 유지)
KEYWORDS = ["수어", "농인", "농아인", "수화", "농아인협회", "수어통역센터", "장애인"]

# 중복 발송 방지를 위한 기록 파일
LOG_FILE = "sent_articles.json"

# 에이블뉴스 전체기사 RSS 피드
ABLE_NEWS_RSS = "https://www.ablenews.co.kr/rss/allArticle.xml"

# 구글 뉴스(대부분의 인터넷 뉴스) 키워드 검색 RSS 피드 자동 생성
search_query = " OR ".join(KEYWORDS)
encoded_query = urllib.parse.quote(search_query)
GOOGLE_NEWS_RSS = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"

# 검사할 피드 목록
RSS_FEEDS = [ABLE_NEWS_RSS, GOOGLE_NEWS_RSS]


# ---------------------------------------------------------
# 2. 기능 구현 부분
# ---------------------------------------------------------
def load_sent_articles():
    """이미 발송한 기사 링크 목록 불러오기"""
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"로그 파일 로드 실패: {e}")
            return set()
    return set()


def save_sent_articles(sent_list):
    """발송한 기사 링크 목록 저장 (최대 1000개 유지)"""
    trimmed_list = list(sent_list)[-1000:]
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed_list, f, ensure_ascii=False, indent=2)


def send_email(new_articles):
    """네이버 SMTP를 사용하여 여러 명에게 메일 발송"""
    naver_id = os.environ.get("NAVER_ID")
    naver_password = os.environ.get("NAVER_PASSWORD")
    recipient_email_str = os.environ.get("RECIPIENT_EMAIL")

    if not all([naver_id, naver_password, recipient_email_str]):
        print("이메일 환경변수가 설정되지 않아 메일을 전송할 수 없습니다.")
        return

    # 쉼표(,)로 구분된 이메일 주소들을 리스트로 분리하여 다중 수신 지원
    recipient_list = [email.strip() for email in recipient_email_str.split(",") if email.strip()]

    if not recipient_list:
        print("수신자 이메일 목록이 비어 있습니다.")
        return

    # 키워드가 많아졌으므로 이메일 제목을 포괄적으로 변경
    subject = f"[통합 뉴스 알림] 설정 키워드 관련 새 기사 {len(new_articles)}건"
    
    articles_html = ""
    for article in new_articles:
        matched_str = ", ".join(article["matched_keywords"])
        source_name = article.get('source', '인터넷 뉴스')
        
        articles_html += f"""
        <div style="margin-bottom: 20px; padding: 15px; border: 1px solid #e0e0e0; border-radius: 8px;">
            <h3 style="margin: 0 0 10px 0;">
                <a href="{article['link']}" target="_blank" style="color: #03c75a; text-decoration: none;">
                    {article['title']}
                </a>
            </h3>
            <p style="margin: 0 0 8px 0; font-size: 13px; color: #666;">
                <strong>출처:</strong> {source_name} | 
                <strong>감지 키워드:</strong> <span style="color: #d93025;">{matched_str}</span><br>
                <strong>발행일:</strong> {article.get('published', '날짜 미상')}
            </p>
            <p style="margin: 0; font-size: 14px; color: #333; line-height: 1.5;">
                {article.get('summary', '')}
            </p>
        </div>
        """

    # 직접 수정하신 깔끔한 제목 양식("📰 뉴스 키워드 알림") 반영
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color: #202124;">📰 뉴스 키워드 알림</h2>
        <p style="color: #5f6368;">설정하신 키워드(<strong>{', '.join(KEYWORDS)}</strong>)가 포함된 새 기사가 등록되었습니다.</p>
        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
        {articles_html}
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = naver_id
    # 수신자가 여러 명일 경우를 위해 쉼표로 다시 조합하여 To에 할당
    msg["To"] = ", ".join(recipient_list)
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        # 네이버 SMTP 서버 연결 (포트 465)
        with smtplib.SMTP_SSL("smtp.naver.com", 465) as server:
            server.login(naver_id, naver_password)
            # 목록에 등록된 모든 사람에게 각각 발송 처리
            server.sendmail(naver_id, recipient_list, msg.as_string())
        print(f"총 {len(recipient_list)}명에게 {len(new_articles)}건의 기사 알림 메일 발송 완료.")
    except Exception as e:
        print(f"메일 발송 중 오류 발생: {e}")


def main():
    sent_articles = load_sent_articles()
    new_matched_articles = []

    # 에이블뉴스와 구글뉴스를 번갈아가며 모두 검사합니다.
    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)

        if feed.bozo:
            print(f"RSS 피드를 파싱하는 중 문제가 발생했습니다: {feed_url}")
            continue

        for entry in feed.entries:
            link = entry.get("link")
            if not link or link in sent_articles:
                continue

            title = entry.get("title", "")
            summary = entry.get("summary", "") or entry.get("description", "")
            content = f"{title} {summary}"

            # 설정된 전체 키워드 매칭 검사
            matched = [kw for kw in KEYWORDS if kw in content]
            if matched:
                source = "에이블뉴스" if feed_url == ABLE_NEWS_RSS else entry.get("source", {}).get("title", "구글 뉴스")
                
                new_matched_articles.append({
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "published": entry.get("published", ""),
                    "matched_keywords": matched,
                    "source": source
                })
                sent_articles.add(link)

    if new_matched_articles:
        print(f"총 {len(new_matched_articles)}개의 새 기사를 찾았습니다.")
        send_email(new_matched_articles)
        save_sent_articles(sent_articles)
    else:
        print("새로 등록된 키워드 관련 기사가 없습니다.")


if __name__ == "__main__":
    main()
