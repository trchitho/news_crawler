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

### `Source`

- `name`, `homepage`, `rss_url`
- `is_active`, `source_score`, `crawl_interval_min`, `last_crawled_at`

### `Article`

- `source` (FK → Source)
- `title`, `slug`, `source_url`
- `excerpt`, `content_html`, `blocks (JSON)`
- `main_image_url`, `main_image_caption`
- `published_at`, `fetched_at`
- `is_visible`, `search_blob` (dùng cho tìm kiếm bỏ dấu)

### `Category`

- `name`, `slug`

### `Comment`, `Reaction`

- Gắn với `Article`
- `Reaction.value`: like, love, wow, sad, angry

---

## 5. Quy trình Crawl

### Dev Mode (không worker, chạy sync)

```bash
# Tạo DB schema
python manage.py migrate

# Seed nguồn RSS
python manage.py seed_sources

# Crawl 30 bài mới (sync, không cần Redis/Celery)
python manage.py crawl_now --limit 30

# Chạy web server
python manage.py runserver
```

### Prod Mode (có worker + Redis)

```bash
# 1. Chạy Redis
docker run -d --name redis -p 6379:6379 redis

# 2. Apply DB schema
python manage.py migrate
python manage.py seed_sources

# 3. Chạy web server
python manage.py runserver

# 4. Chạy Celery worker
celery -A vnnews worker -l info

# 5. Chạy Celery beat (crawl mỗi 2h)
celery -A vnnews beat -l info
```

Reset / ép crawl gần đây:

```bash
python manage.py crawl_recent --hours 2
```

Crawl một URL cụ thể:

```bash
python manage.py crawl_once "https://.../bai-bao.html"
```

---

## 6. Luồng Hoạt Động

1. **Seed Sources** → DB lưu danh sách RSS.
2. **Celery Beat** (mỗi 2h) gọi `schedule_all_sources`.
3. `schedule_all_sources` → queue `task_fetch_feed(source_id)`.
4. `task_fetch_feed` → đọc RSS → queue `task_fetch_article(url)`.
5. `task_fetch_article` → tải HTML, sanitize, trích xuất title, excerpt, image, content → lưu `Article`.
6. **Web App** → HomeView (bài mới), CategoryView (lọc theo danh mục), ArticleDetailView (chi tiết + comment + reaction).

---

## 7. Giao diện

- **base.html**: header, nav categories, search box.
- **home.html**: lưới card (ảnh, tiêu đề, excerpt, meta).
- **category.html**: danh sách bài trong một danh mục.
- **article_detail.html**: nội dung bài sạch (HTML safe), ảnh, caption, reactions, comment box, related articles.

---

## 8. Hướng phát triển

- Tích hợp **full-text search** (Postgres `tsvector`).
- Thêm **tags tự động bằng NLP** (keyword extraction).
- Xây dựng **REST API** (Django REST Framework) cho mobile.
- Tích hợp **HTMX** hoặc **React frontend** để cải thiện UX.
