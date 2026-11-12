# AI Compass EvalLab

A separate AI governance evaluation application built with Next.js, FastAPI, LangChain, LangGraph and LangSmith. Evaluate policy decisions, required conditions, citation references, escalation and tool trajectories. Compare versioned experiments and export case-level evidence.

## Current status

- Frontend production build and TypeScript checks passed.
- Ten backend tests passed.
- Forty fictional, AI-authored demonstration cases are included. All initial labels are pending independent human review.
- Local rule baseline and improved configurations execute real checks. These are demonstration results, not independent model validation.
- Live model execution requires OpenAI and LangSmith credentials. Remote trace delivery is not yet verified.
- Render configuration is supplied, but deployment has not been performed.

## Start locally

Requires Python 3.12 and Node.js 22.

```bash
./setup.sh
cp .env.example .env
./run-local.sh
```

Open http://127.0.0.1:8200. The backend serves the exported Next.js application, so only one server is needed. Configure server-side keys in `.env` for live runs; never commit credentials.

## Application screens

1. Overview: purpose, evaluation workflow and readiness.
2. Dataset: inspect and independently review proposed reference labels.
3. Experiments: run baseline or selected improvements in demo or live mode.
4. Compare: compare identical dataset, policy and execution-mode snapshots.
5. Case explorer: inspect expected versus actual behavior, tool events and human judgments.
6. Observability: local events, architecture, audit and remote tracing status.
7. Evidence: export JSON snapshots or CSV case-level scores.

## Evaluation integrity

Expected answers are never passed to the agent. Scoring occurs after execution. Runs retain dataset snapshots and fingerprints; changing a label prevents comparison with an older version. Citation matching checks reference IDs, not semantic faithfulness. Human answer-support review is separate. Metrics without applicable cases are not treated as perfect scores.

The seed dataset is entirely AI-authored. The Week 4 handout limits purely LLM-generated examples to below 20%; replace or supplement these seeds with appropriately sourced, independently reviewed cases before submission. Keep a holdout set for validation.

## Demonstration results

| Metric | Baseline | Four improvements |
| --- | ---: | ---: |
| Decision accuracy | 50.0% | 100.0% |
| Required condition recall | 29.17% | 100.0% |
| Citation reference match | 50.0% | 100.0% |
| Escalation recall | 27.27% | 100.0% |
| Tool trajectory accuracy | 90.0% | 100.0% |

These results came from executing local policy rules on the same 40 proposed cases. The baseline deliberately omits checks to demonstrate diagnosis and remediation. They do not measure the existing Compass AI deployment or establish production reliability. Latency is measured per execution; demo model fees are zero. Live dollar cost is not estimated without pricing configuration.

## Validation

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend run build
```

## Deployment preparation

`render.yaml` defines a single FastAPI service serving the Next.js static export and a persistent SQLite disk. A paid persistent-disk service is specified; review the current Render plan before deploying. The deployment starts in protected-write mode with an operator token. Public reads expose only fictional demonstration data. Operator-entered reviewer names are not authenticated identities. Do not use this configuration for confidential enterprise data without proper identity, authorization, retention and access controls.

LangSmith is required for live runs and deployment validation. Verify actual trace delivery, model execution and case metadata before declaring live readiness. Render deployment is a separate, not-yet-executed step.
