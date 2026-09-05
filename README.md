Dynamic DNS IP Updater
======================

A small Python service that detects your public IP address and keeps dynamic DNS
records up to date. It supports [DuckDNS](https://www.duckdns.org/) and
[Cloudflare](https://www.cloudflare.com/) DNS records, and runs continuously in a
loop (typically as a Docker container).

How it works
------------

On each cycle the updater determines your current public IP using a randomly
chosen method:

- `dig` against OpenDNS (`myip.opendns.com`)
- `https://ifconfig.co/json`
- Any of the HTTP services listed in `http_services.json`

If the detected IP differs from the last one it saw, it pushes the update to
whichever providers are configured, then records the new IP and sleeps until the
next cycle.

- **DuckDNS** is updated whenever configured (the IP is inferred server-side).
- **Cloudflare** is updated only when a public IP was successfully detected. The
  zone ID and DNS record ID are looked up automatically from `CF_RECORD_NAME`,
  and the record is stamped with a comment noting the new IP and a UTC timestamp.

Configuration
-------------

Copy `updater_example.env` to `updater.env` and fill in your values:

    cp updater_example.env updater.env

| Variable | Description |
| --- | --- |
| `SLEEP_SECS` | Seconds to wait between checks (default `3600`). |
| `MAX_RETRIES` | Times to retry fetching the current IP before giving up (default `3`). |
| `DUCK_DOMAINS` | Comma-separated DuckDNS subdomains. Enables DuckDNS when set with the token. |
| `DUCK_TOKEN` | Your DuckDNS token. |
| `CF_API_TOKEN` | Cloudflare API token with **Zone > DNS > Edit** on the record's zone. |
| `CF_RECORD_NAME` | Full record to update, e.g. `dynamic.example.org`. Zone is derived from it. |
| `CF_PROXIED` | `true`/`false` — proxy the record through Cloudflare. Default `false`. |
| `USER_AGENT` | User-Agent sent with outbound HTTP requests. |
| `HTTP_SERVICES` | Path (inside the container) to the IP-lookup services JSON file. |

A provider is enabled only when its variables are present, so you can run
DuckDNS, Cloudflare, or both.

`http_services.json` is a list of IP-lookup endpoints. Each entry has a `url`;
add an optional `re` with a named `ip` group when the response isn't a bare IP
address.

Running with Docker
-------------------

Build the image and run it, mounting this directory to `/config` so the container
can read `http_services.json`:

    make build
    make run

`make run` uses `updater.env` for configuration. See the `Makefile` for the
build/tag/push targets and `docker-compose.yml` for a Compose setup.

Running locally
---------------

    pip install -r requirements.txt
    export $(grep -v '^#' updater.env | xargs)
    python dyndns_upd_ip.py
