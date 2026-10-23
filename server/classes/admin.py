from django.contrib import admin

from .models import Classroom, Membership


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ("name", "professor", "status", "invite_code")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "classroom", "role")
    list_filter = ("role",)
