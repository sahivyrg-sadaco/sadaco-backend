from django.db import models


class Notification(models.Model):
    user       = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='notifications',
    )
    type       = models.CharField(max_length=50)
    title      = models.CharField(max_length=500)
    body       = models.TextField()
    link       = models.CharField(max_length=500, blank=True)
    read       = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.type}: {self.title}'
