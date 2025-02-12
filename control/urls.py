from django.urls import path, re_path
from . import views

ADDRESS_PATTERN = r'0x[a-fA-F0-9]{40}'
HASH_PATTERN = r'0x[a-fA-F0-9]{64}'

urlpatterns = [
    path("", views.view_home, name="home"),
    path("search/<str:search_type>/", views.search_view, name="search"),
    path("error/<int:error_number>/<str:error_message>/", views.view_error, name="error"),
    re_path(f"token/(?P<address>{ADDRESS_PATTERN})/$", views.view_token, name="token"),
    re_path(f"user/(?P<address>{ADDRESS_PATTERN})/$", views.view_user, name="user"),
    re_path(f"transaction/(?P<hash_tx>{HASH_PATTERN})/$", views.view_tx, name="transaction"),
    path("api/token/<str:address>/price", views.api_token_price, name="api_token_price"),
]

