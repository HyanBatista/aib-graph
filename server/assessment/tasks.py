from celery import shared_task

from . import services


@shared_task
def generate_test_task(classroom_id):
    services.generate_test(classroom_id)


@shared_task
def grade_attempt_task(attempt_id):
    services.grade_attempt(attempt_id)
