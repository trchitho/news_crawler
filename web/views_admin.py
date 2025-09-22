# web/views_admin.py
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import UpdateView, View
from django.urls import reverse
from django.http import HttpResponseBadRequest
from django.utils.decorators import method_decorator
from django.core.management import call_command

from articles.models import Article
from web.forms import ArticleForm
from crawler.tasks import schedule_all_sources  # nếu dùng Celery

def is_admin(u):
    return u.is_authenticated and (u.is_superuser or u.is_staff)

admin_required = [login_required, user_passes_test(is_admin)]

@method_decorator(admin_required, name="dispatch")
class AdminArticleListView(View):
    template_name = "admin/article_list.html"

    def get(self, request):
        q = (request.GET.get("q") or "").strip()
        origin = (request.GET.get("origin") or "").strip()  # "user" | "crawler" | ""
        qs = Article.objects.all().select_related("author").order_by("-published_at", "-id")

        if q:
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(excerpt__icontains=q) |
                Q(search_blob__icontains=q.lower())
            )

        # Lọc nguồn CHUẨN: model đang dùng "crawler" và "user"
        if origin in {"user", "crawler"}:
            qs = qs.filter(origin=origin)

        page_obj = Paginator(qs, 25).get_page(request.GET.get("page"))

        ctx = {
            "page_obj": page_obj,
            "q": q,
            "origin": origin,
        }
        return render(request, self.template_name, ctx)

@method_decorator(admin_required, name="dispatch")
class AdminArticleEditView(UpdateView):
    model = Article
    form_class = ArticleForm
    template_name = "admin/article_edit.html"

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        # Chỉ cho sửa bài do user đăng
        if obj.origin != "user":
            messages.error(request, "Bài do crawler thu thập — chỉ được xoá, không được sửa.")
            return redirect("admin_articles")
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        messages.success(self.request, "Đã cập nhật bài viết.")
        return reverse("admin_articles")

@admin_required[0]
@admin_required[1]
def admin_delete_article(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")
    a = get_object_or_404(Article, pk=pk)
    a.delete()
    messages.success(request, "Đã xoá bài.")
    return redirect("admin_articles")

# web/views.py (hoặc nơi bạn đang đặt admin views)
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.management import call_command
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect

# Celery task
try:
    from crawler.tasks import schedule_all_sources
except Exception:
    schedule_all_sources = None

@staff_member_required  # hoặc dùng decorator admin_required của bạn
def admin_crawl_now(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    # Ưu tiên Celery nếu có
    if schedule_all_sources:
        try:
            schedule_all_sources.delay()
            messages.success(request, "Đã gửi yêu cầu cào tin (Celery).")
            return redirect("admin_articles")
        except Exception:
            pass  # fallback xuống chạy đồng bộ

    # Fallback: chạy management command đồng bộ
    try:
        call_command("crawl_now", limit=50)
        messages.success(request, "Đã cào xong (chạy đồng bộ).")
    except Exception as e:
        messages.error(request, f"Lỗi khi cào tin: {e}")

    return redirect("admin_articles")

