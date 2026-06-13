import django_filters
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db.models import Q

from .models import Event


class EventFilter(django_filters.FilterSet):
    location = django_filters.CharFilter(field_name="location", lookup_expr="icontains")
    language = django_filters.CharFilter(field_name="language", lookup_expr="iexact")
    starts_after = django_filters.IsoDateTimeFilter(field_name="starts_at", lookup_expr="gte")
    starts_before = django_filters.IsoDateTimeFilter(field_name="starts_at", lookup_expr="lte")
    q = django_filters.CharFilter(method="filter_q")

    class Meta:
        model = Event
        fields = ["location", "language", "starts_after", "starts_before", "q"]

    def filter_q(self, queryset, name, value):
        """Full-text search on title/description (GIN-indexed), OR'd with icontains
        so partial tokens ("yog" -> "yoga") still match. FTS handles stemming and
        multi-word queries; icontains covers prefixes the stemmer would miss."""
        search = SearchQuery(value, config="english")
        return queryset.annotate(fts=SearchVector("title", "description", config="english")).filter(
            Q(fts=search) | Q(title__icontains=value) | Q(description__icontains=value)
        )
