import urllib.request as u
r = {}
for ver in ("8.0.4", "7.0.14", "8.1.3"):
    url = f"https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-{ver}.zip"
    try:
        resp = u.urlopen(u.Request(url, method="GET",
                                   headers={"Range": "bytes=0-0"}), timeout=25)
        r[ver] = (resp.status,
                  resp.headers.get("Content-Length"),
                  resp.headers.get("Content-Range"))
    except Exception as e:  # noqa: BLE001
        r[ver] = ("ERR", type(e).__name__, str(e)[:100])
print(r)
