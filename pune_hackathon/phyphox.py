import requests
import time

URL = "http://10.111.160.115:8080/get?accX&accY&accZ"

def get_data():
    try:
        res = requests.get("http://10.111.160.115:8080/get?accX&accY&accZ", timeout=2)
        data = res.json()

        accX = data["buffer"]["accX"]["buffer"]
        accY = data["buffer"]["accY"]["buffer"]
        accZ = data["buffer"]["accZ"]["buffer"]

        x = accX[-1] if accX and accX[-1] is not None else 0
        y = accY[-1] if accY and accY[-1] is not None else 0
        z = accZ[-1] if accZ and accZ[-1] is not None else 0

        return x, y, z

    except Exception as e:
        print("Phyphox Error:", e)
        return 0, 0, 0
    
    import time

while True:
    x, y, z = get_data()
    print(x, y, z)
    time.sleep(1)