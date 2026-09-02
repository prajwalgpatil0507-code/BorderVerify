"""Download + extract MongoDB Community Server (no admin required)."""
import os
import sys
import urllib.request as u
import zipfile

VER = "8.0.4"
URL = f"https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-{VER}.zip"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ZIP = os.path.join(ROOT, "mongodb", "mongodb.zip")
OUT = os.path.join(ROOT, "mongodb")


def download():
    os.makedirs(os.path.dirname(ZIP), exist_ok=True)
    if os.path.exists(ZIP) and os.path.getsize(ZIP) > 700_000_000:
        print("Zip already downloaded:", ZIP)
        return
    print("Downloading", URL)
    req = u.Request(URL, method="GET")
    with u.urlopen(req, timeout=300) as resp, open(ZIP, "wb") as f:
        total = int(resp.headers.get("Content-Length", "0"))
        done = 0
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            print(f"\r  {done/1e6:6.1f}/{total/1e6:.1f} MB", end="")
    print("\nDownload complete.")


def extract():
    os.makedirs(OUT, exist_ok=True)
    target = os.path.join(OUT, "mongod.exe")
    if os.path.exists(target):
        print("mongod.exe already present:", target)
        return target
    print("Extracting mongod.exe ...")
    with zipfile.ZipFile(ZIP) as z:
        name = [n for n in z.namelist() if n.endswith("bin/mongod.exe")][0]
        with z.open(name) as src, open(target, "wb") as dst:
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                dst.write(chunk)
    print("Extracted:", target)
    return target


if __name__ == "__main__":
    download()
    target = extract()
    print("MONGOD_EXE=" + target)
