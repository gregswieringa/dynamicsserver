#!/usr/bin/env python3
"""Simulates steady, realistic buyer-api traffic: mostly GETs against known
users (like people logging in), fewer profile MODIFYs, rare CREATEs (new
signups) -- volume follows a diurnal curve peaking 8am-10pm US/Eastern and
trailing off overnight, not a hard on/off switch.

Meant to be invoked once a minute by cron (see deploy/traffic-sim.cron);
each invocation computes how many requests to fire *this* minute from the
current time of day, then paces them with small random gaps across the
minute. Deliberately stdlib-only -- this runs directly on the VM host via
cron, not in a container, so no pip/venv setup needed.

State (the pool of known user IDs to target for GET/MODIFY) persists in a
small JSON file between runs -- see --state-file.
"""
import argparse
import json
import random
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

# (hour, requests-per-minute) control points, piecewise-linear between them.
# Flat low overnight, ramp up into the morning, flat peak through the day,
# ramp down into the evening -- a trail-off, not a cliff.
RATE_CURVE = [
    (0, 2), (6, 2), (8, 20), (20, 20), (22, 8), (24, 2),
]

FIRST_NAMES = ["Alex", "Jordan", "Sam", "Casey", "Morgan", "Taylor", "Riley", "Jamie", "Avery", "Quinn"]
LAST_NAMES = ["Smith", "Johnson", "Lee", "Brown", "Garcia", "Nguyen", "Patel", "Kim", "Davis", "Martinez"]


def rate_at(now_eastern: datetime) -> float:
    hour = now_eastern.hour + now_eastern.minute / 60
    for (h1, r1), (h2, r2) in zip(RATE_CURVE, RATE_CURVE[1:]):
        if h1 <= hour <= h2:
            frac = (hour - h1) / (h2 - h1) if h2 != h1 else 0
            return r1 + frac * (r2 - r1)
    return RATE_CURVE[-1][1]


def load_state(path: str) -> list[str]:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_state(path: str, user_ids: list[str]) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(user_ids, f)
    import os
    os.replace(tmp, path)


def request(method: str, url: str, body: dict | None = None) -> int:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def create_user(base_url: str) -> str | None:
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    payload = {
        "email": f"simuser.{random.randint(0, 10_000_000)}@example.com",
        "display_name": f"{first} {last}",
        "first_name": first,
        "last_name": last,
        "marketing_opt_in": random.choice([True, False]),
    }
    req = urllib.request.Request(
        f"{base_url}/users",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
            return body["id"]
    except urllib.error.HTTPError:
        return None


def get_user(base_url: str, user_id: str) -> int:
    return request("GET", f"{base_url}/users/{user_id}")


def modify_user(base_url: str, user_id: str) -> int:
    change = random.choice([
        {"marketing_opt_in": random.choice([True, False])},
        {"display_name": f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"},
    ])
    return request("PATCH", f"{base_url}/users/{user_id}", change)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="e.g. http://localhost:8082")
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--min-pool-size", type=int, default=50)
    parser.add_argument("--get-weight", type=float, default=0.70)
    parser.add_argument("--modify-weight", type=float, default=0.20)
    parser.add_argument("--create-weight", type=float, default=0.10)
    args = parser.parse_args()

    now = datetime.now(EASTERN)
    user_ids = load_state(args.state_file)

    # Bootstrap: first run (or any run that finds too small a pool) tops it
    # up to min_pool_size before doing anything else this minute.
    while len(user_ids) < args.min_pool_size:
        new_id = create_user(args.base_url)
        if new_id:
            user_ids.append(new_id)
    save_state(args.state_file, user_ids)

    target_rate = rate_at(now) * random.uniform(0.8, 1.2)
    n_requests = max(0, round(target_rate))

    counts = {"get": 0, "modify": 0, "create": 0}
    for i in range(n_requests):
        if i > 0:
            time.sleep(60 / max(n_requests, 1) * random.uniform(0.5, 1.5))
        action = random.choices(
            ["get", "modify", "create"],
            weights=[args.get_weight, args.modify_weight, args.create_weight],
        )[0]
        if action == "get" and user_ids:
            get_user(args.base_url, random.choice(user_ids))
        elif action == "modify" and user_ids:
            modify_user(args.base_url, random.choice(user_ids))
        else:
            new_id = create_user(args.base_url)
            if new_id:
                user_ids.append(new_id)
                action = "create"
            else:
                continue
        counts[action] += 1

    save_state(args.state_file, user_ids)
    print(
        f"{now.isoformat()} rate={target_rate:.1f}/min "
        f"fired={sum(counts.values())} get={counts['get']} "
        f"modify={counts['modify']} create={counts['create']} "
        f"pool={len(user_ids)}"
    )


if __name__ == "__main__":
    main()
