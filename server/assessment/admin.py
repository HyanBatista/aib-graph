from django.contrib import admin

from .models import ItemAnswer, Test, TestAttempt, TestItem

admin.site.register(Test)
admin.site.register(TestItem)
admin.site.register(TestAttempt)
admin.site.register(ItemAnswer)
