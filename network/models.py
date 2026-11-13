import math

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.conf import settings


NODE_TYPES = [("pq", "PQ"), ("pu", "PU"), ("slack", "Балансирующий")]
BRANCH_KINDS = [("line", "Линия"), ("t2", "Трансформатор 2О"), ("t3", "Трансформатор 3О")]


class Project(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name="projects", verbose_name="Владелец")
    name = models.CharField("Название", max_length=200)
    description = models.TextField("Описание", blank=True)
    accuracy = models.FloatField("Точность, МВА", default=1e-3, validators=[MinValueValidator(1e-9)])
    max_iterations = models.PositiveIntegerField("Макс. итераций", default=100)
    damping = models.FloatField("Демпфирование (0…1]", default=1.0,
                                validators=[MinValueValidator(1e-6), MaxValueValidator(1.0)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Проект"
        verbose_name_plural = "Проекты"
        constraints = [models.UniqueConstraint(fields=["owner", "name"], name="uniq_project_per_owner")]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("project_detail", args=[self.pk])


class Load(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="loads")
    load_name = models.CharField("Имя", max_length=100)
    p_0 = models.FloatField("P₀, МВт", default=0)
    q_0 = models.FloatField("Q₀, Мвар", default=0)
    z_p = models.FloatField("Z_p", default=0)
    i_p = models.FloatField("I_p", default=0)
    p_p = models.FloatField("P_p", default=1)
    z_q = models.FloatField("Z_q", default=0)
    i_q = models.FloatField("I_q", default=0)
    p_q = models.FloatField("P_q", default=1)
    u_0 = models.FloatField("U₀, кВ", default=110)

    class Meta:
        verbose_name = "Нагрузка"; verbose_name_plural = "Нагрузки"
        constraints = [models.UniqueConstraint(fields=["project", "load_name"], name="uniq_load_per_project")]

    def __str__(self):
        return self.load_name


class Node(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="nodes")
    node_name = models.CharField("Имя", max_length=100)
    type_node = models.CharField("Тип узла", max_length=5, choices=NODE_TYPES, default="pq")
    u_base = models.FloatField("U баз, кВ", default=110)
    g_shunt = models.FloatField("G шунта, См", default=0)
    b_shunt = models.FloatField("B шунта, См", default=0)
    u_magnitude = models.FloatField("U нач, кВ", default=110)
    u_angle = models.FloatField("δ нач, рад", default=0,
                                validators=[MinValueValidator(0), MaxValueValidator(2 * math.pi)])
    p_gen = models.FloatField("P ген, МВт", default=0)
    q_gen = models.FloatField("Q ген, Мвар", default=0)
    q_min = models.FloatField("Q min, Мвар", default=0)
    q_max = models.FloatField("Q max, Мвар", default=0)
    u_setpoint = models.FloatField("Уставка U (PU/Slack), кВ", null=True, blank=True)
    loads = models.ManyToManyField(Load, blank=True, related_name="nodes", verbose_name="Нагрузки")

    class Meta:
        verbose_name = "Узел"; verbose_name_plural = "Узлы"
        constraints = [models.UniqueConstraint(fields=["project", "node_name"], name="uniq_node_per_project")]

    def __str__(self):
        return self.node_name


class Branch(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="branches")
    branch_name = models.CharField("Имя", max_length=100)
    kind = models.CharField("Тип ветви", max_length=4, choices=BRANCH_KINDS, default="line")
    node_1 = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="+", verbose_name="Узел 1")
    node_2 = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="+", verbose_name="Узел 2")
    node_3 = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="+",
                               null=True, blank=True, verbose_name="Узел 3 (только 3О)")
    r_1 = models.FloatField("R₁, Ом", default=0)
    x_1 = models.FloatField("X₁, Ом", default=0)
    g_shunt = models.FloatField("G шунта, См", default=0)
    b_shunt = models.FloatField("B шунта, См", default=0)
    u_1 = models.FloatField("U₁, кВ", null=True, blank=True)
    u_2 = models.FloatField("U₂, кВ", null=True, blank=True)
    u_3 = models.FloatField("U₃, кВ", null=True, blank=True)
    r_2 = models.FloatField("R₂, Ом", null=True, blank=True)
    x_2 = models.FloatField("X₂, Ом", null=True, blank=True)
    r_3 = models.FloatField("R₃, Ом", null=True, blank=True)
    x_3 = models.FloatField("X₃, Ом", null=True, blank=True)

    class Meta:
        verbose_name = "Ветвь"; verbose_name_plural = "Ветви"
        constraints = [models.UniqueConstraint(fields=["project", "branch_name"], name="uniq_branch_per_project")]

    def __str__(self):
        return self.branch_name


class CalculationRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "В очереди"
        RUNNING = "running", "Выполняется"
        SUCCESS = "success", "Завершен"
        FAILED = "failed", "Ошибка"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="runs")
    created_at = models.DateTimeField("Время", auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    message = models.TextField("Сообщение", blank=True)
    results = models.JSONField("Результаты", default=dict, blank=True)

    class Meta:
        verbose_name = "Расчет"; verbose_name_plural = "Расчеты"
        ordering = ["-created_at"]

    @property
    def success(self):          # совместимость со старыми шаблонами
        return self.status == self.Status.SUCCESS

    @property
    def in_progress(self):
        return self.status in (self.Status.PENDING, self.Status.RUNNING)
