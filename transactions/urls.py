from django.urls import path

from .views import (
    AnalyticsView, TransactionCreateView, TransactionDeleteView,
    TransactionListView, TransactionUpdateView
)

app_name = 'transactions'

urlpatterns = [
    path('', TransactionListView.as_view(), name='transaction_list'),
    path('analytics/', AnalyticsView.as_view(), name='analytics'),
    path('new/', TransactionCreateView.as_view(), name='transaction_create'),
    path('<int:pk>/edit/', TransactionUpdateView.as_view(), name='transaction_update'),
    path('<int:pk>/delete/', TransactionDeleteView.as_view(), name='transaction_delete'),
]
