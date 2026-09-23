# Retrospective — Written for the Person I Was in Week 1

**Author:** John (nguyenhoangtuk23hcmus@gmail.com)
**Date:** 2026-08-31
**Project:** Content Refresh Priority Engine (Lane 2 — Refresh / Content Opportunity Scoring)

---

When I started this internship, I thought building an ML model meant choosing the right algorithm. Pick random forest, tune the hyperparameters, get a good accuracy score, done. The first two weeks seemed to confirm that — I ran the starter notebooks, the numbers looked reasonable, and I felt like I was on track.

Week 3 broke that illusion. The moment I decomposed the 90-day metrics window into three 30-day sub-windows and realized that every `*_90d` column — the ones with the highest feature importance in the reference pipeline — literally *contained* the outcome period, everything I thought I knew about building a model had to be rebuilt. The reconstruction error was zero: `impressions_90d = first30 + prev30 + last30`, exactly. The model was not predicting the future; it was reading it.

That was the turning point. Before it, I was following a recipe. After it, I was making decisions about what information the model was allowed to see, and each decision had a cost I could measure. Excluding `days_since_last_update` was the hardest one — it was the signal my Week-4 baseline depended on, and it felt like throwing away the best feature I had. But 68% of pages were updated inside the outcome window. The feature knew the future. I excluded it, watched my baseline collapse to ROC-AUC 0.500, and realized that the collapse was the result: a rule that scores 12 of 18,010 pages cannot rank a queue, no matter how intuitive it feels.

**What changed in how I work:**

First, I stopped trusting metrics at face value. The leaky random forest hit precision@200 of 0.995 — a beautiful number that was a confession, not a result. Now I check what the model could see at the decision point before I read any score. The split-design gap exercise made this concrete: random row split gave PR-AUC 0.760, but grouped-by-client gave 0.718. That +0.042 was client memorisation, and I would never have caught it without running both.

Second, I learned to write claims that match the evidence. Early in the project I wrote things like "the model predicts which pages will decline." By Week 6, I knew that was wrong in two ways: it is association, not prediction in the causal sense; and the model ranks risk, it does not classify. The honest sentence is "the model ranks pages by associated decline risk at precision@50 of 0.88 (base rate 0.616)" — specific, bounded, and falsifiable. That discipline carried into every table and every conclusion in the capstone.

Third, I learned that negative results are results. My Week-4 rule failing was not a setback — it was the clearest finding of the whole project. Word count not surviving as a predictive feature (permutation importance ≈ 0.0009) was not a contradiction of the FlyRank research paper — it was a distinction between an observed state and a predictive signal. Reporting those honestly earned more credibility than any headline number.

Fourth, I learned that a point estimate is a claim, not evidence. After the capstone shipped I went back and attacked my own headline with a client-clustered bootstrap and a permutation test that retrains the whole pipeline on shuffled labels. Part of it held up better than I expected: chance never came close (p = 0.005), and the model beat the rule inside 14 of 18 clients. Part of it did not: the precision@50 gap over the rule, the number I had led with, has a 95% interval of −0.06 to +0.24. It crosses zero. With thirty clients, "44 versus 37 of the top 50" is what happened on this snapshot, not a promise for the next one. The audit also found two numbers in my own write-ups that had drifted from their receipts, which is why every headline number is now checked by a test.

**The three most transferable things I learned:**

1. **Leakage is a design problem, not a debugging problem.** You do not find leakage by looking at residuals. You find it by asking "when in time was this number computed?" for every column, before the model sees any data. The window decomposition diagram I drew in Week 3 has been more valuable than any model architecture I have read about.

2. **A baseline that cannot rank is not a baseline for ranking.** The Week-4 rule was a perfectly good filter. Using it as a ranking baseline was a category error. Knowing the difference between "select a group" and "order a queue" changed how I frame every ML problem now.

3. **The queue is the deliverable, not the model.** Nobody ships a logistic regression. You ship a ranked list with reason codes and confidence labels that an editor can act on in their first hour. The last 30% of the project — building the action queue, assigning reason codes, writing the confidence labels — was where the model became useful to a person who will never see a PR-AUC score.

**What I would build next:** A monitoring layer that re-scores the queue weekly and flags when the model's top-decile hit rate drifts below a threshold. The current pipeline is a single snapshot; the real value comes when someone can watch the predictions play out and retrain when they stop working. I would also bring in the full warehouse data (79M rows) to test whether the model's patterns hold across a much larger, more diverse portfolio — or whether the 30-client slice was too narrow to generalize from.

I started this internship thinking I needed to learn algorithms. I finished it knowing that the hard part is deciding what the model is allowed to see, and saying honestly what it can and cannot do. The model is the easy part. The discipline around it is the work.
