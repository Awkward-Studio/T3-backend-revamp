import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management import BaseCommand, CommandError, call_command
from django.utils import timezone

from auditlog.models import HistoryEntry
from billing.models import Invoice, InvoiceCounter
from catalog.models.insurers_model import InsuranceProvider
from catalog.models.labour_models import Labour
from catalog.models.vehicle_models_model import VehilceModel
from inventory.models import Product
from jobcards.models import (
    CurrentLabour,
    CurrentPart,
    DeletedJobCard,
    JobCard,
    JobCardCounter,
)
from vehicle_management.models import Car, CustomerPortal, TempCar


APPWRITE_META_KEYS = {
    "$collectionId",
    "$createdAt",
    "$databaseId",
    "$id",
    "$permissions",
    "$sequence",
    "$updatedAt",
}

BATCH_SIZE = 1000


def parse_dt(value):
    if not value:
        return timezone.now()
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except ValueError:
            return None


def dec(value, default="0"):
    if value in (None, ""):
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def text(value, default="", max_length=None):
    if value is None:
        value = default
    value = str(value)
    if max_length:
        return value[:max_length]
    return value


def clean_json_value(value):
    if isinstance(value, list):
        return [clean_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: clean_json_value(item) for key, item in value.items()}
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return clean_json_value(json.loads(stripped))
            except json.JSONDecodeError:
                return value
    return value


def strip_meta(row):
    return {key: value for key, value in row.items() if key not in APPWRITE_META_KEYS}


def set_timestamps(instance, row):
    created = parse_dt(row.get("$createdAt"))
    updated = parse_dt(row.get("$updatedAt"))
    instance.__class__.objects.filter(pk=instance.pk).update(
        created_at=created,
        updated_at=updated,
    )


def created_at(row):
    return parse_dt(row.get("$createdAt"))


def updated_at(row):
    return parse_dt(row.get("$updatedAt"))


def invoice_actual_key(row):
    return json.dumps(
        {
            "jobCardId": row.get("jobCardId"),
            "carNumber": row.get("carNumber"),
            "invoiceType": row.get("invoiceType"),
            "invoiceNumber": row.get("invoiceNumber"),
            "invoiceSeries": row.get("invoiceSeries"),
            "invoiceCode": row.get("invoiceCode"),
            "insuranceInvoiceType": row.get("insuranceInvoiceType"),
            "isInsuranceInvoice": row.get("isInsuranceInvoice"),
        },
        sort_keys=True,
        default=str,
    )


class Command(BaseCommand):
    help = "Import Appwrite JSON exports from t3_data into the Django schema."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-dir",
            default="../../t3_data",
            help="Path to the folder containing Appwrite JSON exports.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write data. Without this flag the command only validates and reports.",
        )
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Flush the database before importing. Only allowed with --apply.",
        )

    def handle(self, *args, **options):
        data_dir = Path(options["data_dir"]).resolve()
        apply = options["apply"]
        flush = options["flush"]

        if flush and not apply:
            raise CommandError("--flush requires --apply")
        if not data_dir.exists():
            raise CommandError(f"Data directory does not exist: {data_dir}")

        data = self.load_data(data_dir)
        report = self.analyze(data)
        self.print_report(report)

        if not apply:
            self.stdout.write(self.style.WARNING("Dry run only. Re-run with --apply to import."))
            return

        if flush:
            call_command("flush", "--noinput", verbosity=0)

        maps = self.import_all(data)

        self.stdout.write(
            self.style.SUCCESS(
                "Imported Appwrite data. "
                f"cars={len(maps['cars'])}, temp_cars={len(maps['temp_cars'])}, "
                f"job_cards={len(maps['job_cards'])}, products={len(maps['parts'])}, "
                f"labour={len(maps['labour'])}, invoices=skipped"
            )
        )

    def load_data(self, data_dir):
        files = {
            "counters": "AtomicCounter.json",
            "car_models": "CarModels.json",
            "cars": "Cars.json",
            "deleted_job_cards": "DeletedJobCards.json",
            "history": "History.json",
            "insurers": "InsuranceProviders.json",
            "invoices": "Invoices.json",
            "job_cards": "Job_Cards.json",
            "labour": "Labour.json",
            "parts": "Parts.json",
            "temp_cars": "Temp_Cars.json",
        }
        loaded = {}
        for key, filename in files.items():
            path = data_dir / filename
            if not path.exists():
                raise CommandError(f"Missing export file: {path}")
            loaded[key] = json.loads(path.read_text(encoding="utf-8"))
        return loaded

    def analyze(self, data):
        car_ids = {row["$id"] for row in data["cars"]}
        temp_ids = {row["$id"] for row in data["temp_cars"]}
        job_ids = {row["$id"] for row in data["job_cards"]}
        part_ids = {row["$id"] for row in data["parts"]}
        labour_ids = {row["$id"] for row in data["labour"]}

        invoice_groups = defaultdict(list)
        for row in data["invoices"]:
            invoice_groups[invoice_actual_key(row)].append(row)

        missing_job_temp = sum(1 for row in data["job_cards"] if row.get("carId") not in temp_ids)
        missing_temp_car = sum(1 for row in data["temp_cars"] if row.get("carsTableId") not in car_ids)
        missing_invoice_job = sum(1 for row in data["invoices"] if row.get("jobCardId") not in job_ids)

        missing_job_parts = 0
        missing_job_labour = 0
        for row in data["job_cards"]:
            for item in clean_json_value(row.get("parts") or []):
                if isinstance(item, dict) and item.get("partId") not in part_ids:
                    missing_job_parts += 1
            for item in clean_json_value(row.get("labour") or []):
                if isinstance(item, dict) and item.get("labourId") not in labour_ids:
                    missing_job_labour += 1

        return {
            "counts": {key: len(value) for key, value in data.items()},
            "job_cards_missing_temp_car_rows": missing_job_temp,
            "temp_cars_missing_car_rows": missing_temp_car,
            "invoices_missing_job_cards": missing_invoice_job,
            "invoice_rows": len(data["invoices"]),
            "invoice_rows_after_regen_dedupe": len(invoice_groups),
            "missing_job_part_refs": missing_job_parts,
            "missing_job_labour_refs": missing_job_labour,
            "invoice_duplicate_business_groups": sum(
                1 for rows in invoice_groups.values() if len(rows) > 1
            ),
            "invoice_duplicate_business_rows": sum(
                len(rows) - 1 for rows in invoice_groups.values() if len(rows) > 1
            ),
        }

    def print_report(self, report):
        self.stdout.write("Export counts:")
        for key, count in report["counts"].items():
            self.stdout.write(f"  {key}: {count}")
        self.stdout.write("Reference checks:")
        self.stdout.write(
            f"  job cards needing temp-car stubs: {report['job_cards_missing_temp_car_rows']}"
        )
        self.stdout.write(f"  temp cars missing car rows: {report['temp_cars_missing_car_rows']}")
        self.stdout.write(
            f"  invoices skipped for now: {report['invoice_rows']} "
            f"({report['invoices_missing_job_cards']} reference missing job cards)"
        )
        self.stdout.write(f"  missing job part refs: {report['missing_job_part_refs']}")
        self.stdout.write(f"  missing job labour refs: {report['missing_job_labour_refs']}")
        self.stdout.write(
            "Invoice duplicate business keys, currently skipped: "
            f"{report['invoice_duplicate_business_groups']} groups / "
            f"{report['invoice_duplicate_business_rows']} extra rows"
        )

    def import_all(self, data):
        maps = {
            "cars": {},
            "temp_cars": {},
            "job_cards": {},
            "parts": {},
            "labour": {},
            "invoices": 0,
        }
        self.step("Importing catalog, insurers, parts, and labour")
        self.import_catalog(data, maps)
        self.step(
            f"Imported products={len(maps['parts'])}, labour={len(maps['labour'])}"
        )

        self.step("Importing cars")
        self.import_cars(data, maps)
        self.step(f"Imported cars={len(maps['cars'])}")

        self.step("Importing temp cars")
        self.import_temp_cars(data, maps)
        self.step(f"Imported temp cars from export={len(maps['temp_cars'])}")

        self.step("Importing job cards and creating missing temp-car stubs")
        self.import_job_cards(data, maps)
        self.step(
            f"Imported job cards={len(maps['job_cards'])}, temp car map={len(maps['temp_cars'])}"
        )

        self.step("Rewriting car and temp-car job-card id lists")
        self.update_car_job_lists(data, maps)
        self.step("Updated car/temp-car job-card lists")

        self.step("Deriving current parts and current labour")
        self.import_current_items(data, maps)
        self.step("Imported current parts/current labour")

        # Skip invoices for now. The export contains orphaned invoice rows and
        # repeated generated PDFs that need a separate migration policy.
        self.step("Importing counters")
        self.import_counters(data)
        self.step("Imported counters")

        self.step("Importing deleted job card archive")
        self.import_deleted_job_cards(data)
        self.step("Imported deleted job card archive")

        self.step("Importing history")
        self.import_history(data, maps)
        self.step("Imported history")
        return maps

    def step(self, message):
        self.stdout.write(message)
        self.stdout.flush()

    def import_catalog(self, data, maps):
        vehicle_models = []
        for row in data["car_models"]:
            vehicle_models.append(VehilceModel(
                make=text(row.get("make"), max_length=255),
                models=clean_json_value(row.get("models") or []),
                created_at=created_at(row),
                updated_at=updated_at(row),
            ))
        VehilceModel.objects.bulk_create(vehicle_models, batch_size=BATCH_SIZE)

        insurers = []
        for row in data["insurers"]:
            insurers.append(InsuranceProvider(
                insurer=text(row.get("insurer"), max_length=255),
                address=text(row.get("address")),
                gst=text(row.get("GST"), max_length=50),
                created_at=created_at(row),
                updated_at=updated_at(row),
            ))
        InsuranceProvider.objects.bulk_create(insurers, batch_size=BATCH_SIZE)

        seen_part_payloads = set()
        part_payload_to_pk = {}
        products = []
        for row in data["parts"]:
            payload_key = json.dumps(strip_meta(row), sort_keys=True, default=str)
            if payload_key in seen_part_payloads:
                maps["parts"][row["$id"]] = part_payload_to_pk[payload_key]
                continue
            seen_part_payloads.add(payload_key)
            item = Product(
                name=text(row.get("partName"), max_length=100),
                itemCode=text(row.get("partNumber"), max_length=50),
                sku=text(row.get("partNumber"), max_length=50),
                hsn=text(row.get("hsn"), max_length=50),
                category=text(row.get("category"), max_length=50),
                quantity=0,
                price=dec(row.get("mrp")),
                mrp=dec(row.get("mrp")),
                gst=dec(row.get("gst")),
                cgst=dec(row.get("cgst")),
                sgst=dec(row.get("sgst")),
                created_at=created_at(row),
                updated_at=updated_at(row),
            )
            products.append(item)
            maps["parts"][row["$id"]] = item.pk
            part_payload_to_pk[payload_key] = item.pk
        Product.objects.bulk_create(products, batch_size=BATCH_SIZE)

        seen_labour_payloads = set()
        labour_payload_to_pk = {}
        labours = []
        for row in data["labour"]:
            payload_key = json.dumps(strip_meta(row), sort_keys=True, default=str)
            if payload_key in seen_labour_payloads:
                maps["labour"][row["$id"]] = labour_payload_to_pk[payload_key]
                continue
            seen_labour_payloads.add(payload_key)
            item = Labour(
                labour_name=text(row.get("labourName"), max_length=255),
                labour_code=text(row.get("labourCode"), default=None, max_length=50),
                hsn=text(row.get("hsn"), max_length=20),
                category=text(row.get("category"), default=None, max_length=100),
                mrp=dec(row.get("mrp")),
                gst=dec(row.get("gst")),
                cgst=dec(row.get("cgst")),
                sgst=dec(row.get("sgst")),
                created_at=created_at(row),
                updated_at=updated_at(row),
            )
            labours.append(item)
            maps["labour"][row["$id"]] = item.pk
            labour_payload_to_pk[payload_key] = item.pk
        Labour.objects.bulk_create(labours, batch_size=BATCH_SIZE)

    def import_cars(self, data, maps):
        cars = []
        rows = []
        for row in data["cars"]:
            car = Car(
                car_number=text(row.get("carNumber"), max_length=100),
                car_make=text(row.get("carMake"), max_length=100),
                car_model=text(row.get("carModel"), max_length=100),
                location=text(row.get("location"), max_length=200),
                purpose_of_visit=text(row.get("purposeOfVisit"), max_length=200),
                all_job_cards=[],
                cars_table_id="",
                customer_name=text(row.get("customerName"), max_length=200),
                customer_phone=text(row.get("customerPhone"), max_length=20),
                customer_address=text(row.get("customerAddress"), max_length=300),
                purpose_of_visit_and_advisors=clean_json_value(
                    row.get("purposeOfVisitAndAdvisors") or []
                ),
                customer_email=text(row.get("customerEmail")),
                calling_status=int(row.get("callingStatus") or 0),
                created_at=created_at(row),
                updated_at=updated_at(row),
            )
            cars.append(car)
            rows.append(row)
        Car.objects.bulk_create(cars, batch_size=BATCH_SIZE)
        portals = []
        for row, car in zip(rows, cars):
            maps["cars"][row["$id"]] = car.pk
            portals.append(CustomerPortal(car=car))
        CustomerPortal.objects.bulk_create(portals, batch_size=BATCH_SIZE)

    def import_temp_cars(self, data, maps):
        temp_cars = []
        rows = []
        for row in data["temp_cars"]:
            car_pk = maps["cars"].get(row.get("carsTableId"))
            if not car_pk:
                continue
            temp = TempCar(
                car_id=car_pk,
                job_card_id="",
                car_status=int(row.get("carStatus") or 0),
                cars_table_id=str(car_pk),
                purpose_of_visit_and_advisors=clean_json_value(
                    row.get("purposeOfVisitAndAdvisors") or []
                ),
                all_job_card_ids=[],
                created_at=created_at(row),
                updated_at=updated_at(row),
            )
            temp_cars.append(temp)
            rows.append(row)
        TempCar.objects.bulk_create(temp_cars, batch_size=BATCH_SIZE)
        for row, temp in zip(rows, temp_cars):
            maps["temp_cars"][row["$id"]] = temp.pk

    def import_job_cards(self, data, maps):
        cars_by_number = {car.car_number: car for car in Car.objects.all()}
        for row in data["job_cards"]:
            temp_pk = maps["temp_cars"].get(row.get("carId"))
            if not temp_pk:
                car = cars_by_number.get(row.get("carNumber"))
                if not car:
                    car = Car.objects.create(
                        car_number=text(row.get("carNumber"), max_length=100),
                        customer_name=text(row.get("customerName"), max_length=200),
                        customer_phone=text(row.get("customerPhone"), max_length=20),
                    )
                    cars_by_number[car.car_number] = car
                temp = TempCar.objects.create(
                    car=car,
                    job_card_id="",
                    car_status=int(row.get("jobCardStatus") or 0),
                    cars_table_id=str(car.pk),
                    purpose_of_visit_and_advisors=[],
                    all_job_card_ids=[],
                )
                temp_pk = temp.pk
                maps["temp_cars"][row.get("carId")] = temp_pk

            job = JobCard.objects.create(
                car_id=str(temp_pk),
                temp_car_id=temp_pk,
                diagnosis=clean_json_value(row.get("diagnosis") or []),
                send_to_parts_manager=bool(row.get("sendToPartsManager")),
                car_number=text(row.get("carNumber"), max_length=100),
                job_card_status=int(row.get("jobCardStatus") or 0),
                customer_name=text(row.get("customerName"), max_length=255),
                customer_phone=text(row.get("customerPhone"), max_length=15),
                customer_address=text(row.get("customerAddress")),
                customer_email=text(row.get("customerEmail")) or None,
                gstin=text(row.get("gstin"), default=None, max_length=20),
                parts=clean_json_value(row.get("parts") or []),
                labour=clean_json_value(row.get("labour") or []),
                images=clean_json_value(row.get("images") or []),
                job_card_number=int(row.get("jobCardNumber") or 0),
                car_fuel=text(row.get("carFuel"), default=None, max_length=50),
                bat_odometer=text(row.get("carOdometer"), default=None, max_length=50),
                insurance_details=text(row.get("insuranceDetails"), default=None),
                sub_total=dec(row.get("subTotal")),
                discount_amount=dec(row.get("discountAmt")),
                amount=dec(row.get("amount")),
                taxes=clean_json_value(row.get("taxes") or []),
                job_card_pdf=text(row.get("jobCardPDF"), default=None),
                gate_pass_pdf=text(row.get("gatePassPDF"), default=None),
                purpose_of_visit=text(row.get("purposeOfVisit"), default=None, max_length=255),
                service_advisor_id=text(row.get("serviceAdvisorID"), default=None, max_length=100),
                observation_remarks=text(row.get("observationRemarks"), default=None),
                calling_status=int(row.get("callingStatus") or 0),
            )
            maps["job_cards"][row["$id"]] = job.pk
            set_timestamps(job, row)

    def update_car_job_lists(self, data, maps):
        job_ids_by_car_number = defaultdict(list)
        job_ids_by_temp_pk = defaultdict(list)
        for row in data["job_cards"]:
            job_pk = maps["job_cards"].get(row["$id"])
            if not job_pk:
                continue
            job_ids_by_car_number[row.get("carNumber")].append(str(job_pk))
            temp_pk = maps["temp_cars"].get(row.get("carId"))
            if temp_pk:
                job_ids_by_temp_pk[temp_pk].append(str(job_pk))

        for car in Car.objects.all():
            ids = job_ids_by_car_number.get(car.car_number, [])
            if ids:
                car.all_job_cards = ids
                car.save(update_fields=["all_job_cards"])

        for temp in TempCar.objects.all():
            ids = job_ids_by_temp_pk.get(temp.pk, [])
            if ids:
                temp.all_job_card_ids = ids
                temp.job_card_id = ids[-1]
                temp.save(update_fields=["all_job_card_ids", "job_card_id"])

    def import_current_items(self, data, maps):
        current_parts = []
        current_labours = []
        jobs = JobCard.objects.in_bulk(maps["job_cards"].values())
        for row in data["job_cards"]:
            job_pk = maps["job_cards"].get(row["$id"])
            if not job_pk:
                continue
            job = jobs.get(job_pk)
            if not job:
                continue
            for part in clean_json_value(row.get("parts") or []):
                if not isinstance(part, dict):
                    continue
                product_pk = maps["parts"].get(part.get("partId"))
                if not product_pk:
                    continue
                current_parts.append(CurrentPart(
                    job_card_id=job.pk,
                    product_id=product_pk,
                    part_id=str(product_pk),
                    part_name=text(part.get("partName"), max_length=255),
                    part_number=text(part.get("partNumber"), max_length=50),
                    hsn=text(part.get("hsn"), default=None, max_length=20),
                    quantity=int(part.get("quantity") or 1),
                    mrp=dec(part.get("mrp")),
                    sub_total=dec(part.get("subTotal")),
                    total_tax=dec(part.get("totalTax")),
                    amount=dec(part.get("amount")),
                    gst=dec(part.get("gst")),
                    cgst=dec(part.get("cgst")),
                    sgst=dec(part.get("sgst")),
                    cgst_amount=dec(part.get("cgstAmt")),
                    sgst_amount=dec(part.get("sgstAmt")),
                    insurance_percentage=dec(part.get("insurancePercentage"), default="0"),
                    insurance_amount=dec(part.get("insuranceAmt"), default="0"),
                    customer_amount=dec(part.get("customerAmt"), default="0"),
                ))
            for labour in clean_json_value(row.get("labour") or []):
                if not isinstance(labour, dict) or not job.temp_car_id:
                    continue
                current_labours.append(CurrentLabour(
                    temp_car_id=job.temp_car_id,
                    labour_id=str(maps["labour"].get(labour.get("labourId"), labour.get("labourId") or "")),
                    labour_name=text(labour.get("labourName"), max_length=255),
                    labour_code=text(labour.get("labourCode"), max_length=50),
                    hsn_code=text(labour.get("hsn"), default=None, max_length=20),
                    mrp=dec(labour.get("mrp")),
                    gst_percentage=dec(labour.get("gst")),
                    cgst=dec(labour.get("cgst")),
                    sgst=dec(labour.get("sgst")),
                    quantity=int(labour.get("quantity") or 1),
                    sub_total=dec(labour.get("subTotal")),
                    cgst_amount=dec(labour.get("cgstAmt")),
                    sgst_amount=dec(labour.get("sgstAmt")),
                    total_tax=dec(labour.get("totalTax")),
                    total_amount=dec(labour.get("amount")),
                ))
        CurrentPart.objects.bulk_create(current_parts, batch_size=BATCH_SIZE)
        CurrentLabour.objects.bulk_create(current_labours, batch_size=BATCH_SIZE)

    def import_invoices(self, data, maps):
        for row in data["invoices"]:
            job_pk = maps["job_cards"].get(row.get("jobCardId"))
            if not job_pk:
                continue
            invoice = Invoice.objects.create(
                job_card_id=job_pk,
                invoice_series=text(row.get("invoiceSeries"), max_length=10),
                invoice_type=text(row.get("invoiceType"), max_length=50),
                category=text(row.get("insuranceInvoiceType")),
                invoice_number=int(row.get("invoiceNumber") or 0),
                invoice_code=text(row.get("invoiceCode"), max_length=50),
                car_number=text(row.get("carNumber"), max_length=50),
                is_updated=bool(row.get("isUpdatedInvoice")),
                is_insurance_invoice=bool(row.get("isInsuranceInvoice")),
                invoice_url=text(row.get("invoiceUrl")),
            )
            set_timestamps(invoice, row)
            maps["invoices"] += 1

    def import_counters(self, data):
        for row in data["counters"]:
            series = row.get("series")
            current = int(row.get("currentNumber") or 0)
            if series == "JCARD":
                JobCardCounter.objects.update_or_create(
                    name="jobcard",
                    defaults={"last_number": current},
                )
            elif series in {"SER", "BDS"}:
                InvoiceCounter.objects.update_or_create(
                    series=series,
                    defaults={"last_number": current},
                )

    def import_deleted_job_cards(self, data):
        for row in data["deleted_job_cards"]:
            raw = clean_json_value(row.get("details"))
            if not isinstance(raw, dict):
                raw = {"details": row.get("details")}
            DeletedJobCard.objects.create(
                job_card_snapshot=clean_json_value(raw.get("jobcardDetails")),
                reason=text(raw.get("reason")),
                raw_details=raw,
                created_at=parse_dt(row.get("$createdAt")),
                updated_at=parse_dt(row.get("$updatedAt")),
            )

    def import_history(self, data, maps):
        type_maps = {
            "cars": maps["cars"],
            "temp-cars": maps["temp_cars"],
            "job-cards": maps["job_cards"],
            "parts": maps["parts"],
            "labour": maps["labour"],
        }
        for row in data["history"]:
            values = {}
            history = clean_json_value(row.get("history") or [])
            for item in history:
                if isinstance(item, str) and ": " in item:
                    key, value = item.split(": ", 1)
                    values[key] = value
            object_type = values.get("objectType", "")
            old_object_id = values.get("objectId", "")
            new_object_id = type_maps.get(object_type, {}).get(old_object_id, old_object_id)
            if new_object_id != old_object_id:
                history = [
                    f"objectId: {new_object_id}"
                    if isinstance(item, str) and item.startswith("objectId: ")
                    else item
                    for item in history
                ]
            HistoryEntry.objects.create(
                object_id=text(new_object_id, max_length=100),
                object_type=text(object_type, max_length=50),
                operation_type=text(values.get("operationType"), max_length=30),
                user_id=text(values.get("userId"), max_length=100),
                user_email=text(values.get("userEmail")),
                user_name=text(values.get("userName"), max_length=255),
                history=history,
                created_at=parse_dt(row.get("$createdAt")),
            )
