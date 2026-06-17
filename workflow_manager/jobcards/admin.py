from django.contrib import admin
from .models import (
    ApprovalItem,
    CustomerApproval,
    JobCard,
    JobCardCounter,
    CurrentPart,
    CurrentLabour,
)

# Register your models here.
admin.site.register(JobCard)
admin.site.register(JobCardCounter)
admin.site.register(CurrentPart)
admin.site.register(CurrentLabour)
admin.site.register(CustomerApproval)
admin.site.register(ApprovalItem)
