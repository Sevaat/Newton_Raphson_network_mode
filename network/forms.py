import math

from django import forms
from django.core.exceptions import ValidationError

from network.models import Branch, Load, Node, Project




class BootstrapMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            w = field.widget
            if isinstance(w, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                continue
            w.attrs["class"] = "form-select" if isinstance(w, forms.Select) else "form-control"


class ProjectForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description", "accuracy", "max_iterations", "damping"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}


class LoadForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Load
        exclude = ["project"]

    def clean(self):
        cd = super().clean()
        for keys in (("z_p", "i_p", "p_p"), ("z_q", "i_q", "p_q")):
            vals = [cd.get(k) for k in keys]
            if all(v is not None for v in vals) and not math.isclose(sum(vals), 1.0, abs_tol=1e-6):
                raise ValidationError(f"ZIP-коэффициенты {' + '.join(keys)} должны давать в сумме 1")
        return cd


class NodeForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Node
        exclude = ["project"]
        widgets = {"loads": forms.CheckboxSelectMultiple}

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project is not None:   # нагрузки только текущего проекта
            self.fields["loads"].queryset = Load.objects.filter(project=project)

    def clean(self):
        cd = super().clean()
        qmin, qmax = cd.get("q_min"), cd.get("q_max")
        if qmin is not None and qmax is not None and qmin > qmax:
            raise ValidationError("q_min не может быть больше q_max")
        return cd


class BranchForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Branch
        exclude = ["project"]

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project is not None:   # узлы только текущего проекта
            qs = Node.objects.filter(project=project)
            for f in ("node_1", "node_2", "node_3"):
                self.fields[f].queryset = qs

    def clean(self):
        cd = super().clean()
        kind = cd.get("kind")
        n1, n2, n3 = cd.get("node_1"), cd.get("node_2"), cd.get("node_3")
        if n1 and n2 and n1.pk == n2.pk:
            raise ValidationError("Узлы начала и конца ветви должны различаться")
        if not cd.get("r_1") and not cd.get("x_1"):
            raise ValidationError("R₁ и X₁ не могут быть одновременно равны нулю")
        if kind in ("t2", "t3"):
            for f in ("u_1", "u_2"):
                if cd.get(f) is None:
                    self.add_error(f, "Обязательно для трансформатора")
        if kind == "t3":
            if n3 is None:
                self.add_error("node_3", "Обязательно для 3-обмоточного трансформатора")
            elif n1 and n2 and n3.pk in (n1.pk, n2.pk):
                self.add_error("node_3", "Узлы трансформатора должны различаться")
            for f in ("r_2", "x_2", "r_3", "x_3", "u_3"):
                if cd.get(f) is None:
                    self.add_error(f, "Обязательно для 3-обмоточного трансформатора")
        return cd


class ImportForm(BootstrapMixin, forms.Form):
    name = forms.CharField(label="Название проекта", max_length=200)
    file = forms.FileField(label="Файл JSON")

from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

class StyledLoginForm(BootstrapMixin, AuthenticationForm):
    pass

class StyledUserCreationForm(BootstrapMixin, UserCreationForm):
    pass
