"""Custom User model with UUID PK, role, and language preference."""
import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, name, role, password, lang='es', **kwargs):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user  = self.model(email=email, name=name, role=role, lang=lang, **kwargs)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, password, **kwargs):
        kwargs.setdefault('is_staff',     True)
        kwargs.setdefault('is_superuser', True)
        return self.create_user(email, name, 'admin', password, **kwargs)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('admin',      'Admin'),
        ('sales',      'Sales'),
        ('operations', 'Operations'),
        ('finance',    'Finance'),
    ]

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email      = models.EmailField(unique=True)
    name       = models.CharField(max_length=200)
    role       = models.CharField(max_length=20, choices=ROLE_CHOICES)
    lang       = models.CharField(max_length=5, default='es')
    is_active  = models.BooleanField(default=True)
    is_staff   = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['name', 'role']

    objects = UserManager()

    class Meta:
        db_table = 'users'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} <{self.email}>'
