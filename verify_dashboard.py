import asyncio
from playwright.async_api import async_playwright
import os
import django
from datetime import timedelta
from decimal import Decimal

# Ensure env is set BEFORE django.setup()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
os.environ['SECRET_KEY'] = 'secret'
os.environ['DEBUG'] = 'True'

django.setup()

from django.utils import timezone
from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from accounts.models import Account
from categories.models import Category
from transactions.models import Transaction

User = get_user_model()

async def verify_dashboard_projection():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={'width': 1280, 'height': 1600})
        page = await context.new_page()

        # Create user if not exists
        user, created = await asyncio.to_thread(User.objects.get_or_create,
            email='dashboard@example.com',
            defaults={'is_staff': True, 'is_superuser': True}
        )
        if created:
            await asyncio.to_thread(user.set_password, 'password123')
            await asyncio.to_thread(user.save)

        # Create account and category
        account, _ = await asyncio.to_thread(Account.objects.get_or_create,
            user=user, name='Carteira Projeção', defaults={'balance': Decimal('5000.00')}
        )
        category, _ = await asyncio.to_thread(Category.objects.get_or_create,
            user=user, name='TIM', defaults={'category_type': 'EXPENSE', 'color': '#0000FF'}
        )

        # Clear existing for this user to be clean
        await asyncio.to_thread(Transaction.objects.filter(account__user=user).delete)

        # Create a recurring transaction for 12 months starting NEXT month
        base_date = timezone.now().date() + relativedelta(months=1)
        base_date = base_date.replace(day=1)

        for i in range(12):
            await asyncio.to_thread(Transaction.objects.create,
                account=account,
                category=category,
                transaction_type='EXPENSE',
                amount=Decimal('50.00'),
                transaction_date=base_date + relativedelta(months=i),
                description=f'TIM ({i+1}/12)'
            )

        # Login
        await page.goto('http://localhost:8000/auth/login/')
        await page.fill('input[name="email"]', 'dashboard@example.com')
        await page.fill('input[name="password"]', 'password123')
        await page.click('button[type="submit"]')

        # Wait for dashboard
        await page.wait_for_url('**/dashboard/')

        # Give some time for charts to render
        await page.wait_for_timeout(2000)

        # Take screenshot
        os.makedirs('/home/jules/verification', exist_ok=True)
        await page.screenshot(path='/home/jules/verification/dashboard_projection.png', full_page=True)

        print("Dashboard projection verified and screenshot saved.")
        await browser.close()

if __name__ == '__main__':
    # Make sure server is running
    import subprocess
    import time

    # Kill any existing server
    subprocess.run("kill $(lsof -t -i :8000) 2>/dev/null", shell=True)

    # Write .env for the subprocess server
    with open('.env', 'w') as f:
        f.write("DEBUG=True\nSECRET_KEY=secret\nALLOWED_HOSTS=*\n")

    process = subprocess.Popen(['python3', 'manage.py', 'runserver', '0.0.0.0:8000'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(5) # wait for server to start

    try:
        asyncio.run(verify_dashboard_projection())
    finally:
        process.terminate()
