# GEO Visibility

**Brand Intelligence for AI Answers**

**When buyers ask AI what to buy, does your brand make the shortlist?**

GEO Visibility is a Streamlit web app for brand and marketing teams working on generative engine optimization (GEO). It runs buyer questions through configured AI providers, measures how often a brand appears and how strongly it is recommended, and compares it with up to three competitors. The report shows the answers behind the numbers, flags potential conflicts with verified company facts, and suggests what to investigate or improve.

Imagine an AI answer calls your product paid-only even though you offer a free plan. A mention count would still look like a win. GEO Visibility lets you read the original answer, spot the discrepancy, and decide what information to make easier for buyers to verify.

## Two-minute demo

The app opens in **Demo** with AcmeFlow, a fictional project management brand. The bundled report contains 15 simulated answers to five buyer questions and runs without API keys.

| AcmeFlow visibility | Brand mention rate | Answers reviewed | Findings |
| :--- | :--- | :--- | :--- |
| **68 / 100** | **60%** (9 of 15) | **15** simulated | **4** |

1. **Overview.** Compare AcmeFlow with TaskPilot, WorkNest, and SprintDeck. TaskPilot leads this sample with **84 / 100**. The provider chart shows where AcmeFlow appeared most often.
2. **Response evidence.** Select **OpenAI** and **Which project management tools have a free plan?** Open the matching answer. It describes AcmeFlow as a paid-only option. The provider name here is a label in the synthetic fixture.
3. **Findings & actions.** Compare the answer with the sample fact that AcmeFlow offers a free plan for up to five users. The report suggests publishing a dated pricing FAQ that states the limit. It also flags buyer questions where competitors appear and AcmeFlow is missing.

Use **Restore bundled example** to reset the demo. The full scenario and answer text are in the [AcmeFlow fixture](demo_data/sample.json).

## Run locally

Use **Python 3.11 or newer**. On macOS or Linux, run these commands:

```sh
git clone https://github.com/iamadeel09/brand_visibility.git
cd brand_visibility
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py --theme.base light --theme.primaryColor '#0f9886'
```

Open [localhost:8501](http://localhost:8501). On Windows PowerShell, use `py -m venv .venv` and `.venv\Scripts\Activate.ps1` for the environment setup. Run the same installation and Streamlit commands from the repository root.

## Run your own scan

1. Enter your **brand** and up to **three distinct competitors**.
2. Enter **one to five buyer questions**. Use questions a potential customer would ask, such as “Which project management tools work well for small agencies?” A neutral question lets the models choose which brands to mention.
3. Optionally, add **verified company facts**, one statement per line. Use facts you can confirm with a reliable source such as your official pricing page or documentation. These facts give the app a reference for checking claims about your brand.
4. Choose **Demo** to test the workflow with synthetic answers, or **Live** to query configured providers. Select **Run scan**, then open the evidence and findings behind the scores.

### Configure Live mode

Copy [`.env.example`](.env.example) to `.env` in the repository root if you do not already have one. Set `GEO_PROVIDERS` to a comma-separated list such as `openai,gemini` and supply a key for each selected provider. With no provider list, the app defaults to OpenAI.

| Value in `GEO_PROVIDERS` | API key variable | Optional model override |
| :--- | :--- | :--- |
| `openai` | `OPENAI_API_KEY` | `OPENAI_MODEL` |
| `gemini` | `GEMINI_API_KEY` | `GEMINI_MODEL` |
| `anthropic` | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL` |

For Anthropic, also run `python -m pip install anthropic` in the virtual environment. If a default model is unavailable to your account, set the corresponding model override to a model your key can access. Restart Streamlit after changing `.env`. Keep API keys in your local `.env`, which Git ignores. Live requests may use API credits.

**Live results** and **Synthetic demo** have separate labels and results. If some provider calls fail, the report lists the failures and scores the usable answers. If every call fails, the app displays an error without substituting demo data.

## What the app fetches and how it works

The scanner sends each buyer question and a neutral instruction to each configured model API. It collects the generated answer text and records the provider and question for each response. Brand names, competitor names, and verified facts are used by the local analysis stage. The scan measures answers from the configured APIs under the questions you chose.

| Stage | What it does | Code |
| :--- | :--- | :--- |
| Scan | Runs provider requests concurrently and records successful answers and failures. Custom Demo scans generate synthetic responses locally. | [Scanner](backend/scanner.py) |
| Analyze and compare | Detects mentions in the answer text, scores their strength, ranks competitors, and identifies questions where a competitor appears while the brand is absent. | [Analyzer](backend/analyzer.py) |
| Check claims | TruthGuard compares statements about the brand with supplied facts. It flags certain numeric discrepancies and cases that need manual review. | [TruthGuard](backend/truthguard.py) |
| Prioritize actions | The Python agent ranks findings, pulls supporting evidence, and returns up to three suggested actions with reasons. | [Agent](backend/agent.py) |
| Present the results | Streamlit provides the input form, report views, and evidence filters. Plotly draws the competitor and provider comparisons. | [App](app.py) and [dashboard](dashboard.py) |

The website calls `backend.agent.run_analysis` with the brand, competitors, questions, verified facts, and scan mode. The function returns visibility and mention scores, competitor scores, response evidence, findings, and recommendations. The dashboard validates that result before displaying it.

### How to read the scores

- **Brand mention rate** is the percentage of usable answers that mention the brand. A negative mention still counts as an appearance.
- **Visibility score** assigns each usable answer a score from 0 to 3 for the brand, then scales the average to 100. The rules distinguish no mention, a passing or negative mention, stronger placement, and a clear recommendation. Competitors use the same scale.
- **Potential misinformation** is a review queue. Compare the evidence with the supplied fact and check the primary source before acting.

## Verify the project

From the repository root, with the virtual environment active:

```sh
python -m py_compile app.py dashboard.py
python -m json.tool demo_data/sample.json
python -m pytest -q
```

The [backend test suite](tests/test_backend.py) covers scoring, mention detection, fact checks, provider failure handling, and the analysis workflow. To verify the interface without credentials, follow the three-step demo above.

## Limitations

- **Coverage depends on the scan.** Model, prompt wording, and run time can change the answers. Use the same questions and providers when comparing runs, and check for failures that reduced coverage.
- **Scoring and fact checks are rule-based.** Subtle recommendations, aliases, or nuanced claims can be missed. Claim checks depend on the quality and completeness of the facts you supply.
- **Recommendations require human judgment.** They suggest what to investigate or update. Teams verify the evidence and decide what to publish.

The frontend and backend were developed for the same hackathon project. The backend and tests originated in the [shared EU Brand Visibility repository](https://github.com/danish2k04/EU_brand_visibilty).
