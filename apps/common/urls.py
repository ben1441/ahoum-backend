from django.http import JsonResponse
from django.urls import path


def healthz(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [path("", healthz, name="healthz")]
