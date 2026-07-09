"""
URL configuration for schoolsoft project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.static import serve as serve_static

urlpatterns = [
    path('', include('core.urls')),
    path('admin/', admin.site.urls),
]

# Serve uploaded media (student photos, etc.) ourselves in every environment.
# WhiteNoise only serves STATIC_URL, not MEDIA_URL, and this app is small/low-traffic
# enough (single school) that Django's own file serving is fine - no need for a
# separate nginx/object-storage layer just to show a photo.
urlpatterns += [
    path(
        f"{settings.MEDIA_URL.lstrip('/')}<path:path>",
        serve_static,
        {"document_root": settings.MEDIA_ROOT},
    ),
]
