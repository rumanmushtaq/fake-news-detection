import math

from django.db import models

# Create your models here.


class User(models.Model):
    username = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=89)
    email = models.EmailField(max_length=90, unique=True)
    password = models.CharField(max_length=128)
    is_banned = models.BooleanField(default=False)

    def __str__(self):
        return self.username


class Contact(models.Model):
    names = models.CharField(max_length=30)
    email = models.EmailField(max_length=50, null='True')
    phone = models.CharField(max_length=10, null='True')
    desc = models.TextField(null='True')
    # var = models.TextField(null='True')
    # var2 = models.TextField(null='True')


class AdminData(models.Model):
    admin_username = models.CharField(max_length=80, unique=True)
    admin_email = models.EmailField(max_length=90, unique=True)
    password = models.CharField(max_length=128)


class NewsHistory(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    news_text = models.TextField()
    result = models.CharField(max_length=20)
    timestamp = models.DateTimeField(auto_now_add=True)
    # Model output details (empty for predictions saved before these fields existed)
    real_probability = models.FloatField(null=True, blank=True)
    token_count = models.PositiveIntegerField(null=True, blank=True)
    truncated = models.BooleanField(default=False)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)

    @property
    def confidence(self):
        """Probability of the predicted label, 0-1."""
        if self.real_probability is None:
            return None
        return self.real_probability if self.result == "Real" else 1 - self.real_probability

    @property
    def confidence_pct(self):
        # Rounded down so 99.98% shows as 99.9%, never an overstated 100.0%
        c = self.confidence
        return None if c is None else math.floor(c * 1000) / 10

    @property
    def real_pct(self):
        return None if self.real_probability is None else math.floor(self.real_probability * 1000) / 10

    @property
    def fake_pct(self):
        return None if self.real_probability is None else math.floor((1 - self.real_probability) * 1000) / 10

    @property
    def word_count(self):
        return len(self.news_text.split())
