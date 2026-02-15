from datetime import date
from decimal import Decimal

from django import forms
from django.db.models import Count

from accounts.models import Account
from categories.models import Category

from .models import Transaction


class TransactionForm(forms.ModelForm):
    '''
    Form for creating and editing financial transactions.

    This form handles transaction creation and updates with comprehensive
    validation including:
    - Category type must match transaction type (INCOME/EXPENSE)
    - Amount must be positive
    - Transaction date cannot be in the future
    - Account must have sufficient balance for expenses
    - User can only select their own accounts and categories

    Attributes:
        user: The authenticated user (passed via __init__)
        balance_warning: Optional warning message about low balance

    Security:
        - Filters accounts and categories by user
        - Validates user ownership in clean() method
        - Prevents cross-user data access
    '''

    installments = forms.IntegerField(
        required=False,
        min_value=1,
        initial=1,
        label='Quantidade de Meses',
        help_text='Para gastos recorrentes, informe por quantos meses deseja lançar esta transação.'
    )

    def __init__(self, *args, user=None, **kwargs):
        '''
        Initialize form with user-specific querysets and widget styling.

        Args:
            user: The authenticated user (required for filtering)
            *args: Positional arguments passed to ModelForm
            **kwargs: Keyword arguments passed to ModelForm

        Note:
            When editing, stores original instance to calculate available
            balance correctly (considering the reversal of old transaction).
        '''
        self.user = user
        super().__init__(*args, **kwargs)
        self._original_instance = None

        # Hide installments field when editing
        if self.instance.pk:
            self.fields.pop('installments', None)

        if self.instance.pk:
            try:
                self._original_instance = Transaction.objects.select_related(
                    'account'
                ).get(pk=self.instance.pk)
            except Transaction.DoesNotExist:
                self._original_instance = None

        if self.user:
            self.fields['account'].queryset = Account.objects.filter(
                user=self.user
            ).order_by('name')

            # Set initial account to the most used one if creating a new transaction
            if not self.instance.pk:
                most_used_account = Account.objects.filter(
                    user=self.user
                ).annotate(
                    transaction_count=Count('transactions')
                ).order_by('-transaction_count').first()

                if most_used_account:
                    self.fields['account'].initial = most_used_account

            self.fields['category'].queryset = Category.objects.filter(
                user=self.user
            ).order_by('name')

        self.fields['account'].widget.attrs.update({
            'class': 'form-select w-full px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition duration-200',
        })
        self.fields['category'].widget.attrs.update({
            'class': 'form-select w-full px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition duration-200',
        })
        self.fields['transaction_type'].widget.attrs.update({
            'class': 'form-select w-full px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition duration-200',
        })
        self.fields['amount'].widget = forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition duration-200',
            'placeholder': '0,00',
            'inputmode': 'numeric',
        })
        self.fields['transaction_date'].widget = forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition duration-200',
        })
        self.fields['description'].widget = forms.Textarea(attrs={
            'rows': 3,
            'class': 'w-full px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition duration-200',
            'placeholder': 'Descreva esta transação',
        })

        if 'installments' in self.fields:
            self.fields['installments'].widget.attrs.update({
                'class': 'w-full px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition duration-200',
                'placeholder': '1',
            })

        if not self.instance.pk:
            self.fields['transaction_date'].initial = date.today().isoformat()
            self.fields['transaction_type'].initial = Transaction.TransactionType.EXPENSE

    class Meta:
        model = Transaction
        fields = [
            'account',
            'category',
            'transaction_type',
            'amount',
            'transaction_date',
            'description',
        ]
        labels = {
            'account': 'Conta',
            'category': 'Categoria',
            'transaction_type': 'Tipo de Transação',
            'amount': 'Valor',
            'transaction_date': 'Data',
            'description': 'Descrição',
        }

    def clean_amount(self):
        '''
        Validate that transaction amount is positive.

        Returns:
            Decimal: The validated amount

        Raises:
            ValidationError: If amount is zero or negative
        '''
        amount = self.cleaned_data.get('amount')
        if amount is not None and amount <= 0:
            raise forms.ValidationError('O valor da transação deve ser positivo.')
        return amount

    def clean_transaction_date(self):
        '''
        Return the transaction date. Future date validation is handled in clean()
        to support recurring transactions.

        Returns:
            date: The transaction date
        '''
        return self.cleaned_data.get('transaction_date')

    def clean(self):
        '''
        Perform cross-field validation and security checks.

        Validations:
        1. User ownership: Account and category must belong to authenticated user
        2. Category match: Category type must match transaction type
        3. Balance check: For expenses, ensure account has sufficient funds

        Returns:
            dict: Cleaned data dictionary

        Raises:
            ValidationError: For any validation failures (added to specific fields)

        Note:
            Sets self.balance_warning if balance is low but transaction is allowed.
        '''
        cleaned_data = super().clean()
        category = cleaned_data.get('category')
        transaction_type = cleaned_data.get('transaction_type')
        account = cleaned_data.get('account')
        amount = cleaned_data.get('amount')

        if account and self.user and account.user_id != self.user.id:
            self.add_error('account', 'Selecione uma conta válida.')

        if category and self.user and category.user_id != self.user.id:
            self.add_error('category', 'Selecione uma categoria válida.')

        if category and transaction_type:
            is_expense_type = transaction_type in Transaction.get_expense_types()
            if is_expense_type and category.category_type != Category.CategoryType.EXPENSE:
                self.add_error(
                    'category',
                    'A categoria selecionada deve ser do tipo Saída para esta transação.',
                )
            elif transaction_type == Transaction.TransactionType.INCOME and category.category_type != Category.CategoryType.INCOME:
                self.add_error(
                    'category',
                    'A categoria selecionada deve ser do tipo Entrada para esta transação.',
                )

        # Validate future date
        transaction_date = cleaned_data.get('transaction_date')
        installments = cleaned_data.get('installments', 1) or 1
        if installments == 1 and transaction_date and transaction_date > date.today():
            self.add_error(
                'transaction_date',
                'A data da transação não pode ser no futuro.',
            )

        self.balance_warning = None
        is_expense_type = transaction_type in Transaction.get_expense_types()
        if (
            is_expense_type
            and account
            and amount
        ):
            available_balance = self._get_available_balance(account)
            if available_balance < amount:
                self.add_error(
                    'amount',
                    'Saldo insuficiente na conta selecionada para esta transação.',
                )

        return cleaned_data

    def _get_available_balance(self, account):
        '''
        Calculate available balance considering pending transaction updates.

        When editing an existing transaction, the current account balance
        includes the old transaction's effect. This method calculates what
        the balance would be if we first reverse the old transaction.

        Args:
            account: The Account instance

        Returns:
            Decimal: Available balance for validation

        Example:
            # Current balance: R$ 1000 (includes old expense of R$ 300)
            # Changing expense from R$ 300 to R$ 500
            # Available: R$ 1000 - (-300) = R$ 1300
            # New expense R$ 500 is valid (< R$ 1300)
        '''
        available_balance = account.balance

        # When editing, account for reversal of old transaction
        if (
            self._original_instance
            and self._original_instance.account_id == account.id
        ):
            previous_delta = self._calculate_delta(
                self._original_instance.amount,
                self._original_instance.transaction_type,
            )
            # Reverse the old transaction effect to get true available balance
            available_balance = account.balance - previous_delta

        return available_balance

    @staticmethod
    def _calculate_delta(amount, transaction_type):
        '''
        Calculate transaction's effect on account balance.

        INCOME transactions add to balance (positive delta).
        Expense-like transactions subtract from balance (negative delta).

        Args:
            amount: Transaction amount (Decimal, always positive)
            transaction_type: Transaction.TransactionType choices

        Returns:
            Decimal: Positive for INCOME, negative for others

        Example:
            >>> _calculate_delta(Decimal('100'), 'INCOME')
            Decimal('100')
            >>> _calculate_delta(Decimal('100'), 'EXPENSE')
            Decimal('-100')
        '''
        if transaction_type == Transaction.TransactionType.INCOME:
            return amount
        return amount * Decimal('-1')
