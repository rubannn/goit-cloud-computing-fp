"""Bounded, read-only HTTP load test for the Quotes application (standard library only)."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime
import threading
import time
from urllib.parse import urlsplit
from urllib.request import urlopen


def run_test(base_url: str, duration: float, workers: int) -> int:
    url = base_url.rstrip("/") + "/api/quotes?limit=20"
    stop = threading.Event()
    lock = threading.Lock()
    counts = {"successful": 0, "errors": 0}
    started = time.monotonic()
    deadline = started + duration

    def report():
        with lock:
            successful, errors = counts["successful"], counts["errors"]
        print(f"Elapsed: {time.monotonic() - started:.1f}s | Successful: {successful} | Errors: {errors}", flush=True)

    def worker():
        while not stop.is_set() and time.monotonic() < deadline:
            success = False
            try:
                with urlopen(url, timeout=10) as response:
                    response.read()
                    success = response.status == 200
            except OSError:
                pass
            with lock:
                counts["successful" if success else "errors"] += 1

    print(f"URL: {url}", flush=True)
    print(f"Start: {datetime.now().astimezone().isoformat(timespec='seconds')}", flush=True)
    print(f"Duration: {duration:g}s | Workers: {workers} | Stop: Ctrl+C", flush=True)
    interrupted = False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker) for _ in range(workers)]
        try:
            pending = futures
            while pending:
                _, pending = wait(pending, timeout=15)
                report()
            for future in futures:
                future.result()
        except KeyboardInterrupt:
            interrupted = True
            stop.set()
            print("Stopping; waiting for in-flight requests (timeout: 10s).", flush=True)
    print(f"End: {datetime.now().astimezone().isoformat(timespec='seconds')}", flush=True)
    report()
    return 130 if interrupted else int(counts["errors"] > 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Base URL of your own Quotes environment")
    parser.add_argument("--duration", type=float, default=900, help="Duration in seconds (default: 900)")
    parser.add_argument("--workers", type=int, default=10, help="Concurrent requests (default: 10; maximum: 100)")
    args = parser.parse_args()
    parsed = urlsplit(args.url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error("--url must be an HTTP(S) base URL without credentials, query or fragment")
    if not 0 < args.duration <= 3600:
        parser.error("--duration must be greater than 0 and at most 3600 seconds")
    if not 1 <= args.workers <= 100:
        parser.error("--workers must be between 1 and 100")
    return run_test(args.url, args.duration, args.workers)


if __name__ == "__main__":
    raise SystemExit(main())
