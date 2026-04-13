import requests
from requests.auth import HTTPBasicAuth

url = "http://127.0.0.1:8000/api/jobcards"

# data = {
#     "job_card": "PUT_REAL_JOBCARD_UUID",
#     "invoice_series": "bds",
#     "invoice_type": "proforma",
#     "category": "customer",
#     "invoice_number": 1,
#     "invoice_url": "https://example.com/invoice/1"
# }

response = requests.get(
    url,
    # json=data,
    auth=HTTPBasicAuth("billertest", "87l:JR0z\MT$")
)

print(response.status_code)
print(response.json())
