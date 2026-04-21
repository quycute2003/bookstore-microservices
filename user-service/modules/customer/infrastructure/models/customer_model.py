from django.db import models

class CustomerModel(models.Model):
    name  = models.CharField(max_length=255)
    email = models.EmailField(unique=True)

    class Meta:
        db_table = 'customers'
        app_label = 'customer_infrastructure_models'
