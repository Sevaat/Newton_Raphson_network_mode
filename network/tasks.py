from celery import shared_task

from network.services.calculation import execute_run

@shared_task(name="network.run_calculation")
def run_calculation_task(run_id: int):
    execute_run(run_id)
