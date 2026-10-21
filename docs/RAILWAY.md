# Railway API connectivity

The frontend proxies `/api/` to `investiq-app.railway.internal:8000`. Its runtime environment can override `API_UPSTREAM` with a different `hostname:port` (without `http://` or a path). Both services must be in the same Railway project and environment.

The backend Docker image starts `python run_server.py`. It accepts IPv4 and IPv6 on port 8000 for the private proxy, and also listens on Railway's `PORT` if that differs. Set `API_INTERNAL_PORT` only when intentionally changing the private port, and update the frontend's `API_UPSTREAM` to match. Remove any Railway start-command override that bypasses this script; the normal Docker command is sufficient.

The Nginx configuration is a runtime template. The official image exports the DNS resolvers from `/etc/resolv.conf`, including IPv6 resolver addresses. The proxy resolves its backend at request time and caches DNS answers for ten seconds, so a backend redeployment does not leave it pointing indefinitely at an old container address. Connection attempts are bounded; the longer response timeout permits explicit AI research requests. Normal client-cancellation behavior is preserved.

## Diagnosing a 499

Nginx uses 499 when its downstream client closes before a response is sent. For this frontend, typing another search term, choosing a suggestion, blurring the input, or leaving the page aborts the previous autocomplete request. Those cancellations can legitimately appear as 499 entries; disabling cancellation would make stale search results more likely.

If the static homepage works but `/api/health` hangs, investigate frontend-to-backend connectivity before market providers. The health route does not call Finnhub or OpenAI. Check the backend startup logs, its service name/private port, the shared Railway environment and the frontend's `API_UPSTREAM` value.

Access logs include request time, upstream connect time, upstream response time, upstream status and the selected upstream address. These distinguish immediate browser cancellations from requests waiting on private-network connections or provider responses.

After a rollout, verify both:

```sh
curl --max-time 15 https://YOUR-FRONTEND.up.railway.app/api/health
curl --max-time 20 'https://YOUR-FRONTEND.up.railway.app/api/stocks/search?q=NVDA&market=US'
```

A successful health request with a failed search points to provider configuration or access rather than private-network routing. The search field now shows an availability error when an uncancelled request fails.

Sources: [Railway private networking](https://docs.railway.com/networking/private-networking/how-it-works), [Nginx variable proxy resolution](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass), [Nginx's 499 definition](https://github.com/nginx/nginx/blob/master/src/http/ngx_http_request.h), [official Nginx resolver entrypoint](https://github.com/nginx/docker-nginx/blob/master/entrypoint/15-local-resolvers.envsh).
