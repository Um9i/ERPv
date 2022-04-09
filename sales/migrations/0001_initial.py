# Generated by Django 4.0.3 on 2022-04-09 09:01

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('inventory', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Customer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=256, unique=True)),
                ('address', models.TextField(blank=True)),
                ('phone', models.CharField(blank=True, max_length=64)),
                ('email', models.CharField(blank=True, max_length=128)),
                ('website', models.CharField(blank=True, max_length=256)),
            ],
            options={
                'verbose_name_plural': 'Customer Management',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='CustomerProduct',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='customer_products', to='sales.customer')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='product_customers', to='inventory.product')),
            ],
            options={
                'ordering': ['product__name'],
            },
        ),
        migrations.CreateModel(
            name='SalesOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='customer_sales_orders', to='sales.customer')),
            ],
            options={
                'verbose_name_plural': 'Sales Orders',
                'ordering': ['-pk'],
            },
        ),
        migrations.CreateModel(
            name='SalesOrderLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveBigIntegerField()),
                ('complete', models.BooleanField(default=False)),
                ('closed', models.BooleanField(default=False)),
                ('value', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='product_sales_orders', to='sales.customerproduct')),
                ('sales_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sales_order_lines', to='sales.salesorder')),
            ],
            options={
                'ordering': ['product'],
            },
        ),
        migrations.CreateModel(
            name='SalesLedger',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.BigIntegerField()),
                ('customer', models.CharField(max_length=256)),
                ('value', models.DecimalField(decimal_places=2, max_digits=10)),
                ('date', models.DateTimeField(auto_now_add=True)),
                ('transaction_id', models.PositiveBigIntegerField()),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sales_ledger', to='inventory.product')),
            ],
            options={
                'verbose_name_plural': 'Sales Ledger',
                'ordering': ['-date'],
            },
        ),
        migrations.CreateModel(
            name='CustomerContact',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128)),
                ('address', models.TextField(blank=True)),
                ('phone', models.CharField(blank=True, max_length=64)),
                ('email', models.CharField(blank=True, max_length=128)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='customer_contacts', to='sales.customer')),
            ],
            options={
                'verbose_name_plural': 'Customer Contacts',
                'ordering': ['name'],
            },
        ),
    ]