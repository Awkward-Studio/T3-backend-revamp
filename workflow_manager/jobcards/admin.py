from django.contrib import admin
from .models import JobCard, JobCardCounter, CurrentPart, CurrentLabour

# Register your models here.
admin.site.register(JobCard)
admin.site.register(JobCardCounter)
admin.site.register(CurrentPart)
admin.site.register(CurrentLabour)
