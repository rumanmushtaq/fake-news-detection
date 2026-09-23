import time
import unittest
from unittest import mock

from django.contrib.auth.hashers import make_password
from django.core import mail
from django.test import TestCase, override_settings

from . import views
from .models import AdminData, Contact, NewsHistory, User

LOCMEM_EMAIL = override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')


def make_user(username="alice", email="alice@example.com", password="pw12345", **kw):
    return User.objects.create(username=username, name=username.title(), email=email,
                               password=make_password(password), **kw)


def make_admin(username="root", email="root@example.com", password="adminpw"):
    return AdminData.objects.create(admin_username=username, admin_email=email,
                                    password=make_password(password))


class PublicPagesTests(TestCase):
    def test_public_pages_render(self):
        for url in ["/", "/about/", "/contact/", "/user_login/", "/user_registration/",
                    "/otp_login_home/", "/admin_login/", "/admin_registration/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_project_files_not_served(self):
        for url in ["/db.sqlite3", "/global_project/settings.py", "/manage.py"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)


class RegistrationLoginTests(TestCase):
    def register(self, **overrides):
        data = dict(username="alice", name="Alice", email="alice@example.com",
                    password="pw12345", confirm_password="pw12345")
        data.update(overrides)
        return self.client.post("/user_registration/", data)

    def test_register_hashes_password(self):
        self.assertRedirects(self.register(), "/user_login/")
        user = User.objects.get(username="alice")
        self.assertNotEqual(user.password, "pw12345")
        self.assertTrue(user.password.startswith("pbkdf2_"))
        self.assertEqual(str(user), "alice")

    def test_register_rejects_mismatch_and_empty(self):
        self.register(confirm_password="other")
        self.client.post("/user_registration/", {})
        self.assertEqual(User.objects.count(), 0)

    def test_login_by_email_and_username(self):
        make_user()
        for identifier in ["alice@example.com", "alice"]:
            with self.subTest(identifier=identifier):
                self.client.post("/user_logout/")
                r = self.client.post("/user_login/", dict(email=identifier, password="pw12345"))
                self.assertRedirects(r, "/user_home/")
                self.assertIsNotNone(self.client.session.get("user_id"))

    def test_login_wrong_password(self):
        make_user()
        self.client.post("/user_login/", dict(email="alice", password="nope"))
        self.assertNotIn("user_id", self.client.session)

    def test_legacy_plaintext_password_upgraded(self):
        User.objects.create(username="old", name="Old", email="old@example.com", password="plain")
        self.client.post("/user_login/", dict(email="old", password="plain"))
        self.assertIsNotNone(self.client.session.get("user_id"))
        self.assertTrue(User.objects.get(username="old").password.startswith("pbkdf2_"))

    def test_banned_user_cannot_login(self):
        make_user(is_banned=True)
        self.client.post("/user_login/", dict(email="alice", password="pw12345"))
        self.assertNotIn("user_id", self.client.session)

    def test_user_pages_require_login(self):
        for url in ["/user_home/", "/detect/", "/history/", "/user_contact/"]:
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), "/user_login/")


FAKE_ANALYSIS = {"label": "Fake", "real_probability": 0.12, "token_count": 7, "truncated": False, "latency_ms": 41}


@mock.patch.object(views, "analyze_news", return_value=FAKE_ANALYSIS)
class DetectionTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.post("/user_login/", dict(email="alice", password="pw12345"))

    def test_detect_saves_history_and_redirects_to_result(self, analyze):
        r = self.client.post("/detect/", dict(news_text="Some news text for the model"))
        record = NewsHistory.objects.get()
        self.assertRedirects(r, f"/result/{record.pk}/")
        analyze.assert_called_once_with("Some news text for the model")
        self.assertEqual(record.user, self.user)
        self.assertEqual(record.result, "Fake")
        self.assertEqual(record.confidence_pct, 88.0)
        page = self.client.get(f"/result/{record.pk}/")
        self.assertContains(page, "Reads as fake")
        self.assertContains(page, "88.0%")

    def test_detect_rejects_empty_and_too_short(self, analyze):
        self.assertRedirects(self.client.post("/detect/", dict(news_text="   ")), "/detect/")
        r = self.client.post("/detect/", dict(news_text="too short"))
        self.assertEqual(r.status_code, 400)
        self.assertContains(r, "too short", status_code=400)  # text kept in the box
        analyze.assert_not_called()

    def test_result_is_private(self, analyze):
        other = make_user("bob", "bob@example.com")
        record = NewsHistory.objects.create(user=other, news_text="Bob's article", result="Real")
        self.assertEqual(self.client.get(f"/result/{record.pk}/").status_code, 404)

    def test_legacy_record_without_probability(self, analyze):
        record = NewsHistory.objects.create(user=self.user, news_text="Old article", result="Real")
        r = self.client.get(f"/result/{record.pk}/")
        self.assertContains(r, "Reads as real")
        self.assertContains(r, "before confidence scores were recorded")

    def test_low_confidence_flag(self, analyze):
        record = NewsHistory.objects.create(user=self.user, news_text="Unclear article", result="Real",
                                            real_probability=0.55)
        self.assertContains(self.client.get(f"/result/{record.pk}/"), "Low confidence")

    def test_history_shows_own_predictions_with_filters(self, analyze):
        NewsHistory.objects.create(user=self.user, news_text="My own real article", result="Real")
        NewsHistory.objects.create(user=self.user, news_text="My own fake article", result="Fake")
        other = make_user("bob", "bob@example.com")
        NewsHistory.objects.create(user=other, news_text="Someone else's article", result="Real")
        r = self.client.get("/history/")
        self.assertContains(r, "My own real article")
        self.assertNotContains(r, "Someone else")
        r = self.client.get("/history/?result=Fake")
        self.assertContains(r, "My own fake article")
        self.assertNotContains(r, "My own real article")
        r = self.client.get("/history/?q=nothing-matches")
        self.assertContains(r, "No matches")

    def test_workspace_pages_render(self, analyze):
        NewsHistory.objects.create(user=self.user, news_text="An article", result="Real", real_probability=0.9)
        for url in ["/user_home/", "/detect/", "/history/", "/user_contact/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class SampleAnalysisTests(TestCase):
    @mock.patch.object(views, "analyze_news", return_value=FAKE_ANALYSIS)
    def test_sample_api(self, analyze):
        views._sample_cache.clear()
        data = self.client.get("/api/sample-analysis/").json()
        self.assertEqual(set(data["samples"]), {"wire", "clickbait"})
        self.assertEqual(data["samples"]["wire"]["label"], "Fake")
        views._sample_cache.clear()


@unittest.skipUnless((views.MODEL_PATH / "config.json").exists(), "model not downloaded")
class RealModelTests(TestCase):
    def test_model_predictions(self):
        real = ("WASHINGTON (Reuters) - The U.S. Senate on Tuesday voted 68-31 to approve a bill "
                "funding the government through December, congressional aides said.")
        fake = ("YOU WON'T BELIEVE what Obama just got caught doing!!! Patriots are FURIOUS after "
                "this SHOCKING video leaked. SHARE before it gets deleted!")
        self.assertEqual(views.predict_news(real), "Real")
        self.assertEqual(views.predict_news(fake), "Fake")

    def test_long_text_is_truncated(self):
        analysis = views.analyze_news("word " * 3000)
        self.assertEqual(analysis["token_count"], 512)
        self.assertTrue(analysis["truncated"])

    def test_detect_end_to_end_with_real_model(self):
        make_user()
        self.client.post("/user_login/", dict(email="alice", password="pw12345"))
        text = ("YOU WON'T BELIEVE what Obama just got caught doing!!! Patriots are FURIOUS after "
                "this SHOCKING video leaked. SHARE before it gets deleted!")
        r = self.client.post("/detect/", dict(news_text=text), follow=True)
        record = NewsHistory.objects.get()
        self.assertEqual(record.result, "Fake")
        self.assertGreater(record.confidence, 0.5)
        self.assertIsNotNone(record.latency_ms)
        self.assertContains(r, "Reads as fake")


@LOCMEM_EMAIL
class OtpTests(TestCase):
    def setUp(self):
        make_user()

    def request_otp(self, email="alice@example.com"):
        return self.client.post("/otp_login_home/", dict(email=email))

    def sent_otp(self):
        return mail.outbox[-1].body.split("OTP is ")[1][:6]

    def test_unregistered_email(self):
        self.assertRedirects(self.request_otp("nobody@example.com"), "/otp_login_home/")
        self.assertEqual(len(mail.outbox), 0)

    def test_full_otp_login(self):
        self.assertRedirects(self.request_otp(), "/otp_login_home/verify_otp/")
        self.assertEqual(len(mail.outbox), 1)
        r = self.client.post("/otp_login_home/verify_otp/", dict(otp=self.sent_otp()))
        self.assertRedirects(r, "/user_home/")
        self.assertEqual(self.client.session.get("username"), "alice")

    def test_wrong_and_non_numeric_otp(self):
        self.request_otp()
        for bad in ["abc", "000000x"]:
            r = self.client.post("/otp_login_home/verify_otp/", dict(otp=bad))
            self.assertRedirects(r, "/otp_login_home/verify_otp/")
        self.assertNotIn("user_id", self.client.session)

    def test_attempt_limit(self):
        self.request_otp()
        otp = self.sent_otp()
        for _ in range(views.OTP_MAX_ATTEMPTS):
            self.client.post("/otp_login_home/verify_otp/", dict(otp="wrong"))
        self.client.post("/otp_login_home/verify_otp/", dict(otp=otp))
        self.assertNotIn("user_id", self.client.session)

    def test_expired_otp(self):
        self.request_otp()
        otp = self.sent_otp()
        session = self.client.session
        session["otp_time"] = time.time() - views.OTP_VALID_SECONDS - 1
        session.save()
        r = self.client.post("/otp_login_home/verify_otp/", dict(otp=otp))
        self.assertRedirects(r, "/otp_login_home/")
        self.assertNotIn("user_id", self.client.session)

    def test_resend(self):
        self.request_otp()
        r = self.client.get("/otp_login_home/verify_otp/resend_OTP/")
        self.assertRedirects(r, "/otp_login_home/verify_otp/")
        self.assertEqual(len(mail.outbox), 2)
        r = self.client.post("/otp_login_home/verify_otp/", dict(otp=self.sent_otp()))
        self.assertRedirects(r, "/user_home/")

    def test_banned_user_cannot_use_otp(self):
        User.objects.filter(username="alice").update(is_banned=True)
        self.request_otp()
        self.assertEqual(len(mail.outbox), 0)
        self.assertNotIn("user_id", self.client.session)


class ContactTests(TestCase):
    data = dict(name="Zed", email="z@example.com", phone="1234567890", desc="Hello")

    def test_public_contact_saves(self):
        self.client.post("/contact/", self.data)
        self.assertEqual(Contact.objects.get().names, "Zed")

    def test_user_contact_saves(self):
        make_user()
        self.client.post("/user_login/", dict(email="alice", password="pw12345"))
        self.client.post("/user_contact/", self.data)
        self.assertEqual(Contact.objects.count(), 1)


class AdminTests(TestCase):
    ADMIN_URLS = ["/admin_home/", "/view_user/", "/view_contact/", "/news_history/", "/view_stat/"]

    def login_admin(self):
        make_admin()
        self.client.post("/admin_login/", dict(admin_username="root", password="adminpw"))

    def test_first_admin_can_register_then_registration_closes(self):
        data = dict(admin_username="root", email="root@example.com", password="p", confirm_password="p")
        self.client.post("/admin_registration/", data)
        self.assertTrue(AdminData.objects.get().password.startswith("pbkdf2_"))
        data.update(admin_username="intruder", email="i@example.com")
        self.assertRedirects(self.client.post("/admin_registration/", data), "/admin_login/")
        self.assertEqual(AdminData.objects.count(), 1)

    def test_admin_duplicate_email(self):
        self.login_admin()
        r = self.client.post("/admin_registration/", dict(admin_username="root2", email="root@example.com",
                                                          password="p", confirm_password="p"))
        self.assertRedirects(r, "/admin_registration/")
        self.assertEqual(AdminData.objects.count(), 1)

    def test_admin_login_by_email(self):
        make_admin()
        self.client.post("/admin_login/", dict(admin_username="root@example.com", password="adminpw"))
        self.assertEqual(self.client.session.get("admin_username"), "root")

    def test_admin_pages_require_admin(self):
        user = make_user()
        for url in self.ADMIN_URLS:
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), "/admin_login/")
        for action in ["ban-user", "delete-user"]:
            self.client.post(f"/{action}/{user.id}/")
        user.refresh_from_db()
        self.assertFalse(user.is_banned)

    def test_admin_pages_render(self):
        self.login_admin()
        u = make_user()
        NewsHistory.objects.create(user=u, news_text="x", result="Fake")
        Contact.objects.create(names="Zed Contact", email="z@example.com", phone="1", desc="d")
        for url in self.ADMIN_URLS + ["/news_history/?result=Fake", "/news_history/?date=2020-01-01"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.get("/view_contact/"), "Zed Contact")

    def test_ban_unban_delete(self):
        self.login_admin()
        u = make_user()
        self.client.post(f"/ban-user/{u.id}/")
        u.refresh_from_db(); self.assertTrue(u.is_banned)
        self.client.post(f"/unban-user/{u.id}/")
        u.refresh_from_db(); self.assertFalse(u.is_banned)
        self.assertEqual(self.client.get(f"/delete-user/{u.id}/").status_code, 405)
        self.client.post(f"/delete-user/{u.id}/")
        self.assertFalse(User.objects.filter(id=u.id).exists())

    def test_missing_user_returns_404(self):
        self.login_admin()
        for action in ["ban-user", "unban-user", "delete-user"]:
            with self.subTest(action=action):
                self.assertEqual(self.client.post(f"/{action}/99999/").status_code, 404)
