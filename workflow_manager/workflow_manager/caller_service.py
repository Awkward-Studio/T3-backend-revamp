from jobcards.models import JobCard
from django.utils import timezone
from vehicle_management.models import Car


def _car_key(value):
    return "".join(character for character in (value or "").upper() if character.isalnum())


def _local_date(value):
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.date()


def caller_car_records(cutoff):
    """Return Caller-page cars due since their latest completed service period."""
    cars = list(Car.objects.all().order_by("-id"))
    car_numbers = [car.car_number for car in cars]
    car_keys = {_car_key(car.car_number) for car in cars}
    latest_jobcard = {}
    latest_completed = {}
    jobcards = JobCard.objects.filter(car_number__in=car_numbers).order_by("-created_at")
    for jobcard in jobcards:
        key = _car_key(jobcard.car_number)
        if key not in car_keys:
            continue
        latest_jobcard.setdefault(key, jobcard)
        if jobcard.post_delivery_completed_at is not None:
            current = latest_completed.get(key)
            if current is None or jobcard.post_delivery_completed_at > current.post_delivery_completed_at:
                latest_completed[key] = jobcard

    records = []
    for car in cars:
        key = _car_key(car.car_number)
        fallback = latest_jobcard.get(key)
        use_fallback = bool(
            fallback and not car.customer_name and not car.customer_phone
        )
        completed = latest_completed.get(key)
        period_at = completed.post_delivery_completed_at if completed else car.created_at
        if period_at > cutoff:
            continue
        records.append(
            {
                "car": car,
                "car_number": key,
                "period_date": _local_date(period_at),
                "customer_name": fallback.customer_name if use_fallback else car.customer_name,
                "customer_phone": fallback.customer_phone if use_fallback else car.customer_phone,
            }
        )
    return records
