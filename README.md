# 📖 VN News – Django All-in-One News Aggregator

## 1. Giới thiệu

VN News là một dự án **thu thập và hiển thị tin tức từ nhiều nguồn báo chí Việt Nam**, phát triển bằng **Django All-in-One** (Django + Celery + Redis + PostgreSQL/SQLite).

Hệ thống có thể:

- Chạy nhanh ở **dev mode** (không cần worker, crawl đồng bộ).
- Chạy ổn định ở **prod mode** (Celery worker + Redis, crawl định kỳ).

---

## 2. Kiến trúc & Công nghệ

- **Django**: ORM, template engine, admin, management commands.
- **Database**: PostgreSQL (production) / SQLite (dev).
- **Celery + Redis**: xử lý tác vụ nền (crawl RSS, fetch HTML, làm sạch dữ liệu).
- **Requests + Feedparser + Trafilatura**: tải RSS, parse HTML, trích xuất nội dung.
- **BeautifulSoup + Bleach**: sanitize & định dạng HTML.
- **Whitenoise + Gunicorn**: phục vụ static file & production server.
- **Django Template Engine**: giao diện thuần HTML/CSS (có thể kết hợp HTMX).

---

## 3. Cấu trúc thư mục

```text
.vscode/settings.json         # VSCode config
celerybeat-schedule.*         # Celery Beat state files
db.sqlite3                    # SQLite database (dev)
manage.py                     # Django management script
requirements.txt              # Python dependencies

articles/                     # App quản lý bài viết
  ├── models.py               # Article model
  ├── views.py, admin.py      # Views & Admin
  └── migrations/             # Schema migrations

crawler/                      # App crawler
  ├── tasks.py                # Celery tasks (fetch_feed, fetch_article)
  ├── utils.py                # Hàm fetch_and_extract
  ├── management/commands/    # CLI: crawl_now, crawl_once, seed_sources…
  └── migrations/

sources/                      # App quản lý nguồn
  ├── models.py               # Source, Category
  └── admin.py, migrations/

web/                          # App giao diện
  ├── views.py                # Home, Category, ArticleDetail
  ├── models.py               # Comment, Reaction
  └── templates/              # HTML templates
       ├── base.html
       ├── home.html
       ├── category.html
       └── article_detail.html

vnnews/                       # Project config
  ├── settings.py             # Django settings
  ├── urls.py                 # URL routes
  ├── celery.py               # Celery app & schedule
  ├── wsgi.py / asgi.py       # Entrypoints
```

---

## 4. Mô hình dữ liệu

### Source

- `name`, `homepage`, `rss_url`
- `is_active`, `source_score`, `crawl_interval_min`, `last_crawled_at`

### Article

- `source` (FK → Source)
- `title`, `slug`, `source_url`
- `excerpt`, `content_html`, `blocks (JSON)`
- `main_image_url`, `main_image_caption`
- `published_at`, `fetched_at`
- `is_visible`, `search_blob` (tìm kiếm bỏ dấu)

### Category

- `name`, `slug`

### Comment, Reaction

- Gắn với `Article`
- `Reaction.value`: like, love, wow, sad, angry

---

5. Cài đặt & Chạy (DEV – không cần Redis/Celery)

Mục tiêu: chạy bằng SQLite + crawl đồng bộ (sync), không cần Redis/Celery.

5.1. Yêu cầu hệ thống

Python 3.10+, Git, pip

Khuyến nghị dùng venv để cô lập môi trường

KHÔNG cần PostgreSQL/Redis cho DEV

5.2. Clone repo & tạo môi trường ảo

# Clone

git clone https://github.com/trchitho/news_crawler.git
cd news_crawler

# Tạo venv

# Linux/macOS:

python3 -m venv .venv && source .venv/bin/activate

# Windows PowerShell:

python -m venv .venv
.\.

Bạn đã nói:
viết lại hoàn chỉnh chứ

ChatGPT đã nói:
Đã suy nghĩ trong 1 giây
Đã suy nghĩ trong 9s

Chuẩn—mình viết lại mục 5 (DEV) thật đầy đủ, “copy-paste là chạy”, kèm luôn lệnh Git để cập nhật khi có thay đổi (migrations, requirements). Bạn chỉ cần thay thế mục 5 trong README bằng nội dung dưới đây.

5. Cài đặt & Chạy (DEV – không cần Redis/Celery)

Mục tiêu: chạy bằng SQLite + crawl đồng bộ (sync), không cần Redis/Celery.
Tất cả lệnh đều theo thứ tự; làm xong bước trước mới tới bước sau.

5.1. Yêu cầu hệ thống

Python 3.10+, Git, pip

Khuyến nghị dùng venv để cô lập môi trường

KHÔNG cần PostgreSQL/Redis cho DEV

5.2. Clone repo & tạo môi trường ảo

# Clone

git clone https://github.com/trchitho/news_crawler.git
cd news_crawler

# Tạo venv

# Linux/macOS:

python3 -m venv .venv && source .venv/bin/activate

# Windows PowerShell:

python -m venv .venv
.\.venv\Scripts\Activate.ps1

⚠️ Nếu PowerShell chặn script: mở PowerShell Run as Administrator và chạy
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

5.3. Cài thư viện Python

# Nâng pip + công cụ build (nhất là trên Windows)

python -m pip install --upgrade pip setuptools wheel

# Cài đúng dependencies của dự án

pip install -r requirements.txt

Nếu sau này lệnh crawl báo thiếu gói (ví dụ feedparser), cài bổ sung:
pip install feedparser requests bleach beautifulsoup4 trafilatura readability-lxml django-taggit

5.4. Tạo file cấu hình môi trường .env

Tạo file .env tại thư mục gốc (có thể copy từ .env.example nếu có):

# Django

DEBUG=True
SECRET_KEY=change-me
ALLOWED_HOSTS=127.0.0.1,localhost
TIME_ZONE=Asia/Ho_Chi_Minh

# Database (DEV dùng SQLite)

DATABASE_URL=sqlite:///db.sqlite3

# Redis (KHÔNG cần cho DEV sync)

REDIS_URL=redis://localhost:6379/0

Đảm bảo vnnews/settings.py đọc .env (vd: dùng django-environ).
Nếu chưa, thêm khởi tạo environ vào settings.py (load .env), rồi chạy lại.

5.5. Khởi tạo CSDL & seed nguồn

# Tạo schema DB

python manage.py migrate

# (Tuỳ chọn) tạo tài khoản admin để vào /admin

python manage.py createsuperuser

# Nạp danh sách nguồn RSS (idempotent – chạy nhiều lần cũng không sao)

python manage.py seed_sources

Nếu Django báo: “models trong app X đã thay đổi nhưng chưa có migration”
thì tạo migration trước:
python manage.py makemigrations web (UPDATE CHỖ NÀY!)
(sửa nhiều app thì gom luôn: python manage.py makemigrations web articles sources)
rồi chạy lại python manage.py migrate.

5.6. Crawl dữ liệu mẫu (đồng bộ – không cần Celery)

# Lấy ~30 bài mới từ các nguồn RSS (chạy SYNC)

python manage.py crawl_now --limit 30

Lệnh này KHÔNG dùng Celery, giúp có dữ liệu ngay để test UI.

5.7. Chạy web server (DEV)
python manage.py runserver

App: http://127.0.0.1:8000

Admin: http://127.0.0.1:8000/admin

5.8. Lệnh hữu ích trong DEV

# Kiểm tra cấu hình Django

python manage.py check

# Rebuild trường search_blob (tìm kiếm bỏ dấu)

python manage.py reindex_search

# Crawl một URL cụ thể (debug)

python manage.py crawl_once "https://.../bai-bao.html"

Chỉ khi dùng Celery (không áp dụng cho DEV sync):
python manage.py crawl_recent --hours 2

---

## 6. Luồng Hoạt Động

1. **Seed Sources** → DB lưu danh sách RSS.
2. **(DEV sync)**: `crawl_now` gọi trực tiếp hàm fetch & lưu Article, **không cần Celery**.
3. **(Prod)**: Celery Beat mỗi 2h gọi `schedule_all_sources` → queue `task_fetch_feed(source_id)` → queue `task_fetch_article(url)`.
4. `task_fetch_article` → tải HTML, sanitize, trích xuất title, excerpt, image, content → lưu `Article`.
5. **Web App** → HomeView (bài mới), CategoryView (lọc danh mục), ArticleDetailView (chi tiết + comment + reaction).

---

## 7. Giao diện

- **base.html**: header, nav categories, search box.
- **home.html**: lưới card (ảnh, tiêu đề, excerpt, meta).
- **category.html**: danh sách bài trong một danh mục.
- **article_detail.html**: nội dung bài sạch (HTML safe), ảnh, caption, reactions, comment box, related articles.
