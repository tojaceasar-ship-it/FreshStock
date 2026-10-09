#!/usr/bin/env python3
"""
FreshStock performance test - create N products and measure API response times.
Run against local backend (localhost:8000). Sequential to avoid SQLite pool exhaustion.
"""

import time
import httpx
import statistics

BASE = "http://127.0.0.1:8000/api"

def login(client: httpx.Client):
    r = client.post(f"{BASE}/auth/login", json={"username": "manager", "password": "TestManager123!"})
    r.raise_for_status()
    return r.json()["access_token"]

def create_product(client: httpx.Client, headers: dict, idx: int):
    payload = {
        "sku": f"PERF-{idx:06d}",
        "name": f"Product {idx}",
        "purchase_price": "10.00",
        "selling_price": "15.00",
        "unit": "szt",
        "vat_rate": "23.00",
        "min_stock": 5,
        "target_stock": 20,
    }
    start = time.perf_counter()
    r = client.post(f"{BASE}/products", json=payload, headers=headers)
    elapsed = time.perf_counter() - start
    if r.status_code not in (200, 201):
        return None, elapsed, f"HTTP {r.status_code}: {r.text[:100]}"
    return r.json()["id"], elapsed, None

def list_products(client: httpx.Client, headers: dict):
    start = time.perf_counter()
    r = client.get(f"{BASE}/products", headers=headers)
    elapsed = time.perf_counter() - start
    r.raise_for_status()
    data = r.json()
    return len(data), elapsed

def search_products(client: httpx.Client, headers: dict, query: str):
    start = time.perf_counter()
    r = client.get(f"{BASE}/products", params={"q": query}, headers=headers)
    elapsed = time.perf_counter() - start
    r.raise_for_status()
    data = r.json()
    return len(data), elapsed

def get_product(client: httpx.Client, headers: dict, pid: int):
    start = time.perf_counter()
    r = client.get(f"{BASE}/products/{pid}", headers=headers)
    elapsed = time.perf_counter() - start
    r.raise_for_status()
    return r.json(), elapsed

def run_perf_test(count: int):
    print(f"\n=== Performance test: {count} products ===")
    with httpx.Client(timeout=60.0) as client:
        token = login(client)
        headers = {"Authorization": f"Bearer {token}"}

        # Create products sequentially
        print(f"Creating {count} products sequentially...")
        create_times = []
        errors = 0
        product_ids = []

        start = time.perf_counter()
        for i in range(1, count + 1):
            pid, elapsed, err = create_product(client, headers, i)
            if err:
                errors += 1
                print(f"  Error creating product {i}: {err}")
            else:
                create_times.append(elapsed)
                product_ids.append(pid)
        total_create = time.perf_counter() - start
        print(f"  Created {len(product_ids)}/{count} products in {total_create:.2f}s ({errors} errors)")
        if create_times:
            sorted_times = sorted(create_times)
            print(f"  Create latency: avg={statistics.mean(create_times)*1000:.1f}ms, "
                  f"p50={statistics.median(create_times)*1000:.1f}ms, "
                  f"p95={sorted_times[int(len(sorted_times)*0.95)]*1000:.1f}ms, "
                  f"p99={sorted_times[int(len(sorted_times)*0.99)]*1000:.1f}ms")

        # List all products
        print(f"Listing products...")
        list_times = []
        for _ in range(5):
            cnt, elapsed = list_products(client, headers)
            list_times.append(elapsed)
        print(f"  List ({cnt} products): avg={statistics.mean(list_times)*1000:.1f}ms")

        # Search products
        print(f"Searching products...")
        search_times = []
        for q in ["PERF-", "Product 1", "999", "sku"]:
            cnt, elapsed = search_products(client, headers, q)
            search_times.append(elapsed)
        print(f"  Search: avg={statistics.mean(search_times)*1000:.1f}ms")

        # Get individual products
        print(f"Getting individual products...")
        get_times = []
        for pid in product_ids[:min(50, len(product_ids))]:
            _, elapsed = get_product(client, headers, pid)
            get_times.append(elapsed)
        if get_times:
            sorted_get = sorted(get_times)
            print(f"  Get by ID (x{len(get_times)}): avg={statistics.mean(get_times)*1000:.1f}ms, "
                  f"p95={sorted_get[int(len(sorted_get)*0.95)]*1000:.1f}ms")

        print(f"=== Done {count} products ===")

def main():
    run_perf_test(1000)
    run_perf_test(10000)

if __name__ == "__main__":
    main()