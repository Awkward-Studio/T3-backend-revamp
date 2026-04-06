import django_filters
from .models import Product


class ProductFilter(django_filters.FilterSet):
    """
    Filter class for Product model to handle:
    - Price range
    - Category match
    - Name search
    - Date range filtering
    - Exact date filtering
    """

    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    category = django_filters.CharFilter(field_name="category", lookup_expr="icontains")
    name = django_filters.CharFilter(field_name="name", lookup_expr="icontains")
    created_on = django_filters.DateFilter(
        field_name="created_at", lookup_expr="date"
    )  # Exact date
    created_after = django_filters.DateFilter(
        field_name="created_at", lookup_expr="gte"
    )  # Date range (after)
    created_before = django_filters.DateFilter(
        field_name="created_at", lookup_expr="lte"
    )  # Date range (before)

    class Meta:
        model = Product
        fields = [
            "min_price",
            "max_price",
            "category",
            "name",
            "created_on",
            "created_after",
            "created_before",
        ]
