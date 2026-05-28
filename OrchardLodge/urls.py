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

    path('login/', LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('change-password/', PasswordChangeView.as_view(template_name='registration/change-password.html', success_url = '/'), name='change_password'),
    path('logout/', LogoutView.as_view(next_page='/'), name='logout'),

    path('residents/', views.residents, name="residents"),
    path('residents/<res_url>/',views.specific_resident, name="specific_resident"),
    path('payments/', views.payments, name="payments"),
    path('payments/new/', views.new_payments, name="new_payments"),
    path('sefton-action-items/', views.sefton_action_items, name="sefton_action_items"),
    path('sefton-action-items/<str:action_id>/', views.sefton_action_item, name="sefton_action_item"),
    path('cash-and-cheques/', views.cash_and_cheques, name="cash_and_cheques"),

    path('upload/', views.upload, name="upload"),
    path('download/', views.download, name="download"),
]
