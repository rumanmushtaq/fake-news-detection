import random
import time
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import EmailMultiAlternatives
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import AdminData, Contact, NewsHistory, User


# ========================================
# access helpers
# ========================================

def user_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.session.get('user_id'):
            messages.error(request, "Please log in first.")
            return redirect('user_login')
        return view(request, *args, **kwargs)
    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.session.get('admin_username'):
            messages.error(request, "Please log in as admin first.")
            return redirect('admin_login')
        return view(request, *args, **kwargs)
    return wrapper


def verify_password(obj, raw_password):
    """Check a hashed password; upgrade legacy plaintext passwords on first successful login."""
    if check_password(raw_password, obj.password):
        return True
    if obj.password == raw_password:
        obj.password = make_password(raw_password)
        obj.save(update_fields=['password'])
        return True
    return False


def login_session(request, user):
    request.session.cycle_key()
    request.session['user_id'] = user.id
    request.session['username'] = user.username


# ========================================
# public pages
# ========================================

def prediction_counts(queryset):
    counts = queryset.aggregate(
        total=Count('id'),
        real=Count('id', filter=Q(result="Real")),
        fake=Count('id', filter=Q(result="Fake")),
    )
    total = counts['total'] or 0
    counts['fake_pct'] = round(counts['fake'] * 100 / total) if total else 0
    counts['real_pct'] = 100 - counts['fake_pct'] if total else 0
    return counts


def index(request):
    return render(request, 'index.html', {"stats": prediction_counts(NewsHistory.objects.all()),
                                          "model": MODEL_INFO})

def about(request):
    return render(request, 'about.html', {"model": MODEL_INFO})

def contact(request):
    if request.method == 'POST':
        names = (request.POST.get('name') or '').strip()
        email = (request.POST.get('email') or '').strip()
        phone = (request.POST.get('phone') or '').strip()
        desc = (request.POST.get('desc') or '').strip()

        if not (names and email and desc):
            messages.error(request, "Name, email and query are required.")
            return redirect(request.path)

        Contact.objects.create(names=names, email=email, phone=phone[:10], desc=desc)
        messages.success(request, "Thanks! Your message has been sent.")
        return redirect(request.path)

    layout = "layouts/app.html" if request.path.startswith('/user_contact') else "layouts/public.html"
    return render(request, 'contact.html', {"layout": layout})


# ========================================
# user login / registration
# ========================================

def user_login(request):
    if request.method == "POST":
        identifier = (request.POST.get("email") or "").strip()  # can be email or username
        password = request.POST.get("password") or ""

        user = User.objects.filter(Q(email=identifier) | Q(username=identifier)).first()

        if not user or not verify_password(user, password):
            messages.error(request, "Invalid credentials.")
            return redirect('user_login')

        if user.is_banned:
            messages.error(request, "Your account is banned. You cannot log in.")
            return redirect('user_login')

        login_session(request, user)
        messages.success(request, "Login successful.")
        return redirect('user_home')

    return render(request, "login.html")


def user_registration(request):
    if request.method == "POST":
        username = (request.POST.get('username') or '').strip()
        name = (request.POST.get('name') or '').strip()
        email = (request.POST.get('email') or '').strip()
        password = request.POST.get('password') or ''
        confirm_password = request.POST.get('confirm_password') or ''

        if not (username and name and email and password):
            messages.error(request, "All fields are required.")
            return redirect('user_registration')

        # Check if user with email is already banned
        if User.objects.filter(email=email, is_banned=True).exists():
            messages.error(request, "You are banned from registering.")
            return redirect('user_registration')

        if User.objects.filter(username=username).exists():
            messages.warning(request, 'Username is already exists')
            return redirect('user_registration')

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered.")
            return redirect('user_registration')

        # Check if passwords match
        if password != confirm_password:
            messages.error(request, "Both passwords did not match.")
            return redirect('user_registration')

        User.objects.create(
            username=username,
            name=name,
            email=email,
            password=make_password(password)
        )

        messages.success(request, "Registration successful. Please log in.")
        return redirect('user_login')

    return render(request, "register.html")


def user_logout(request):
    request.session.flush()
    messages.success(request, "Logged out successfully.")
    return redirect('home')


# ========================================
# OTP login
# ========================================

OTP_VALID_SECONDS = 600
OTP_MAX_ATTEMPTS = 5

OTP_EMAIL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: 'Segoe UI', sans-serif;
            background-color: #f4f6f8;
            margin: 0;
            padding: 0;
        }}
        .container {{
            max-width: 500px;
            margin: 40px auto;
            background: #ffffff;
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .title {{
            font-size: 22px;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 10px;
        }}
        .badge {{
            display: inline-block;
            background: #ff9800;
            color: white;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 12px;
            margin-bottom: 15px;
        }}
        .subtitle {{
            color: #555;
            font-size: 14px;
            margin-bottom: 25px;
        }}
        .otp-box {{
            font-size: 34px;
            font-weight: bold;
            color: white;
            background: linear-gradient(135deg, {color1}, {color2});
            padding: 15px 25px;
            border-radius: 10px;
            display: inline-block;
            letter-spacing: 5px;
            margin-bottom: 20px;
        }}
        .note {{
            font-size: 13px;
            color: #888;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="title">🔐 Fake News Detection</div>
        {badge}
        <div class="subtitle">{intro}</div>

        <div class="otp-box">{otp}</div>

        <div class="subtitle">
            This OTP is valid for <b>10 minutes</b><br>
            Do not share it with anyone
        </div>

        <div class="note">{note}</div>
    </div>
</body>
</html>
"""


def send_otp(request, email, resend=False):
    otp = f"{random.SystemRandom().randint(0, 999999):06d}"

    # Stored in the (database-backed) session so it survives restarts and multiple workers
    request.session['otp_email'] = email
    request.session['otp'] = make_password(otp)
    request.session['otp_time'] = time.time()
    request.session['otp_attempts'] = 0

    if resend:
        subject = "Your OTP for Login (Resent)"
        html_content = OTP_EMAIL_HTML.format(
            color1="#ff758c", color2="#ff7eb3", otp=otp,
            badge='<div class="badge">OTP Resent</div>',
            intro="Your previous OTP expired or was requested again.",
            note="If you didn't request this, please secure your account.",
        )
    else:
        subject = "Your OTP for Login"
        html_content = OTP_EMAIL_HTML.format(
            color1="#667eea", color2="#764ba2", otp=otp, badge="",
            intro="Use the OTP below to securely log in",
            note="If you didn't request this, please ignore this email.",
        )
    text_content = f"Your Fake News Detection login OTP is {otp}. It is valid for 10 minutes."

    email_message = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [email])
    email_message.attach_alternative(html_content, "text/html")
    email_message.send()


def clear_otp(request):
    for key in ('otp_email', 'otp', 'otp_time', 'otp_attempts'):
        request.session.pop(key, None)


def otp_login_home(request):
    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip()

        if not email:
            messages.error(request, "Email is required")
            return redirect('otp_login_home')

        user = User.objects.filter(email=email).first()
        if not user:
            messages.error(request, "Email is not registered")
            return redirect('otp_login_home')

        if user.is_banned:
            messages.error(request, "Your account is banned. You cannot log in.")
            return redirect('otp_login_home')

        try:
            send_otp(request, email)
        except Exception:
            messages.error(request, "Could not send the OTP email. Please try again later.")
            return redirect('otp_login_home')

        messages.success(request, f"OTP sent successfully to {email}")
        return redirect('verify_otp')

    return render(request, 'OTP/otp_login_home.html')


def verify_otp(request):
    if request.method == "POST":
        otp = (request.POST.get("otp") or "").strip()
        email = request.session.get("otp_email")
        stored_otp = request.session.get("otp")

        if not otp:
            messages.error(request, "OTP is required")
            return redirect('verify_otp')

        if not email or not stored_otp:
            messages.error(request, "No OTP found. Please request again.")
            return redirect('otp_login_home')

        # Check if OTP expired (10 minutes)
        if time.time() - request.session.get("otp_time", 0) > OTP_VALID_SECONDS:
            clear_otp(request)
            messages.error(request, "OTP has expired. Please request a new one.")
            return redirect('otp_login_home')

        attempts = request.session.get("otp_attempts", 0) + 1
        request.session["otp_attempts"] = attempts
        if attempts > OTP_MAX_ATTEMPTS:
            clear_otp(request)
            messages.error(request, "Too many wrong attempts. Please request a new OTP.")
            return redirect('otp_login_home')

        if check_password(otp, stored_otp):
            user = User.objects.filter(email=email).first()
            clear_otp(request)

            if not user or user.is_banned:
                messages.error(request, "Your account is banned. You cannot log in.")
                return redirect('user_login')

            login_session(request, user)
            messages.success(request, "Logged in Successfully")
            return redirect('user_home')

        messages.error(request, "Invalid OTP")
        return redirect('verify_otp')

    return render(request, 'OTP/verify_otp.html')


def resend_otp(request):
    email = request.session.get("otp_email")

    if not email:
        messages.error(request, "No email found. Please login again.")
        return redirect('otp_login_home')

    try:
        send_otp(request, email, resend=True)
    except Exception:
        messages.error(request, "Could not send the OTP email. Please try again later.")
        return redirect('verify_otp')

    messages.success(request, f"New OTP has been sent to {email}")
    return redirect('verify_otp')


# ========================================
# after user login
# ========================================

@user_required
def userhome(request):
    own = NewsHistory.objects.filter(user_id=request.session['user_id'])
    detailed = [r.confidence for r in own.filter(real_probability__isnull=False)]
    context = {
        "stats": prediction_counts(own),
        "recent": own.order_by('-timestamp')[:5],
        "avg_confidence": round(sum(detailed) * 100 / len(detailed), 1) if detailed else None,
    }
    return render(request, 'user_home.html', context)


@user_required
def user_contact(request):
    return contact(request)


def user_about(request):
    return render(request, 'about.html')


# ========================================
# detection function
# ========================================

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_PATH = settings.BASE_DIR / "bert_fake_news_model"
REAL_LABEL = 1  # model output index meaning "Real" (0 = "Fake")
MAX_TOKENS = 512
LOW_CONFIDENCE = 0.70  # below this, results are flagged as "low confidence" in the UI

# Facts about the model shown in the UI
MODEL_INFO = {
    "id": "Pulk17/Fake-News-Detection",
    "url": "https://huggingface.co/Pulk17/Fake-News-Detection",
    "base": "bert-base-uncased",
    "layers": 12,
    "params": "110M",
    "max_tokens": MAX_TOKENS,
    "labels": ["Fake", "Real"],
}

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_tokenizer = None
_model = None


def load_model():
    """Load tokenizer and model once, on first prediction (keeps manage.py commands fast)."""
    global _tokenizer, _model
    if _model is None:
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
        _model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
        _model.to(device)
        _model.eval()
        # One warm-up pass so the first real request isn't billed for one-time setup
        with torch.no_grad():
            _model(**{k: v.to(device) for k, v in _tokenizer("warm up", return_tensors="pt").items()})
    return _tokenizer, _model


def analyze_news(text):
    """Run BERT on the text; returns the label plus the details the model actually produces."""
    tokenizer, model = load_model()
    started = time.perf_counter()

    full_length = len(tokenizer(text, truncation=False, verbose=False)["input_ids"])
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=MAX_TOKENS, padding=True)

    # Move to device
    inputs = {key: val.to(device) for key, val in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)

    probs = torch.softmax(outputs.logits, dim=1)[0]
    real_probability = probs[REAL_LABEL].item()
    label = "Real" if int(torch.argmax(probs).item()) == REAL_LABEL else "Fake"

    return {
        "label": label,
        "real_probability": real_probability,
        "token_count": min(full_length, MAX_TOKENS),
        "truncated": full_length > MAX_TOKENS,
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }


def predict_news(text):
    return analyze_news(text)["label"]


SAMPLE_ARTICLES = {
    "wire": ("BRUSSELS (Reuters) - European Union finance ministers agreed on Friday to extend a budget "
             "deficit deadline for France by two years, officials said after a meeting in Luxembourg."),
    "clickbait": ("SHOCKING!!! You won't BELIEVE what the media is hiding from you. Insiders just EXPOSED "
                  "the plot they refuse to cover. SHARE before it gets DELETED!!!"),
}
_sample_cache = {}


def sample_analysis(request):
    """Live model output on two fixed sample texts, used by the landing page preview."""
    if not _sample_cache:
        for key, text in SAMPLE_ARTICLES.items():
            _sample_cache[key] = {"text": text, **analyze_news(text)}
    return JsonResponse({"model": MODEL_INFO["id"], "samples": _sample_cache})


@user_required
def detect(request):
    if request.method == "POST":

        text = (request.POST.get('news_text') or '').strip()

        if not text:
            messages.error(request, "Paste an article or headline to analyze.")
            return redirect('detect')

        if len(text.split()) < 5:
            messages.warning(request, "Add at least a full sentence — the model needs context to judge writing style.")
            return render(request, "detect.html", {"text": text}, status=400)

        user = User.objects.filter(id=request.session['user_id']).first()
        if not user:
            request.session.flush()
            return redirect('user_login')

        analysis = analyze_news(text)

        record = NewsHistory.objects.create(
            user=user,
            news_text=text,
            result=analysis["label"],
            real_probability=analysis["real_probability"],
            token_count=analysis["token_count"],
            truncated=analysis["truncated"],
            latency_ms=analysis["latency_ms"],
        )
        return redirect('result', pk=record.pk)

    return render(request, "detect.html", {"model": MODEL_INFO})


@user_required
def result(request, pk):
    record = get_object_or_404(NewsHistory, pk=pk, user_id=request.session['user_id'])
    return render(request, "result.html", {
        "record": record,
        "model": MODEL_INFO,
        "low_confidence": record.confidence is not None and record.confidence < LOW_CONFIDENCE,
        "low_confidence_pct": round(LOW_CONFIDENCE * 100),
    })


@user_required
def history(request):
    own = NewsHistory.objects.filter(user_id=request.session['user_id'])
    result_filter = request.GET.get('result')
    query = (request.GET.get('q') or '').strip()

    user_history = own.order_by('-timestamp')
    if result_filter in ["Real", "Fake"]:
        user_history = user_history.filter(result=result_filter)
    if query:
        user_history = user_history.filter(news_text__icontains=query)

    # Pagination (10 per page)
    paginator = Paginator(user_history, 10)
    history_page = paginator.get_page(request.GET.get('page'))

    return render(request, "history.html", {
        "history": history_page,
        "stats": prediction_counts(own),
        "result_filter": result_filter,
        "query": query,
    })


# ========================================
# admin
# ========================================

def admin_login(request):
    if request.method == 'POST':
        admin_username = (request.POST.get('admin_username') or '').strip()
        password = request.POST.get('password') or ''

        admin_obj = AdminData.objects.filter(
            Q(admin_username=admin_username) | Q(admin_email=admin_username)
        ).first()

        if admin_obj and verify_password(admin_obj, password):
            request.session.cycle_key()
            request.session['admin_username'] = admin_obj.admin_username
            messages.success(request, "Successfully logged in")
            return redirect('admin_home')

        messages.error(request, "Invalid Username or Password...!")
        return redirect('admin_login')

    return render(request, 'admin_login.html')


def admin_registration(request):
    # The first admin can sign up freely; after that only a logged-in admin can add admins.
    if AdminData.objects.exists() and not request.session.get('admin_username'):
        messages.error(request, "Only a logged-in admin can register new admins.")
        return redirect('admin_login')

    if request.method == 'POST':
        admin_username = (request.POST.get('admin_username') or '').strip()
        email = (request.POST.get('email') or '').strip()
        pass1 = request.POST.get('password') or ''
        pass2 = request.POST.get('confirm_password') or ''

        if not (admin_username and email and pass1):
            messages.warning(request, 'All fields are required')
            return redirect('admin_registration')

        if pass1 != pass2:
            messages.warning(request, 'Both password are not matched')
            return redirect('admin_registration')

        if AdminData.objects.filter(admin_username=admin_username).exists():
            messages.warning(request, 'Admin username is already exists')
            return redirect('admin_registration')

        if AdminData.objects.filter(admin_email=email).exists():
            messages.warning(request, 'Admin email is already registered')
            return redirect('admin_registration')

        AdminData.objects.create(admin_username=admin_username, admin_email=email,
                                 password=make_password(pass1))
        messages.success(request, 'The admin ' + admin_username + " is saved successfully..!")
        if request.session.get('admin_username'):
            return redirect('admin_home')
        return redirect('admin_login')

    layout = "layouts/admin.html" if request.session.get('admin_username') else "layouts/auth.html"
    return render(request, 'admin_registration.html', {"layout": layout})


def admin_logout(request):
    request.session.flush()
    messages.success(request, "Logged out successfully.")
    return redirect('home')


@admin_required
def admin_home(request):
    context = {
        "total_users": User.objects.count(),
        "banned_users": User.objects.filter(is_banned=True).count(),
        "stats": prediction_counts(NewsHistory.objects.all()),
        "messages_count": Contact.objects.count(),
        "recent": NewsHistory.objects.select_related('user').order_by('-timestamp')[:6],
    }
    return render(request, "admin_dir/admin_home.html", context)


@admin_required
def view_user(request):
    form = User.objects.all()
    return render(request, 'admin_dir/view_user.html', {'forms': form})


@admin_required
def view_contact(request):
    form = Contact.objects.all()
    return render(request, 'admin_dir/view_contact.html', {'forms': form})


@admin_required
def news_history(request):
    selected_date = request.GET.get('date')
    result_filter = request.GET.get('result')

    history_list = NewsHistory.objects.select_related('user').order_by('-timestamp')

    # Filter by date
    if selected_date:
        history_list = history_list.filter(timestamp__date=selected_date)

    # Filter by result (Real / Fake)
    if result_filter in ["Real", "Fake"]:
        history_list = history_list.filter(result=result_filter)

    # Pagination (10 entries)
    paginator = Paginator(history_list, 10)
    history = paginator.get_page(request.GET.get('page'))

    context = {
        "history": history,
        "selected_date": selected_date,
        "result_filter": result_filter
    }
    return render(request, "admin_dir/news_history.html", context)


@admin_required
def view_statistics(request):
    # daily predictions
    daily_data = list(
        NewsHistory.objects
        .annotate(date=TruncDate('timestamp'))
        .values('date')
        .annotate(
            count=Count('id'),
            fake=Count('id', filter=Q(result="Fake")),
        )
        .order_by('date')
    )

    # confidence distribution (only predictions that stored model probabilities)
    detailed = list(NewsHistory.objects.filter(real_probability__isnull=False))
    buckets = [0] * 5  # 50-60, 60-70, 70-80, 80-90, 90-100
    for record in detailed:
        buckets[min(int((record.confidence - 0.5) * 10), 4)] += 1
    latency = NewsHistory.objects.filter(latency_ms__isnull=False).aggregate(avg=Avg('latency_ms'))['avg']

    context = {
        "total_users": User.objects.count(),
        "stats": prediction_counts(NewsHistory.objects.all()),
        "dates": [str(d['date']) for d in daily_data],
        "real_counts": [d['count'] - d['fake'] for d in daily_data],
        "fake_counts": [d['fake'] for d in daily_data],
        "daily_rows": [dict(date=d['date'], count=d['count'], fake=d['fake'], real=d['count'] - d['fake'])
                       for d in reversed(daily_data)],
        "confidence_buckets": buckets,
        "detailed_count": len(detailed),
        "avg_confidence": round(sum(r.confidence for r in detailed) * 100 / len(detailed), 1) if detailed else None,
        "avg_latency": round(latency) if latency else None,
    }
    return render(request, "admin_dir/statistics.html", context)


@admin_required
@require_POST
def delete_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.delete()
    messages.success(request, "User Deleted Successfully")
    return redirect('view_user')


@admin_required
@require_POST
def ban_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.is_banned = True
    user.save(update_fields=['is_banned'])
    return redirect('view_user')


@admin_required
@require_POST
def unban_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.is_banned = False
    user.save(update_fields=['is_banned'])
    return redirect('view_user')
