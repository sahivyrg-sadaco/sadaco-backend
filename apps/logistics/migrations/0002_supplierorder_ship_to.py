from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='supplierorder',
            name='ship_to',
            field=models.TextField(blank=True),
        ),
    ]
