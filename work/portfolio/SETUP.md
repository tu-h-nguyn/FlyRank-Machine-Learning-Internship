# Going live — the remaining steps

The form is built, tested, and the access key is in place. Two things stand between it
and a real message in the inbox.

## ~~1. Get a free access key~~ — done

Key `88690ebb-…` is set on the `access_key` input in `docs/portfolio/index.html`.
It is public by design: it names a mailbox, it is not a credential. Free tier is 250
submissions a month.

If it ever needs replacing, change **only** the `value="…"` on that input. The string
`PASTE_YOUR_WEB3FORMS_ACCESS_KEY_HERE` appears once more as a constant in the page's
JavaScript and must stay exactly as it is — it is how the page notices an unset key and
shows the yellow "not connected yet" warning.

## ~~2. Paste the key into the page~~ — done

## 3. Merge to `main`

GitHub Pages serves `docs/` from the **`main`** branch, so the page is not public until
this branch is merged. Once it is, wait a minute or two and open:

**https://tu-h-nguyn.github.io/FlyRank-End-to-End-Machine-Learning-Project-Internship/portfolio/**

## 4. The real test — this is the actual deliverable

1. Open that URL **in a private/incognito window**, so you are testing what a stranger
   gets, not something cached.
2. Confirm there is **no yellow warning box** above the form. If there is, the merge
   did not carry the key through.
3. Fill the form in as a stranger would and send it.
4. Confirm you see the **green** "your message is on its way" line.
5. **Check your Gmail.** Check spam too — the first message from a new sender often
   lands there. Mark it "not spam" so later ones arrive properly.
6. Hit **reply** on that email and confirm it addresses the sender, not Web3Forms.

Screenshot the green line and the received email. That pair is your evidence.

## Also worth doing

- **Rewrite `HOW-IT-WORKS.md` in your own voice.** It is correct and the data flow is
  right, but the brief asks for the explainer *in your own words*, and it was drafted
  with an assistant. Read it, make sure you could defend every line of it out loud, and
  say it the way you would say it. That is the part being marked.
- **The CV link is still dead.** In the header, `<a href="#" ...>CV</a>` goes nowhere.
  Point it at your CV PDF or delete the chip — a dead button on a portfolio is worse
  than one fewer link.
- Re-run the test suite any time you touch the form:
  ```
  pip install playwright && python3 work/scripts/test_contact_form.py
  ```

## If a message never arrives

| What you see | What it means |
|---|---|
| Yellow warning above the form | The key reverted to the placeholder — check the merge did not drop it. |
| Red line saying "Invalid access key" | The key was never verified — click the confirmation link Web3Forms emailed you. |
| Red line saying "Could not reach the server" | Network or ad-blocker. Try another network with the blocker off. |
| Green line, but no email | Check spam first. Then confirm the key belongs to the address you are checking. |
