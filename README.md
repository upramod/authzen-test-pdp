# AuthZEN Test PDP

A small, **non-certified** experimental Policy Decision Point (PDP) for AuthZEN interoperability testing. It is not production authorization software.

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

The fixture PDP uses hardcoded, illustrative decisions. It implements single evaluation, batch evaluation with `execute_all`, subject/resource/action search, and unsigned discovery metadata. Search returns all matches without pagination. Optional short-circuit batch semantics are unsupported and return HTTP 400.

The previously deployed evaluation-only version was reported as passing 31 tests in [this alpha evaluation plan](https://www.certification.openid.net/plan-detail.html?plan=kgzhV4OSKp2Pv). That result does not cover the newly added endpoints. Official batch, search, and discovery runs remain pending. Local unit tests are not OpenID certification.

Discovery uses `PDP_IDENTIFIER` from the environment, defaulting to the existing Azure test deployment. Set it to the exact public HTTPS base URL when deploying elsewhere. Metadata never derives its URLs from caller-supplied Host headers.

## Remaining official test plans

Use the [OpenID testing instructions](https://openid.net/certification/authzen_testing/) and `conformance-config.json` after deploying this version. For batch and search select authentication `none`, metadata `discovery`, and specification support `properties`. Discovery has no variants. Keep results private until inspected.

Run these plans:

- `authzen-pdp-evaluations-test-plan`
- `authzen-pdp-subject-search-test-plan`
- `authzen-pdp-resource-search-test-plan`
- `authzen-pdp-action-search-test-plan`
- `authzen-pdp-discovery-test-plan`

Also rerun `authzen-pdp-evaluation-test-plan` to check the existing endpoint. Record each plan URL, suite version, tested image commit, pass/fail/skip counts, and any failing test details. Do not report unexecuted plans as passed.

## Docker

```bash
docker build -t authzen-test-pdp .
docker run --rm -p 8080:8080 authzen-test-pdp
```

For a remote certification test, deploy behind HTTPS with appropriate access restrictions. Do not expose this illustrative PDP as a real authorization service.

## Contributing

Use pull requests and GitHub Actions for tests. The official AuthZEN test suite is maintained separately at https://gitlab.com/openid/conformance-suite.
