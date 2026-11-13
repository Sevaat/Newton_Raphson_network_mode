import logging
import math

from celery.exceptions import SoftTimeLimitExceeded
from django.utils import timezone

from src.nr_method import ConvergenceError, NewtonRaphsonMethod
from src.postprocessing import calc_results
from src.util.file_manager import FileManager

from network.models import CalculationRun
from network.services.adapter import project_to_dict

logger = logging.getLogger(__name__)


def compute_results(project) -> dict:
    """Чистое вычисление режима — исполняется в воркере Celery."""
    loads, nodes, branches, params = FileManager.load_from_dict(project_to_dict(project))
    nodes, branches, params = NewtonRaphsonMethod.run(nodes, branches, params)
    slack_powers, flows = calc_results(nodes, branches)
    return {
        "nodes": [
            dict(n.model_dump(exclude={"loads"}),
                 u_angle_deg=math.degrees(n.u_angle), u_pu=n.u_magnitude / n.u_base)
            for n in nodes
        ],
        "slack_powers": [s.model_dump() for s in slack_powers],
        "branch_flows": [f.model_dump() for f in flows],
        "total_losses": {"dp": sum(f.dp for f in flows), "dq": sum(f.dq for f in flows)},
    }


def execute_run(run_id: int) -> None:
    run = CalculationRun.objects.select_related("project").get(pk=run_id)
    run.status = CalculationRun.Status.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])
    try:
        run.results = compute_results(run.project)
        run.status = CalculationRun.Status.SUCCESS
        run.message = "Расчет сошелся"
    except (ConvergenceError, ValueError, KeyError, TypeError) as e:
        run.status = CalculationRun.Status.FAILED
        run.message = str(e)
    except SoftTimeLimitExceeded:
        run.status = CalculationRun.Status.FAILED
        run.message = "Превышен лимит времени расчета"
    except Exception as e:
        logger.exception("Расчет %s упал", run_id)
        run.status = CalculationRun.Status.FAILED
        run.message = f"Внутренняя ошибка: {e}"
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "message", "results", "finished_at"])
