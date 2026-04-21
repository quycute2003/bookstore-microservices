from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='ProductModel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('product_type', models.CharField(
                    choices=[('book', 'Sách'), ('cloth', 'Thời trang')],
                    db_index=True, max_length=20
                )),
                ('price', models.DecimalField(decimal_places=2, max_digits=15)),
                ('stock', models.IntegerField(default=0)),
                ('category_id', models.IntegerField(blank=True, db_index=True, null=True)),
                ('image_url', models.URLField(blank=True, max_length=1000, null=True)),
                ('attributes', models.JSONField(default=dict)),
            ],
            options={'db_table': 'products', 'ordering': ['id']},
        ),
    ]
