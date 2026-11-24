from django.db import models

NODE_TYPES = [("pq", "PQ"), ("pu", "PU"), ("slack", "Slack")]
BRANCH_KINDS = [("line", "Линия"), ("t2", "Трансформатор 2-обм."), ("t3", "Трансформатор 3-обм.")]


class NetworkCase(models.Model):
    """Схема сети: группирует нагрузки, узлы, ветви, параметры и расчёты."""
    name = models.CharField(max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class CalculationParameters(models.Model):
    case = models.OneToOneField(NetworkCase, on_delete=models.CASCADE, related_name="parameters")
    accuracy = models.FloatField(default=0.01)
    max_iterations = models.PositiveIntegerField(default=100)
    damping = models.FloatField(default=1.0)


class Load(models.Model):
    case = models.ForeignKey(NetworkCase, on_delete=models.CASCADE, related_name="loads")
    load_name = models.CharField(max_length=100)
    p_0 = models.FloatField()
    q_0 = models.FloatField()
    z_p = models.FloatField(default=0)
    i_p = models.FloatField(default=0)
    p_p = models.FloatField(default=1)
    z_q = models.FloatField(default=0)
    i_q = models.FloatField(default=0)
    p_q = models.FloatField(default=1)
    u_0 = models.FloatField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["case", "load_name"], name="uniq_load_name")]


class Node(models.Model):
    case = models.ForeignKey(NetworkCase, on_delete=models.CASCADE, related_name="nodes")
    node_name = models.CharField(max_length=100)
    type_node = models.CharField(max_length=5, choices=NODE_TYPES, default="pq")
    type_node_current = models.CharField(max_length=5, choices=NODE_TYPES, default="pq")
    u_base = models.FloatField()
    g_shunt = models.FloatField(default=0)
    b_shunt = models.FloatField(default=0)
    u_magnitude = models.FloatField()
    u_angle = models.FloatField(default=0)  # радианы, как в src/model/node.py
    u_setpoint = models.FloatField(null=True, blank=True)
    p_gen = models.FloatField(default=0)
    q_gen = models.FloatField(default=0)
    q_min = models.FloatField(default=0)
    q_max = models.FloatField(default=0)
    loads = models.ManyToManyField(Load, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["case", "node_name"], name="uniq_node_name")]


class Branch(models.Model):
    """Одна таблица для line/t2/t3; лишние поля kind хранятся как NULL."""
    case = models.ForeignKey(NetworkCase, on_delete=models.CASCADE, related_name="branches")
    kind = models.CharField(max_length=4, choices=BRANCH_KINDS, default="line")
    branch_name = models.CharField(max_length=100)
    node_1 = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="+")
    node_2 = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="+")
    node_3 = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="+", null=True, blank=True)
    r_1 = models.FloatField()
    x_1 = models.FloatField()
    g_shunt = models.FloatField(default=0)
    b_shunt = models.FloatField(default=0)
    u_1 = models.FloatField(null=True, blank=True)
    u_2 = models.FloatField(null=True, blank=True)
    r_2 = models.FloatField(null=True, blank=True)
    x_2 = models.FloatField(null=True, blank=True)
    r_3 = models.FloatField(null=True, blank=True)
    x_3 = models.FloatField(null=True, blank=True)
    u_3 = models.FloatField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["case", "branch_name"], name="uniq_branch_name")]


class CalculationRun(models.Model):
    """Снимок результата расчёта; исходные данные схемы не изменяются."""
    case = models.ForeignKey(NetworkCase, on_delete=models.CASCADE, related_name="runs")
    created_at = models.DateTimeField(auto_now_add=True)
    converged = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    total_dp = models.FloatField(null=True, blank=True)
    total_dq = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class NodeResult(models.Model):
    run = models.ForeignKey(CalculationRun, on_delete=models.CASCADE, related_name="node_results")
    node_name = models.CharField(max_length=100)
    type_node_current = models.CharField(max_length=5)
    u_magnitude = models.FloatField()
    u_angle = models.FloatField()
    q_gen = models.FloatField()


class SlackPowerResult(models.Model):
    run = models.ForeignKey(CalculationRun, on_delete=models.CASCADE, related_name="slack_powers")
    node_name = models.CharField(max_length=100)
    p = models.FloatField()
    q = models.FloatField()


class BranchFlowResult(models.Model):
    run = models.ForeignKey(CalculationRun, on_delete=models.CASCADE, related_name="branch_flows")
    branch_name = models.CharField(max_length=100)
    p_1 = models.FloatField()
    q_1 = models.FloatField()
    p_2 = models.FloatField()
    q_2 = models.FloatField()
    p_3 = models.FloatField(null=True, blank=True)
    q_3 = models.FloatField(null=True, blank=True)
    dp = models.FloatField()
    dq = models.FloatField()
