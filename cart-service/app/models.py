from django.db import models

class Cart(models.Model):
    customer_id = models.IntegerField()

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE)
    book_id = models.IntegerField()
    item_type = models.CharField(max_length=50, default='book')
    quantity = models.IntegerField()