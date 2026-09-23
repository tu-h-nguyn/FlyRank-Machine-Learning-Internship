# Final submission handoff

The capstone code and evidence pack are complete in this directory.

## Required external step

The GitHub connector available to the build session cannot create a new repository. The capstone brief requires a dedicated public repository, so create one empty public repository named:

flyrank-capstone-metering-billing

Then from this directory run:

~~~bash
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/flyrank-capstone-metering-billing.git
git branch -M main
git push -u origin main
~~~

Do not push .env, secrets, app.db, Python caches, or pytest caches.

## Before submission

Run:

~~~bash
pytest -q
PYTHONPATH=. python scripts/evidence_smoke.py
~~~

For a real integration check, also run Docker Compose and the Stripe CLI in test mode using README.md.

The official submission should point the portal to the dedicated repository URL, not to the existing FlyRank-Machine-Learning-Internship repository.
