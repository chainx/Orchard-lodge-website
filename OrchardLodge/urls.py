"""OrchardLodge URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
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
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.urls import path, include
from main import views

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name="home"),
    path('', include("django.contrib.auth.urls")),
    path('change-password/', PasswordChangeView.as_view(template_name='registration/change-password.html',success_url = '/'), name='change_password'),
    path('residents/', views.residents, name="residents"),
    path('residents/<res_url>/',views.specific_resident, name="specific_resident"),
    path('upload/', views.upload, name="upload"),
    path('download/', views.download, name="download"),
]
