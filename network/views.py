import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from network.forms import (BranchForm, ImportForm, LoadForm, NodeForm, ProjectForm,
                           StyledUserCreationForm)
from network.mixins import OwnerMixin
from network.models import Branch, CalculationRun, Load, Node, Project
from network.services.adapter import project_from_dict, project_to_dict
from network.tasks import run_calculation_task

CRUD = {"load": (Load, LoadForm), "node": (Node, NodeForm), "branch": (Branch, BranchForm)}


class SignupView(CreateView):
    form_class = StyledUserCreationForm
    template_name = "registration/auth_form.html"
    success_url = reverse_lazy("login")
    extra_context = {"title": "Регистрация", "is_login": False}


class ProjectListView(OwnerMixin, ListView):
    model = Project
    template_name = "network/project_list.html"
    context_object_name = "projects"


class ProjectCreateView(LoginRequiredMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = "network/form.html"
    extra_context = {"title": "Новый проект"}

    def form_valid(self, form):
        form.instance.owner = self.request.user   # владельца нельзя подделать через POST
        return super().form_valid(form)


class ProjectDetailView(OwnerMixin, DetailView):
    model = Project
    template_name = "network/project_detail.html"
    context_object_name = "project"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        p = self.object
        ctx.update(
            nodes=p.nodes.prefetch_related("loads"),
            branches=p.branches.select_related("node_1", "node_2", "node_3"),
            loads=p.loads.all(),
            runs=p.runs.all()[:10],
        )
        return ctx


class ProjectUpdateView(OwnerMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = "network/form.html"
    extra_context = {"title": "Параметры проекта"}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["project"] = self.object
        return ctx


class ProjectDeleteView(OwnerMixin, DeleteView):
    model = Project
    success_url = reverse_lazy("project_list")
    template_name = "network/project_confirm_delete.html"


def _get_project(request, pk):
    return get_object_or_404(Project, pk=pk, owner=request.user)


def _crud(kind):
    if kind not in CRUD:
        raise Http404
    return CRUD[kind]


@login_required
def item_create(request, pk, kind):
    project = _get_project(request, pk)
    model, form_class = _crud(kind)
    kw = {"project": project} if kind in ("node", "branch") else {}
    form = form_class(request.POST or None, **kw)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.project = project
        obj.save()
        form.save_m2m()
        return redirect(project)
    return render(request, "network/form.html", {
        "form": form, "project": project,
        "title": f"{project.name}: добавить ({model._meta.verbose_name})"})


@login_required
def item_edit(request, pk, kind, item_pk):
    project = _get_project(request, pk)
    model, form_class = _crud(kind)
    obj = get_object_or_404(model, pk=item_pk, project=project)
    kw = {"project": project} if kind in ("node", "branch") else {}
    form = form_class(request.POST or None, instance=obj, **kw)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect(project)
    return render(request, "network/form.html",
                  {"form": form, "project": project, "title": f"{project.name}: {obj}"})


@login_required
@require_POST
def item_delete(request, pk, kind, item_pk):
    project = _get_project(request, pk)
    model, _ = _crud(kind)
    get_object_or_404(model, pk=item_pk, project=project).delete()
    return redirect(project)


@login_required
@require_POST
def project_run(request, pk):
    project = _get_project(request, pk)
    if project.runs.filter(status__in=[CalculationRun.Status.PENDING,
                                       CalculationRun.Status.RUNNING]).exists():
        messages.warning(request, "Расчет уже выполняется — дождитесь завершения")
        return redirect("project_detail", pk=project.pk)
    run = CalculationRun.objects.create(project=project, status=CalculationRun.Status.PENDING)
    # задачу отправляем только после коммита транзакции, иначе воркер может не увидеть строку
    transaction.on_commit(lambda: run_calculation_task.delay(run.pk))
    messages.info(request, "Расчет поставлен в очередь")
    return redirect("run_detail", pk=project.pk, run_pk=run.pk)


@login_required
def run_detail(request, pk, run_pk):
    project = _get_project(request, pk)
    run = get_object_or_404(CalculationRun, pk=run_pk, project=project)
    return render(request, "network/results.html", {"project": project, "run": run})


@login_required
def run_status(request, pk, run_pk):
    """JSON-статус для опроса страницы (AJAX), если не устраивает meta-refresh."""
    project = _get_project(request, pk)
    run = get_object_or_404(CalculationRun, pk=run_pk, project=project)
    return JsonResponse({"status": run.status, "message": run.message})


@login_required
def project_export(request, pk):
    project = _get_project(request, pk)
    response = JsonResponse(project_to_dict(project),
                            json_dumps_params={"ensure_ascii": False, "indent": 2})
    response["Content-Disposition"] = f'attachment; filename="project_{project.pk}.json"'
    return response


@login_required
def project_import(request):
    form = ImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            data = json.load(form.cleaned_data["file"])
            project = project_from_dict(data, form.cleaned_data["name"], owner=request.user)
        except (ValueError, KeyError, TypeError) as e:
            form.add_error(None, f"Ошибка импорта: {e}")
        else:
            messages.success(request, "Проект импортирован")
            return redirect(project)
    return render(request, "network/form.html", {"form": form, "title": "Импорт проекта из JSON"})
