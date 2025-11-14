import requests

URL = "https://www.mju.ac.kr/diet/mjukr/7/view.do"
html = requests.get(URL, headers={"User-Agent": "Test"}).text

with open("RAW_HTML.txt", "w", encoding="utf-8") as f:
    f.write(html)

print("Saved RAW_HTML.txt")
