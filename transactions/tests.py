from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Account
from categories.models import Category
from transactions.models import Transaction

User = get_user_model()

class RecurringTransactionTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='test@example.com', password='password123')
        self.client.login(email='test@example.com', password='password123')

        self.account = Account.objects.create(
            user=self.user,
            name='Test Account',
            bank_name='Test Bank',
            account_type=Account.CHECKING,
            balance=Decimal('1000.00')
        )

        self.category = Category.objects.create(
            user=self.user,
            name='Test Category',
            category_type=Category.CategoryType.EXPENSE
        )

    def test_create_recurring_transactions(self):
        url = reverse('transactions:transaction_create')
        data = {
            'account': self.account.id,
            'category': self.category.id,
            'transaction_type': Transaction.TransactionType.EXPENSE,
            'amount': Decimal('50.00'),
            'transaction_date': date.today().isoformat(),
            'description': 'TIM bill',
            'installments': 3
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        transactions = Transaction.objects.all().order_by('transaction_date')
        self.assertEqual(transactions.count(), 3)

        base_date = date.today()
        for i, trans in enumerate(transactions):
            self.assertEqual(trans.amount, Decimal('50.00'))
            self.assertEqual(trans.transaction_date, base_date + relativedelta(months=i))
            self.assertEqual(trans.description, f'TIM bill ({i+1}/3)')

        # Check account balance: 1000 - (3 * 50) = 850
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('850.00'))

    def test_future_date_allowed_for_recurring(self):
        url = reverse('transactions:transaction_create')
        future_date = date.today() + relativedelta(months=1)
        data = {
            'account': self.account.id,
            'category': self.category.id,
            'transaction_type': Transaction.TransactionType.EXPENSE,
            'amount': Decimal('50.00'),
            'transaction_date': future_date.isoformat(),
            'description': 'Future bill',
            'installments': 2
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Transaction.objects.count(), 2)

    def test_future_date_not_allowed_for_single(self):
        url = reverse('transactions:transaction_create')
        future_date = date.today() + relativedelta(days=1)
        data = {
            'account': self.account.id,
            'category': self.category.id,
            'transaction_type': Transaction.TransactionType.EXPENSE,
            'amount': Decimal('50.00'),
            'transaction_date': future_date.isoformat(),
            'description': 'Future bill',
            'installments': 1
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200) # Form invalid
        self.assertIn('A data da transação não pode ser no futuro.', response.content.decode('utf-8'))
        self.assertEqual(Transaction.objects.count(), 0)

    def test_insufficient_balance_for_first_installment(self):
        url = reverse('transactions:transaction_create')
        self.account.balance = Decimal('10.00')
        self.account.save()

        data = {
            'account': self.account.id,
            'category': self.category.id,
            'transaction_type': Transaction.TransactionType.EXPENSE,
            'amount': Decimal('50.00'),
            'transaction_date': date.today().isoformat(),
            'description': 'TIM bill',
            'installments': 3
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Saldo insuficiente na conta selecionada para esta transação.', response.content.decode('utf-8'))
        self.assertEqual(Transaction.objects.count(), 0)
