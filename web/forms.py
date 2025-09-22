# web/forms.py
import re
from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.core.validators import EmailValidator
from django.utils import timezone

from articles.models import Article
from sources.models import Category

UserModel = get_user_model()

PHONE_RE = re.compile(r"^(?:\+?84|0)(?:\d{9,10})$")


def normalize_identifier(x: str) -> str:
    return (x or "").strip().lower()


def is_phone(s: str) -> bool:
    return bool(PHONE_RE.fullmatch(s or ""))


# web/forms.py (đoạn RegisterForm đã sửa)

from django import forms
from django.core.validators import EmailValidator
from django.contrib.auth import get_user_model
import re

UserModel = get_user_model()

# ---- Fallback helpers (chỉ dùng nếu bạn chưa định nghĩa sẵn) ----
def _fallback_normalize_identifier(s: str) -> str:
    if s is None:
        return ""
    s = s.strip()
    # email -> lower; phone -> bỏ ký tự không phải số
    if "@" in s:
        return s.lower()
    return re.sub(r"\D+", "", s)

def _fallback_is_phone(s: str) -> bool:
    # chấp nhận 9-11 chữ số (tuỳ bạn siết lại theo VN)
    return bool(re.fullmatch(r"\d{9,11}", s))

# -----------------------------------------------------------------

class RegisterForm(forms.Form):
    full_name = forms.CharField(label="Họ và tên", max_length=120)
    email_or_mobile = forms.CharField(label="Email hoặc SĐT", max_length=120)
    password1 = forms.CharField(label="Mật khẩu", widget=forms.PasswordInput, min_length=6)
    password2 = forms.CharField(label="Xác nhận mật khẩu", widget=forms.PasswordInput, min_length=6)

    def clean_email_or_mobile(self):
        raw = self.cleaned_data.get("email_or_mobile", "")

        # Dùng helper của bạn nếu có; nếu không, dùng fallback
        norm = None
        try:
            norm = normalize_identifier(raw)  # type: ignore  # dùng hàm có sẵn của bạn
        except NameError:
            norm = _fallback_normalize_identifier(raw)

        if "@" in norm:
            # --- Email path ---
            email_val = norm.lower()
            EmailValidator(message="Email không hợp lệ")(email_val)

            # Email phải unique (case-insensitive)
            if UserModel.objects.filter(email__iexact=email_val).exists():
                raise forms.ValidationError("Email đã được sử dụng, vui lòng chọn email khác.")

            # Tránh username đụng đúng chuỗi email này (do bạn dùng email làm username khi đăng bằng email)
            if UserModel.objects.filter(username__iexact=email_val).exists():
                raise forms.ValidationError("Tên đăng nhập đã tồn tại, vui lòng dùng thông tin khác.")

            return email_val
        else:
            # --- Phone path ---
            try:
                ok_phone = is_phone(norm)  # type: ignore  # dùng hàm có sẵn của bạn
            except NameError:
                ok_phone = _fallback_is_phone(norm)

            if not ok_phone:
                raise forms.ValidationError("SĐT không hợp lệ.")

            # Username = SĐT phải unique
            if UserModel.objects.filter(username__iexact=norm).exists():
                raise forms.ValidationError("Tài khoản đã tồn tại.")

            return norm

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1") or ""
        p2 = cleaned.get("password2") or ""
        if p1 != p2:
            self.add_error("password2", "Mật khẩu xác nhận không khớp")
        return cleaned

    def save(self, request=None):
        data = self.cleaned_data
        username = data["email_or_mobile"]  # đã được normalize từ clean_email_or_mobile
        # Nếu là email -> gán email; nếu là SĐT -> để rỗng (hoặc bạn có thể lưu vào field khác)
        email = username if "@" in username else ""

        user = UserModel.objects.create_user(
            username=username,
            email=email,
            password=data["password1"],
        )
        # Lưu quick display name (tuỳ bạn có first/last_name hay full_name riêng)
        user.first_name = (data.get("full_name") or "")[:30]
        user.save(update_fields=["first_name"])
        return user


# web/forms.py
from django import forms
from django.contrib.auth import get_user_model, authenticate

UserModel = get_user_model()

class LoginForm(forms.Form):
    email_or_mobile = forms.CharField(label="Email hoặc SĐT", max_length=120)
    password = forms.CharField(label="Mật khẩu", widget=forms.PasswordInput)

    def clean(self):
        cleaned = super().clean()
        ident = (cleaned.get("email_or_mobile") or "").strip().lower()
        pwd = cleaned.get("password") or ""

        if not ident or not pwd:
            # Django sẽ hiển thị “Trường này là bắt buộc.” cho field trống,
            # nhưng ta giữ check này để tránh chạy tiếp authenticate khi thiếu dữ liệu
            return cleaned

        # Tìm user theo email (case-insensitive) trước
        qs = UserModel.objects.filter(email__iexact=ident)
        if not qs.exists():
            # Không có theo email -> thử username (dùng cho SĐT)
            qs = UserModel.objects.filter(username__iexact=ident)

        if not qs.exists():
            raise forms.ValidationError("Email/SĐT hoặc mật khẩu không đúng.")

        if qs.count() > 1:
            # Tránh login nhầm nếu vẫn còn dữ liệu trùng
            raise forms.ValidationError("Email này đang có nhiều tài khoản. Hãy liên hệ quản trị để hợp nhất.")

        user = qs.first()
        auth_user = authenticate(username=user.username, password=pwd)
        if not auth_user:
            raise forms.ValidationError("Email/SĐT hoặc mật khẩu không đúng.")

        cleaned["user"] = auth_user
        return cleaned


# --------- Guest comment form ----------
class GuestCommentForm(forms.Form):
    article_id = forms.IntegerField(widget=forms.HiddenInput)
    full_name = forms.CharField(label="Họ và tên", max_length=120)
    email = forms.EmailField(label="Email")
    content = forms.CharField(label="Nội dung", widget=forms.Textarea, min_length=3)


# --------- Article create/update form for journalists ----------
class ArticleCreateForm(forms.ModelForm):
    """
    Form đăng bài thủ công cho nhà báo.
    - Không yêu cầu source_url.
    - Có chọn categories (optional).
    - Luôn “bắt lỗi” nhẹ nhàng để không crash.
    """
    categories = forms.ModelMultipleChoiceField(
        queryset=Category.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Chuyên mục"
    )

    class Meta:
        model = Article
        fields = [
            "title",
            "excerpt",
            "content_html",
            "main_image_url",
            "main_image_caption",
            "categories",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Tiêu đề"}),
            "excerpt": forms.Textarea(attrs={"rows": 3, "placeholder": "Tóm tắt ngắn…"}),
            "content_html": forms.Textarea(attrs={"rows": 12, "placeholder": "Nội dung (có thể chèn <img> …)"}),
            "main_image_url": forms.URLInput(attrs={"placeholder": "URL ảnh đại diện (tuỳ chọn)"}),
            "main_image_caption": forms.TextInput(attrs={"placeholder": "Chú thích ảnh (tuỳ chọn)"}),
        }
        labels = {
            "title": "Tiêu đề",
            "excerpt": "Tóm tắt",
            "content_html": "Nội dung",
            "main_image_url": "Ảnh đại diện (URL)",
            "main_image_caption": "Chú thích ảnh",
        }

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()
        if not title:
            raise forms.ValidationError("Tiêu đề không được để trống")
        return title

    def clean_content_html(self):
        content = (self.cleaned_data.get("content_html") or "").strip()
        if len(content) < 3:
            raise forms.ValidationError("Nội dung quá ngắn")
        return content

    def save(self, user, commit=True):
        """
        Lưu bài viết:
        - Gán author = user, origin = USER
        - source_url = None
        - published_at = now nếu chưa có
        """
        try:
            obj: Article = super().save(commit=False)
            obj.author = user
            obj.origin = Article.Origin.USER
            obj.source_url = None
            if not obj.published_at:
                obj.published_at = timezone.now()
            obj.is_visible = True
            if commit:
                obj.save()
                self.save_m2m()
            return obj
        except Exception as e:
            # biến lỗi thành ValidationError để view hiển thị đẹp
            raise forms.ValidationError(f"Lỗi lưu bài viết: {e}")

# web/forms.py

from django import forms
from articles.models import Article
from sources.models import Category
from django.contrib.auth import get_user_model

UserModel = get_user_model()


class ArticleForm(forms.ModelForm):
    categories = forms.ModelMultipleChoiceField(
        queryset=Category.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "w-full", "size": 6}),
        label="Danh mục"
    )

    class Meta:
        model = Article
        fields = [
            "title", "excerpt", "content_html",
            "main_image_url", "main_image_caption",
            "categories", "is_visible",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "w-full"}),
            "excerpt": forms.Textarea(attrs={"rows": 3, "class": "w-full"}),
            "content_html": forms.Textarea(attrs={"rows": 12, "class": "w-full monospace"}),
            "main_image_url": forms.URLInput(attrs={"class": "w-full"}),
            "main_image_caption": forms.TextInput(attrs={"class": "w-full"}),
            "is_visible": forms.CheckboxInput(),
        }

    def save(self, commit=True, author=None):
        obj = super().save(commit=False)
        # Gắn cờ bài user đăng
        obj.origin = "user"

        # Nếu có author truyền vào → gắn vào bài
        if author and getattr(obj, "author_id", None) is None:
            obj.author = author

        if commit:
            obj.save()
            # ManyToMany (categories)
            self.save_m2m()
        return obj

        
    # web/forms.py  (thêm/điều chỉnh nếu bạn đang đặt form ở đây)
from django import forms
from articles.models import Article
from sources.models import Category

class SubmitArticleForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = ["title", "excerpt", "content_html", "main_image_url",
                  "main_image_caption", "categories", "is_visible"]
        widgets = {
            "excerpt": forms.Textarea(attrs={"rows": 3}),
            "content_html": forms.Textarea(attrs={"rows": 12}),
            "categories": forms.SelectMultiple(attrs={"size": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Gắn style/class 1 lần cho tất cả widget
        base_attrs = {
            "class": "w-full",
            "style": "width:100%;padding:12px 14px;border-radius:12px;"
                     "border:1px solid var(--ring);background:var(--card);"
                     "color:var(--text);outline:0",
        }
        for name, field in self.fields.items():
            current = field.widget.attrs
            current.update({k: v for k, v in base_attrs.items() if k not in current})
        # Label tiếng Việt
        self.fields["title"].label = "Tiêu đề"
        self.fields["excerpt"].label = "Tóm tắt"
        self.fields["content_html"].label = "Nội dung (có thể chèn ảnh)"
        self.fields["main_image_url"].label = "Ảnh đại diện (URL)"
        self.fields["main_image_caption"].label = "Chú thích ảnh đại diện"
        self.fields["categories"].label = "Chuyên mục"
        self.fields["is_visible"].label = "Hiển thị"

class ArticleSubmitFormSimple(forms.ModelForm):
    class Meta:
        model = Article
        fields = ["title", "excerpt", "main_image_url", "content_html", "categories", "is_visible"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Tiêu đề…"}),
            "excerpt": forms.Textarea(attrs={"rows": 3, "placeholder": "Tóm tắt ngắn…"}),
            "main_image_url": forms.URLInput(attrs={"placeholder": "https://… (link ảnh trực tiếp .jpg/.png)"}),
            "content_html": forms.Textarea(attrs={"rows": 14, "placeholder": "Nội dung (có thể chèn <img src='...'>)…"}),
        }

    categories = forms.ModelMultipleChoiceField(
        queryset=Category.objects.all().order_by("name"),
        required=False,
        widget=forms.SelectMultiple(attrs={"size": 5})
    )


# web/forms.py
from django import forms
from django.utils.html import strip_tags
import re
from articles.models import Article

IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)

class ArticleSubmitForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = ["title", "excerpt", "main_image_url", "content_html", "categories", "is_visible"]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "w-full", "placeholder": "Tiêu đề bài viết",
                "style": "width:100%;padding:12px;border-radius:12px;border:1px solid var(--ring);"
                         "background:var(--card);color:var(--text);outline:0"
            }),
            "excerpt": forms.Textarea(attrs={
                "class": "w-full", "rows": 3, "placeholder": "Tóm tắt ngắn",
                "style": "width:100%;padding:12px;border-radius:12px;border:1px solid var(--ring);"
                         "background:var(--card);color:var(--text);outline:0"
            }),
            "main_image_url": forms.URLInput(attrs={
                "class": "w-full", "id": "imgUrl", "placeholder": "URL ảnh tiêu đề (tùy chọn)",
                "style": "width:100%;padding:10px;border-radius:12px;border:1px solid var(--ring);"
                         "background:var(--card);color:var(--text);outline:0"
            }),
            "content_html": forms.Textarea(attrs={
                "class": "w-full mono", "rows": 16,
                "placeholder": 'Nội dung HTML sạch. Có thể chèn ảnh: <img src="https://...jpg">',
                "style": "width:100%;min-height:360px;padding:12px;border-radius:12px;"
                         "border:1px solid var(--ring);background:var(--card);color:var(--text);"
                         "outline:0;font-family:ui-monospace,monospace"
            }),
            "categories": forms.SelectMultiple(attrs={
                "class": "w-full",
                "style": "width:100%;padding:8px;border-radius:12px;border:1px solid var(--ring);"
                         "background:var(--card);color:var(--text);outline:0"
            }),
        }

    def clean_main_image_url(self):
        url = (self.cleaned_data.get("main_image_url") or "").strip()
        return url or ""

    def clean_content_html(self):
        html = self.cleaned_data.get("content_html") or ""
        # (Optional) very light guard so empty posts aren’t allowed
        if not strip_tags(html).strip():
            raise forms.ValidationError("Nội dung không được để trống.")
        return html

    def extract_first_image(self):
        """Return first <img src="..."> in content_html if any."""
        html = self.cleaned_data.get("content_html") or ""
        m = IMG_SRC_RE.search(html)
        return (m.group(1).strip() if m else "") or ""

