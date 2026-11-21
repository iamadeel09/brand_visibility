# GEO Pulse AI

GEO Pulse AI shows where AI providers mention a brand, how it compares with competitors, and which claims and visibility gaps need attention.

## Run locally

Use Python 3.11 or newer. Run these commands from the project root.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py --theme.base light --theme.primaryColor '#0f9886'
```

Open [the local dashboard](http://localhost:8501). On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`.

- **Overview** displays the visibility score, brand mention rate, competitor scores, and brand mentions by provider.
- **Response evidence** filters the original answer text and detected mentions by provider, buyer question, and whether the brand appeared.
- **Findings & actions** shows visibility gaps, potential misinformation, and the agent’s recommendations.

The app opens in **Demo** with the synthetic AcmeFlow example. Select **Run scan** to generate a synthetic scan from the included backend, or use **Restore bundled example** to return to the original inputs and results. For a custom scan, enter your brand and up to three distinct competitors, edit the five buyer-question fields, and enter verified facts one per line. A scan needs at least one question.

## Live scans

Copy the environment template if you have no local `.env`.

```sh
cp -n .env.example .env
```

Set `OPENAI_API_KEY` in your local `.env` for the default OpenAI provider. To enable additional providers, edit `GEO_PROVIDERS` and supply the corresponding API keys. The optional Anthropic provider also needs the `anthropic` Python package. Start Streamlit with the run command above, select **Live**, and select **Run scan**. Provider requests may consume API credits.

For either mode, **Run scan** calls the backend entry point.

```python
from backend.agent import run_analysis

result = run_analysis(
    brand=brand,
    competitors=competitors,
    queries=queries,
    verified_facts=verified_facts,
    demo_mode=demo_mode,
)
```

The result must include `brand`, `visibility_score`, `mention_rate`, `competitors`, `responses`, `issues`, and `recommendations` with the agreed field names. This frontend interprets visibility and competitor scores as points out of 100 and `mention_rate` as a percentage from 0 to 100. The provider chart calculates its own percentages from `responses[].mentions`. Use issue types such as `visibility_gap` and `potential_misinformation` for the corresponding panels. Unrecognized types appear under **Other findings**.

The sidebar switch selects the results for that mode. A failed Live scan surfaces an error and clears that run’s Live view. Synthetic results are labeled in the header and available in Demo mode.

## Verify

Run syntax and fixture checks from the project root.

```sh
python -m py_compile app.py dashboard.py
python -m json.tool demo_data/sample.json > /dev/null
```

Run the backend tests from the repository root.

```sh
python -m pytest -q
```

For a UI smoke test, run the bundled Demo, filter the response explorer to OpenAI, open a response, and inspect **Findings & actions**. Run **Live** with valid provider credentials and check that the report carries the **Live results** label.

## Project history

The backend and its tests were developed in the [shared EU Brand Visibility repository](https://github.com/danish2k04/EU_brand_visibilty).
