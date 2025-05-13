# apps/detector/signals.py
from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import DetectionRecord

@receiver(post_delete, sender=DetectionRecord)
def auto_delete_s3_files(sender, instance, **kwargs):
    # 直接呼叫 Django field 的 delete()，觸發 storage（S3）刪除
    instance.original_image.delete(save=False)
    instance.annotated_image.delete(save=False)
