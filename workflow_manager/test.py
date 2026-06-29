def main():
    import requests
    from requests.auth import HTTPBasicAuth

    url = "http://127.0.0.1:8000/api/jobcards"

    response = requests.get(
        url,
        auth=HTTPBasicAuth("billertest", r"87l:JR0z\MT$"),
        timeout=10,
    )

    print(response.status_code)
    print(response.json())


if __name__ == "__main__":
    main()
    print('emmpty commit')
