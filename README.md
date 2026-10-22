# AuthZEN Test PDP

A small, **non-certified** experimental Policy Decision Point (PDP) implementing the AuthZEN Access Evaluation HTTP endpoint for interoperability testing. It is not production authorization software.

## Run locally

```bash
python pdp.py
python -m unittest discover -v
```

Call the endpoint at `POST http://localhost:8080/access/v1/evaluation`:

```bash
curl -X POST http://localhost:8080/access/v1/evaluation \
  -H 'Content-Type: application/json' \
  -d '{"subject":{"type":"user","id":"alice"},"action":{"name":"read"},"resource":{"type":"record","id":"record-1"}}'
```

The fixture PDP uses hardcoded, illustrative decisions. **It has not been tested against the OpenID Foundation certification suite.** It currently implements evaluation only, not batch evaluation, search, or discovery. It needs coverage review against the certification scenario before official testing.

## Docker

```bash
docker build -t authzen-test-pdp .
docker run --rm -p 8080:8080 authzen-test-pdp
```

For a remote certification test, deploy behind HTTPS with appropriate access restrictions. Do not expose this illustrative PDP as a real authorization service.

## Contributing

Use pull requests and GitHub Actions for tests. The official AuthZEN test suite is maintained separately at https://gitlab.com/openid/conformance-suite.
