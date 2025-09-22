# web/views.py
from django.db.models import Q, Count
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

# Stdlib / third-party
import json

# Local apps
from articles.models import Article
from sources.models import Category
from web.models import Comment, Reaction

# web/views.py (thêm imports)
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import transaction
from django.shortcuts import redirect, render, get_object_or_404

from .forms import ArticleForm, SubmitArticleForm
from articles.models import Article





def post_comment(request, article_id: int):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    a = get_object_or_404(Article, pk=article_id, is_visible=True)
    content = (request.POST.get("content") or "").strip()
    author = (request.POST.get("author") or "Ẩn danh").strip()[:120]
    if not content:
        return HttpResponseBadRequest("Empty content")

    Comment.objects.create(article=a, author=author, content=content)
    return redirect("article_detail", slug=a.slug)

def article_detail(request, slug):
    # Bài hiện tại
    a = get_object_or_404(
        Article.objects.select_related().prefetch_related('categories'),
        slug=slug, is_visible=True
    )

    # === RELATED: chỉ cùng category, exclude chính nó, distinct, ưu tiên trùng nhiều category ===
    cat_ids = list(a.categories.values_list('id', flat=True))
    if cat_ids:
        related_qs = (
            Article.objects.filter(is_visible=True)
            .exclude(pk=a.pk)
            .filter(categories__id__in=cat_ids)
            .annotate(
                same_cats=Count('categories', filter=Q(categories__id__in=cat_ids), distinct=True)
            )
            .order_by('-same_cats', '-published_at')
            .distinct()[:8]          # lấy tối đa 8 bài, KHÔNG filler khác chủ đề
        )
    else:
        # Không có category -> không gợi ý (tránh lạc chủ đề)
        related_qs = Article.objects.none()

    related = list(related_qs)

    # (Giữ nguyên phần reaction counts / comments của bạn)
    try:
        from django.db.models import Count as _Count  # tránh trùng tên
        from web.models import Reaction
        base = {k.label: 0 for k in Reaction.Kind}
        agg = Reaction.objects.filter(article=a).values('value').annotate(n=_Count('id'))
        counts = base | {Reaction.Kind(r['value']).label: r['n'] for r in agg}
    except Exception:
        counts = {"like": 0, "love": 0, "wow": 0, "sad": 0, "angry": 0}

    try:
        from web.models import Comment
        comments = Comment.objects.filter(article=a, is_approved=True).order_by('-created_at')
    except Exception:
        comments = []

    return render(request, 'article_detail.html', {
        'a': a,
        'related': related,
        'counts': counts,
        'comments': comments,
        'object': a,
    })



from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.db.models import Count

from articles.models import Article
from .models import Reaction

@require_POST
@csrf_protect
def react_article(request):
    slug = request.POST.get('slug')
    raw  = request.POST.get('value')  # có thể là "like" hoặc "1"

    article = get_object_or_404(Article, slug=slug, is_visible=True)
    # map chuỗi -> số
    mapping = {
        'like':  Reaction.Kind.LIKE,
        'love':  Reaction.Kind.LOVE,
        'wow':   Reaction.Kind.WOW,
        'sad':   Reaction.Kind.SAD,
        'angry': Reaction.Kind.ANGRY,
    }
    try:
        kind = int(raw)
    except (TypeError, ValueError):
        kind = mapping.get(str(raw).lower())

    valid_values = {k.value for k in Reaction.Kind}
    if kind not in valid_values:
        return JsonResponse({'ok': False, 'error': 'invalid_reaction'}, status=400)

    # đảm bảo có session
    if not request.session.session_key:
        request.session.save()
    sk = request.session.session_key

    # toggle
    obj, created = Reaction.objects.get_or_create(
        article=article, session_key=sk, value=kind
    )
    if not created:
        obj.delete()
        toggled = False
    else:
        toggled = True

    # tổng hợp counts
    base = {k.label: 0 for k in Reaction.Kind}
    agg = Reaction.objects.filter(article=article).values('value').annotate(n=Count('id'))
    for r in agg:
        base[Reaction.Kind(r['value']).label] = r['n']

    return JsonResponse({'ok': True, 'toggled': toggled, 'counts': base})




def _qsearch(qs, q):
    if not q:
        return qs
    q = q.strip()
    # ưu tiên search_blob nếu có
    if "search_blob" in [f.name for f in Article._meta.get_fields()]:
        toks = [t for t in q.split() if t]
        for t in toks:
            qs = qs.filter(search_blob__icontains=t.lower())
        return qs
    return qs.filter(Q(title__icontains=q) | Q(excerpt__icontains=q))

import unicodedata, re

def normalize_query(q: str) -> str:
    """Bỏ dấu + lowercase + strip"""
    if not q:
        return ""
    try:
        q = unicodedata.normalize("NFKD", q)
        q = q.encode("ascii", "ignore").decode("utf-8")
    except Exception:
        pass
    return re.sub(r"\s+", " ", q).lower().strip()


# web/views.py (chỉ paste phần helper + 2 view list)

from django.db.models import Q
import unicodedata, logging

def _normalize_no_accent(s: str) -> str:
    try:
        return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("utf-8").lower().strip()
    except Exception:
        return (s or "").lower().strip()

def search_articles(qs, q: str):
    """
    Tìm kiếm:
    - Có search_blob: tách token đã bỏ dấu -> filter search_blob__icontains(token)
    - Không có search_blob: dùng query gốc (có dấu) -> filter title/excerpt
    Luôn bắt ngoại lệ để không vỡ trang.
    """
    if not q:
        return qs
    try:
        has_search_blob = any(f.name == "search_blob" for f in Article._meta.get_fields())
    except Exception:
        has_search_blob = False

    try:
        if has_search_blob:
            nq = _normalize_no_accent(q)
            toks = [t for t in nq.split() if t]
            for t in toks:
                qs = qs.filter(search_blob__icontains=t)
            return qs
        else:
            # Fallback: giữ nguyên dấu để SQLite/Postgres match đúng
            return qs.filter(Q(title__icontains=q) | Q(excerpt__icontains=q))
    except Exception as e:
        logging.exception("Search error: %s", e)
        return qs  # không lọc nếu có lỗi


# =========================
# Helpers
# =========================

from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST
from django.shortcuts import redirect
from django.contrib import messages

@staff_member_required
@require_POST
def admin_crawl_now(request):
    """
    Chạy crawl ngay: nếu có Celery thì .delay(), không có thì chạy đồng bộ.
    """
    try:
        from crawler.tasks import crawl_all_sources
    except Exception:
        crawl_all_sources = None

    try:
        if crawl_all_sources:
            # Có Celery -> đẩy task nền
            try:
                crawl_all_sources.delay()
                messages.success(request, "Đã gửi yêu cầu crawl (chạy nền).")
            except Exception:
                # fallback đồng bộ nếu Celery chưa bật
                crawl_all_sources()
                messages.success(request, "Đã crawl đồng bộ.")
        else:
            # Không có task -> fallback util
            from crawler.utils import crawl_all_sources_sync  # nếu bạn có util sync
            crawl_all_sources_sync()
            messages.success(request, "Đã crawl đồng bộ.")
    except Exception as e:
        messages.error(request, f"Lỗi crawl: {e}")

    return redirect("admin_articles")


def _common_filters(qs, request):
    """Áp dụng q / origin / sort giống nhau cho Home & Category."""
    q = (request.GET.get("q") or "").strip()
    origin = (request.GET.get("origin") or "").strip()
    sort = (request.GET.get("sort") or "new").strip()

    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(excerpt__icontains=q) |
            Q(search_blob__icontains=q.lower())
        )
    if origin in {"user", "crawler"}:
        qs = qs.filter(origin=origin)

    if sort == "old":
        qs = qs.order_by("published_at", "id")
    else:
        qs = qs.order_by("-published_at", "-id")
    return qs

def _common_ctx(ctx):
    """Đưa list categories vào base để render dải chip."""
    ctx["categories"] = Category.objects.order_by("name")
    return ctx

# =========================
# Home
# =========================

class HomeView(ListView):
    template_name = "home.html"
    context_object_name = "articles"
    paginate_by = 18  # 3 cột * 6 hàng

    def get_queryset(self):
        qs = Article.objects.filter(is_visible=True).prefetch_related("categories").select_related("author")
        qs = _common_filters(qs, self.request)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        return _common_ctx(ctx)

# =========================
# Category
# =========================

class CategoryView(ListView):
    template_name = "category.html"
    paginate_by = 18

    def get_queryset(self):
        self.category = get_object_or_404(Category, slug=self.kwargs["slug"])
        qs = (Article.objects.filter(is_visible=True, categories=self.category)
              .prefetch_related("categories").select_related("author"))
        qs = _common_filters(qs, self.request)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["category"] = self.category
        return _common_ctx(ctx)

# =========================
# Detail
# =========================

class ArticleDetailView(DetailView):
    model = Article
    template_name = "article_detail.html"
    slug_field = "slug"
    slug_url_kwarg = "slug"
    context_object_name = "a"

    def get_queryset(self):
        return Article.objects.filter(is_visible=True).prefetch_related("categories")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        a = self.object

        # Reactions
        base = {k.label: 0 for k in Reaction.Kind}
        agg = Reaction.objects.filter(article=a).values("value").annotate(n=Count("id"))
        for r in agg:
            base[Reaction.Kind(r["value"]).label] = r["n"]
        ctx["counts"] = base

        # Comments
        try:
            ctx["comments"] = Comment.objects.filter(article=a).order_by("-created_at")
        except Exception:
            ctx["comments"] = []

        # Related: chỉ cùng category, ưu tiên trùng nhiều cat
        cat_ids = list(a.categories.values_list("id", flat=True))
        if cat_ids:
            related_qs = (Article.objects.filter(is_visible=True, categories__id__in=cat_ids)
                          .exclude(pk=a.pk)
                          .annotate(same_cats=Count("categories",
                                                    filter=Q(categories__id__in=cat_ids),
                                                    distinct=True))
                          .order_by("-same_cats", "-published_at")
                          .distinct()[:8])
            ctx["related"] = list(related_qs)
        else:
            ctx["related"] = []

        ctx["object"] = a
        return _common_ctx(ctx)

# =========================
# Submit / My Articles / Edit / Delete
# =========================

from .forms import SubmitArticleForm

@login_required
def submit_article(request):
    if request.method == "POST":
        form = SubmitArticleForm(request.POST)
        if form.is_valid():
            a = form.save(commit=False)
            a.author = request.user
            a.origin = "user"
            a.is_visible = True
            if not a.published_at:
                a.published_at = timezone.now()
            a.save()
            form.save_m2m()
            messages.success(request, "Đã đăng bài.")
            return redirect("my_articles")
    else:
        form = SubmitArticleForm()
    return render(request, "articles/submit.html", {"form": form})

@login_required
def my_articles(request):
    qs = (Article.objects.filter(author=request.user)
          .order_by("-created_at", "-id")
          .prefetch_related("categories"))
    return render(request, "articles/my_articles.html", {"articles": qs})

@login_required
def submit_article_edit(request, pk: int):
    a = get_object_or_404(Article, pk=pk, author=request.user)
    if request.method == "POST":
        form = SubmitArticleForm(request.POST, instance=a)
        if form.is_valid():
            a = form.save(commit=False)
            if not a.published_at:
                a.published_at = timezone.now()
            a.save()
            form.save_m2m()
            messages.success(request, "Đã cập nhật bài viết.")
            return redirect("my_articles")
    else:
        form = SubmitArticleForm(instance=a)
    return render(request, "articles/submit.html", {"form": form, "edit_mode": True})

@login_required
def submit_article_delete(request, pk: int):
    a = get_object_or_404(Article, pk=pk, author=request.user)
    if request.method == "POST":
        a.delete()
        messages.success(request, "Đã xóa bài.")
        return redirect("my_articles")
    return render(request, "confirm_delete.html", {"object": a})






