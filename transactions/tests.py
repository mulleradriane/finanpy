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

class NewTransactionTypeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='test_types@example.com', password='password123')
        self.client.login(email='test_types@example.com', password='password123')

        self.account = Account.objects.create(
            user=self.user,
            name='Test Account',
            bank_name='Test Bank',
            account_type=Account.CHECKING,
            balance=Decimal('1000.00')
        )

        self.category_expense = Category.objects.create(
            user=self.user,
            name='Expense Category',
            category_type=Category.CategoryType.EXPENSE
        )

    def test_create_credito_transaction(self):
        url = reverse('transactions:transaction_create')
        data = {
            'account': self.account.id,
            'category': self.category_expense.id,
            'transaction_type': Transaction.TransactionType.CREDITO,
            'amount': Decimal('100.00'),
            'transaction_date': date.today().isoformat(),
            'description': 'Credito payment'
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        self.account.refresh_from_db()
        # Credito should be treated as expense: 1000 - 100 = 900
        self.assertEqual(self.account.balance, Decimal('900.00'))

    def test_create_debito_transaction(self):
        url = reverse('transactions:transaction_create')
        data = {
            'account': self.account.id,
            'category': self.category_expense.id,
            'transaction_type': Transaction.TransactionType.DEBITO,
            'amount': Decimal('50.00'),
            'transaction_date': date.today().isoformat(),
            'description': 'Debito payment'
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        self.account.refresh_from_db()
        # Debito should be treated as expense: 1000 - 50 = 950
        self.assertEqual(self.account.balance, Decimal('950.00'))

    def test_create_pix_transaction(self):
        url = reverse('transactions:transaction_create')
        data = {
            'account': self.account.id,
            'category': self.category_expense.id,
            'transaction_type': Transaction.TransactionType.PIX,
            'amount': Decimal('20.00'),
            'transaction_date': date.today().isoformat(),
            'description': 'PIX payment'
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        self.account.refresh_from_db()
        # PIX should be treated as expense: 1000 - 20 = 980
        self.assertEqual(self.account.balance, Decimal('980.00'))

class AnalyticsViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='test_analytics@example.com', password='password123')
        self.client.login(email='test_analytics@example.com', password='password123')

        self.account = Account.objects.create(
            user=self.user,
            name='Analytics Account',
            bank_name='Test Bank',
            account_type=Account.CHECKING,
            balance=Decimal('2000.00')
        )

        self.cat_income = Category.objects.get(
            user=self.user,
            name='Salário'
        )

        self.cat_expense = Category.objects.get(
            user=self.user,
            name='Alimentação'
        )

        self.cat_invest = Category.objects.get(
            user=self.user,
            name='Investimentos'
        )

        # Create some transactions for current year
        today = date.today()

        # Income
        Transaction.objects.create(
            account=self.account,
            category=self.cat_income,
            transaction_type=Transaction.TransactionType.INCOME,
            amount=Decimal('5000.00'),
            transaction_date=today.replace(day=1),
            description='Salário'
        )

        # Expense
        Transaction.objects.create(
            account=self.account,
            category=self.cat_expense,
            transaction_type=Transaction.TransactionType.EXPENSE,
            amount=Decimal('1000.00'),
            transaction_date=today.replace(day=2),
            description='Supermercado'
        )

        # Investment
        Transaction.objects.create(
            account=self.account,
            category=self.cat_invest,
            transaction_type=Transaction.TransactionType.EXPENSE,
            amount=Decimal('500.00'),
            transaction_date=today.replace(day=3),
            description='Ações'
        )

    def test_analytics_view_status_code(self):
        url = reverse('transactions:analytics')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'transactions/analytics.html')

    def test_analytics_context_data(self):
        url = reverse('transactions:analytics')
        response = self.client.get(url)

        self.assertEqual(response.context['annual_income'], Decimal('5000.00'))
        self.assertEqual(response.context['annual_expenses'], Decimal('1500.00')) # 1000 + 500
        self.assertEqual(response.context['annual_balance'], Decimal('3500.00'))
        self.assertEqual(response.context['annual_investments'], Decimal('500.00'))

        # Check current month investments
        self.assertEqual(response.context['month_investments'], Decimal('500.00'))

        # Check category analytics
        categories = response.context['category_analytics']
        self.assertTrue(any(c['name'] == 'Salário' and c['annual'] == Decimal('5000.00') for c in categories))
        self.assertTrue(any(c['name'] == 'Alimentação' and c['annual'] == Decimal('1000.00') for c in categories))
        self.assertTrue(any(c['name'] == 'Investimentos' and c['annual'] == Decimal('500.00') for c in categories))
