from jobcards.models import JobCard
from vehicle_management.models import Car


def caller_car_records(cutoff):
    """Return the cars shown to callers, including the existing job-card fallback."""
    cars = list(Car.objects.filter(created_at__lte=cutoff).order_by("-id"))
    missing_numbers = [
        car.car_number
        for car in cars
        if not car.customer_name and not car.customer_phone
    ]
    fallback_by_number = {}
    if missing_numbers:
        jobcards = (
            JobCard.objects.filter(
                created_at__lte=cutoff,
                car_number__in=missing_numbers,
            )
            .order_by("-created_at")
        )
        for jobcard in jobcards:
            fallback_by_number.setdefault(jobcard.car_number, jobcard)

    records = []
    for car in cars:
        fallback = fallback_by_number.get(car.car_number)
        use_fallback = bool(
            fallback and not car.customer_name and not car.customer_phone
        )
        records.append(
            {
                "car": car,
                "customer_name": fallback.customer_name if use_fallback else car.customer_name,
                "customer_phone": fallback.customer_phone if use_fallback else car.customer_phone,
            }
        )
    return records
