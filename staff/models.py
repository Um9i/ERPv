from django.db import models
from django.contrib.auth.models import User, Group


class StaffProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    groups = models.ManyToManyField(Group, blank=True)

    def __str__(self):
        return f"{self.user.username}"
