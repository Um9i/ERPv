# Generated by Django 3.1.4 on 2021-01-01 16:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0002_locationquantity'),
    ]

    operations = [
        migrations.AlterField(
            model_name='locationquantity',
            name='quantity',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
