# TuringTint on Render Free

This package runs independently of your laptop. It serves the website and
source matching against twelve licensed public reference abstracts. The GPU
detector and local writing model are unavailable on this small CPU service.
Authorship scores remain unavailable; source overlap does not establish
plagiarism. An optional Groq writing coach requires a separate free account and
each visitor's explicit choice to send their passage to Groq.

## Deploy step by step

1. Extract the prepared `render-bundle-*.zip` into a new empty folder. The folder
   should directly contain `render.yaml`, `requirements.txt`, `web`, `turingtint`
   and `data`. Publish this curated folder, not the training workspace.
2. Sign in to GitHub and create a **new repository**, for example
   `turingtint-render`. Use a public repository if you want public deployment
   source. Upload all extracted files with their folder structure intact.
   GitHub Desktop can add the extracted folder as a new local repository and
   publish it. Include `.python-version`, `.gitignore` and
   `data/reference.sqlite`; never add an API key or `.env` file.
3. Sign in to [Render](https://dashboard.render.com/), select **New > Blueprint**,
   connect GitHub, and select this new repository. Keep `render.yaml` as the
   Blueprint path and the repository root as the root directory.
4. Review the proposed `turingtint` web service. Its instance plan must be
   **Free**. The Blueprint creates one web service, with no database or disk.
   Create the Blueprint to begin the build.
5. Wait for the service to become **Live**, then open its assigned
   `https://...onrender.com` URL. The exact subdomain is assigned by Render.
   Open `/api/health` on the same hostname to check the JSON health response.
6. Load a sample passage and run a source check. Model assessment should remain
   unavailable. No API key is needed for this base deployment.

The build command is `pip install --no-cache-dir -r requirements.txt`; the start
command is `python -m turingtint.render_server`. The entrypoint uses Render's
`PORT`, binds to `0.0.0.0`, and runs one worker. The Blueprint selects the Render
profile with `TURINGTINT_DEPLOYMENT=render`. Render supplies its external URL;
you do not need to enter your laptop's address. Python 3.12 is selected through
`.python-version`. These settings follow Render's
[Blueprint reference](https://render.com/docs/blueprint-spec) and
[Python version instructions](https://render.com/docs/python-version).

## Optional free writing coach

The website and source check work before this step. To offer the hosted coach,
create a free [Groq account](https://console.groq.com/) and an API key. In the
Render service's **Environment** settings, add `GROQ_API_KEY` as a secret value
and save/redeploy. Keep this key only in Render's environment settings; never
place it in GitHub, the browser, a screenshot, or chat.

The default model is `qwen/qwen3.8-27b`. If needed, set the optional environment
variable `TURINGTINT_GROQ_MODEL` to another compatible model available to your
Groq account; model availability and free quotas can change.

After redeployment, select the Groq coach in the website and enable writing
feedback, explicitly consenting to send the passage to that provider. The
source-only default makes no
external model request. Groq's free usage limits are separate from Render's;
an exhausted quota produces an unavailable coach result while source matching
continues. See [Groq rate limits](https://console.groq.com/docs/rate-limits).
Stay on the free plan; this package provisions no paid model service.

## Hosting limits and data

Render runs the app when your laptop is closed. Free instances sleep after
15 minutes without traffic; opening the site again can take about a minute.
The workspace has a shared monthly free-hours allowance, and bandwidth/build
quotas also apply. With no payment method, exceeding those allowances suspends
services or builds instead of purchasing additional usage. See
[Render's free service limits](https://render.com/docs/free).

The reference database ships with the code and is used read-only. Runtime
filesystem changes are temporary on Render Free. Submitted passages are not
saved by this application; they are sent to the Render server for processing,
and to Groq only when the visitor explicitly selects and consents to that
coach. The hosting/API providers apply their own data policies.

This deployment contains no model weights, training logs, private corpora, HF
credentials, or machine-specific paths. `bundle-manifest.json` records the
packaged files and hashes; `ATTRIBUTION.md` identifies the included reference
abstracts and demo passages. Validation in the development workspace does not
establish detector accuracy or prove a successful cloud deployment.

For updates, prepare a new bundle in the development workspace with
`python scripts/prepare_render.py`, review it, and update this deployment
repository. Do not replace it with a copy of the entire training project.
