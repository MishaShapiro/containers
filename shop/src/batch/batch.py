"""Заглушка «ночной аналитики»: жжёт CPU и держит память. Параметры из env."""
import multiprocessing
import os
import time

CPU_WORKERS = int(os.getenv("CPU_WORKERS", "1"))
MEM_MB = int(os.getenv("MEM_MB", "100"))
STEP_MB = int(os.getenv("MEM_STEP_MB", "50"))


def burn():
    x = 0
    while True:
        x = (x * 31 + 7) % 1000003


if __name__ == "__main__":
    for _ in range(CPU_WORKERS):
        multiprocessing.Process(target=burn, daemon=True).start()
    hog = []
    # b"\x01" * n реально заполняет страницы: память попадает в RSS/working set, а не остаётся «обещанной»
    while len(hog) * STEP_MB < MEM_MB:
        hog.append(b"\x01" * (STEP_MB * 1024 * 1024))
        print(f"holding {len(hog) * STEP_MB} MiB", flush=True)
        time.sleep(1)
    while True:
        time.sleep(60)
