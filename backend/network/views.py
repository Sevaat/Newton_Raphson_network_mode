import json
from pathlib import Path
from urllib.parse import quote

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from pydantic import ValidationError
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import models, services

DATA_ERRORS = (ValidationError, KeyError, TypeError, ValueError)


def _error(e):
    return Response({"detail": str(e)}, status=400)


@api_view(["GET", "POST"])
def cases(request):
    if request.method == "GET":
        return Response([
            {"id": c.id, "name": c.name, "created_at": c.created_at, "runs_count": c.runs.count()}
            for c in models.NetworkCase.objects.order_by("-updated_at")
        ])
    name = (request.data.get("name") or "").strip()
    if not name:
        return Response({"detail": "Укажите название схемы"}, status=400)
    if models.NetworkCase.objects.filter(name=name).exists():
        return Response({"detail": f"Схема '{name}' уже существует"}, status=400)
    case = models.NetworkCase.objects.create(name=name)
    models.CalculationParameters.objects.create(case=case)
    return Response({"id": case.id, "name": case.name}, status=201)


@api_view(["GET", "PUT", "DELETE"])
def case_detail(request, pk):
    case = get_object_or_404(models.NetworkCase, pk=pk)
    if request.method == "GET":
        return Response(services.case_detail(case))
    if request.method == "DELETE":
        case.delete()
        return Response(status=204)
    try:
        name = (request.data.get("name") or case.name).strip()
        if models.NetworkCase.objects.exclude(pk=pk).filter(name=name).exists():
            return Response({"detail": f"Схема '{name}' уже существует"}, status=400)
        services.save_data(case, request.data.get("data") or {})
        case.name = name
        case.save()
        return Response(services.case_detail(case))
    except DATA_ERRORS as e:
        return _error(e)


@api_view(["POST"])
def import_case(request):
    try:
        if "file" in request.FILES:
            file = request.FILES["file"]
            data = json.loads(file.read().decode("utf-8-sig"))
            name = request.data.get("name") or Path(file.name).stem
        else:
            data = request.data.get("data", request.data)
            name = request.data.get("name") or f"Импорт {timezone.localtime():%Y-%m-%d %H-%M-%S}"
        case = services.import_case(name, data)
        return Response({"id": case.id, "name": case.name}, status=201)
    except DATA_ERRORS as e:
        return _error(e)


@api_view(["GET"])
def export_case(request, pk):
    case = get_object_or_404(models.NetworkCase, pk=pk)
    run = None
    if request.query_params.get("run"):
        run = get_object_or_404(models.CalculationRun, pk=request.query_params["run"], case=case)
        if not run.converged:
            return Response({"detail": "Расчёт не сошёлся — экспорт результатов недоступен"}, status=400)
    try:
        data = services.export_data(case, run)
    except DATA_ERRORS as e:
        return _error(e)
    filename = quote(f"{case.name}{'_result' if run else ''}.json")
    response = HttpResponse(json.dumps(data, ensure_ascii=False, indent=2),
                            content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{filename}"
    return response


@api_view(["POST"])
def calculate(request, pk):
    case = get_object_or_404(models.NetworkCase, pk=pk)
    try:
        run = services.run_calculation(case)
    except DATA_ERRORS as e:
        return _error(e)
    return Response(services.run_detail(run))


@api_view(["GET"])
def run_detail(request, pk):
    return Response(services.run_detail(get_object_or_404(models.CalculationRun, pk=pk)))
