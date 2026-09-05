# Where to run AutoGrade

Read this before you share AutoGrade with anyone. It decides who can read your students' work.

---

## 1. The three options

| | **1. Their own computer** | **2. Your university hosts one** ⭐ | **3. You host a public website** |
|---|---|---|---|
| Where student work is stored | Their machine | University server | Your server |
| Who can read it | Only them | University IT, and you | **You** |
| They install anything? | Docker, once | No | No |
| Canvas push | Works | Works | Works, but their Canvas token sits on your server |
| Works with no internet | Yes, with Ollama | If Ollama is on the LAN | No |
| Effort for you | Send the package | One VM | Months |
| Effort for them | ~30 min | None | None |
| Trust needed in you | None | Some | A lot |

**Option 2 for your own university. Option 1 for everyone else. Do not build option 3.**

---

## 2. What happens to a submission

1. The instructor uploads `alice_hw3.ipynb` in their browser
2. It travels over HTTPS to the AutoGrade server
3. It is written to that server's disk as an ordinary file
4. The parsed text is stored in that server's database
5. The text is sent to the AI provider to be graded
6. The grade and feedback are stored back in that database

Two facts you must be able to say out loud:

- **Anyone with administrator access to the server can read every submission.** Files on disk are plain files. Only API keys and Canvas tokens are encrypted.
- **If you run the server, you are the custodian of their students' work**, under your institution's rules and under data-protection law (PIPL, GDPR, FERPA).

### About the AI provider

- **OpenAI and Anthropic both state that API data is not used to train their models by default.** Check their current terms yourself before you quote them.
- **A local model sends nothing anywhere.** With Ollama, step 5 never leaves the building.

---

## 3. Storage and processing are separate questions

| | Question | Who controls it |
|---|---|---|
| **Storage** | Where do the student files live? | Whoever runs the server |
| **Processing** | Who does the AI call go to? | Whoever's API key is used |

"Bring your own key" answers **processing** only. The files still sit on whoever's server AutoGrade runs on.

**A professor using their own API key on your server has not kept their data private.** Only where the server runs decides that.

---

## 4. Canvas

Each instructor connects their own Canvas account, so one instance serves a whole department and every professor pushes into their own courses.

What no engineering can change: a Canvas API token acts as that person, across every course they teach, with full read and write.

- On an instance **you** host, that token sits in **your** database, encrypted with **your** key.
- On an instance **their** department hosts, it sits on their own hardware, encrypted with their own key.

Canvas does not decide whether a shared instance works. It decides whose it should be: the institution whose Canvas it is.

---

## 5. Option 1 — they run it themselves

Send them the ZIP and [INSTALL.md](INSTALL.md). They run one command.

- Nothing ever leaves their machine. With Ollama, nothing leaves at all
- They are their own administrator. You never see their data
- About 30 minutes, most of it Docker downloading

**Good for:** anyone at another institution, anyone hesitant, anyone who says "I'd rather not".

**Cost to them:** they must install Docker, and their machine must be on while grading.

---

## 6. Option 2 — your university hosts one ⭐

One server inside the university, run by IT or by you on a university VM. Everyone signs in with a link and a password.

- Student data never leaves the institution that already holds it
- Colleagues install nothing
- IT can inspect the code and the deployment before approving it

**Good for:** everyone at your own university.

**Cost to you:** a VM, and a conversation with IT — an easy one, because you are asking to run software on their own hardware, not asking them to trust a third party.

**What to ask IT for:**

- A VM that stays on: 4 GB RAM, 10 GB disk
- Docker installed
- A DNS name that resolves on campus
- Ports 80 and 443 open to campus
- Outbound HTTPS to your AI provider

---

## 7. Option 3 — a public website

**Do not build this yet.** It would require, none of which exists today:

- A legal entity and a data-processing agreement with each institution
- A published privacy policy and retention schedule
- Encryption of submissions at rest, and an audit log of administrator access
- Self-service account and data deletion
- Security response, uptime commitments, contractual backups
- Somebody paying the AI bill, or per-user billing

That is a company, not a side project.

---

## 8. What to do

1. **Now** — run one instance for your own department. Host it on a university machine, not your laptop. Invite 3–5 colleagues.
2. **For anyone outside your university** — hand over the package, do not host it. Send the ZIP and INSTALL.md. They add their own AI key and their own Canvas token. Nothing of theirs touches a machine of yours. What you sell is installation, configuration, support and upgrades.
3. **Do not build the public website** unless several institutions ask and someone funds it properly.

---

## 9. Things that build trust, whichever option you pick

- Show them the rubric. The AI is held to it and can never exceed a criterion's maximum
- Show them they approve every grade
- Say which AI provider is used, and that API data is not used for training
- Offer the local-model option to anyone who wants nothing to leave the building
- Tell them where backups live and how long they are kept
- Start with last term's coursework, never live grading

---

## 10. Sentences you can reuse

> "Your students' files are stored on the university's server, alongside Canvas, under university policy. I don't have a copy."

> "Every grade is a proposal until you approve it. The tool never publishes anything on its own."

> "Submissions go to the OpenAI API, which does not use API data for training. If you'd rather nothing left the building, we can run a local model instead."

> "If you'd prefer to run it yourself, here's the package and the guide. It's one command, and then I never see anything."
