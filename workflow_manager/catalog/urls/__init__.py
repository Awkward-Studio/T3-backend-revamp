from .insurers_urls import urlpatterns as insurers_urlpatterns
from .labour_urls import urlpatterns as labour_urlpatterns
from .vehicle_models_urls import urlpatterns as vehicle_models_urlpatterns

# Re-export a single `urlpatterns` list so Django can `include("catalog.urls")`.
urlpatterns = insurers_urlpatterns + labour_urlpatterns + vehicle_models_urlpatterns

