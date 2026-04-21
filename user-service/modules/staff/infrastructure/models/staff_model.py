from django.db import models

class StaffModel(models.Model):
    name       = models.CharField(max_length=255)
    email      = models.EmailField(unique=True)
    department = models.CharField(max_length=100, default='Catalog')

    class Meta:
        db_table  = 'staffs'
        app_label = 'staff_infrastructure_models'
