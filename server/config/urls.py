from django.contrib import admin
from django.urls import path

from .api import api

# Uploaded books (MEDIA_ROOT) are deliberately not served: clients read pages through the authenticated API.
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]
