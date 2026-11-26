import json
import time
import urllib.request

try:
    import requests
except ImportError:
    requests = None

URL = "http://10.111.160.115:8080/get?accX&accY&accZ"


def fetch_data(timeout=2):
    """Fetch the latest (x, y, z) accelerometer sample from Phyphox, raising on error."""
    if requests is not None:
        res = requests.get(URL, timeout=timeout)
        res.raise_for_status()
        data = res.json()
    else:
        with urllib.request.urlopen(URL, timeout=timeout) as res:
            data = json.loads(res.read().decode("utf-8"))

    accX = data["buffer"]["accX"]["buffer"]
    accY = data["buffer"]["accY"]["buffer"]
    accZ = data["buffer"]["accZ"]["buffer"]

    x = accX[-1] if accX and accX[-1] is not None else 0
    y = accY[-1] if accY and accY[-1] is not None else 0
    z = accZ[-1] if accZ and accZ[-1] is not None else 0

    return x, y, z


def get_data():
    try:
        return fetch_data()
    except Exception as e:
        print("Phyphox Error:", e)
        return 0, 0, 0


if __name__ == "__main__":
    while True:
        x, y, z = get_data()
        print(x, y, z)
        time.sleep(1)