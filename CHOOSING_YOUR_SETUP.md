# Choosing how to run AutoGrade

**The trust question, answered honestly.**

You are worried that colleagues will not want to upload their students'
work to a website you run. **That worry is correct, and you should take it
seriously.** This document explains exactly where data goes, what the three
realistic options are, and which one to pick.

---

## 1. The distinction that clears up the confusion

There are **two separate questions**, and mixing them up is what makes this
feel murky:

| | Question | Who controls it |
|---|---|---|
| **A. Storage** | Where do the student files *live*? | Whoever runs the AutoGrade server |
| **B. Processing** | Who does the AI call go to? | Whoever's API key is used |

They are independent. The "bring your own key" feature answers **B** — it
lets a professor use their own OpenAI account, so the AI call happens under
*their* contract and *their* bill.

**It does not answer A.** Their students' files are still stored on
whatever server AutoGrade is running on. If that is your machine, you have
their data.

So: *BYOK does not make a hosted service private.* Only where you run the
server does that.

---

## 2. What actually happens to a submission

Trace it end to end, with no hand-waving:

1. The instructor uploads `alice_hw3.ipynb` in their browser.
2. It travels over HTTPS to the AutoGrade server.
3. **It is written to that server's disk**, in the `uploads` volume, as an
   ordinary file.
4. It is parsed and the parsed text is stored in **that server's
   PostgreSQL database**.
5. The text of the submission is sent to the AI provider (OpenAI, Claude,
   or a local model) to be graded.
6. The grade and feedback are stored back in that database.

Two things follow that you must be able to say out loud to a colleague:

> **Anyone with administrator access to the server can read every
> submission.** Files on disk are plain files; database rows are plain
> rows. Only professors' API keys are encrypted. This is true of nearly
> every hosted tool, but it should be stated rather than glossed over.

> **If you run the server, you are the custodian of their students'
> work** — with whatever that implies under your institution's rules and
> under data-protection law (PIPL in China, GDPR in Europe, FERPA in the
> US).

### About the AI provider

Step 5 sends coursework text to a third party. Two mitigations, both real:

- **OpenAI and Anthropic both state that data sent through their APIs is
  not used to train their models by default.** That is their published API
  policy and it is the main reason API use is defensible where using the
  consumer chat products would not be. Check their current terms yourself
  before you tell a colleague — policies change and you will be quoted.
- **A local model sends nothing anywhere.** With Ollama, step 5 never
  leaves the building. See option 1 and option 2 below.

---

## 3. A second, concrete problem with the shared-website idea

Beyond trust, there is a mechanical blocker.

**The Canvas token is configured once for the whole server, not per
instructor.** Every Canvas push uses that one token, with that one person's
Canvas permissions.

So on a website you host:

- Your Canvas token cannot write grades into a colleague's course, let
  alone another university's Canvas.
- Making it work would mean each professor handing you *their* Canvas API
  token — which acts as them, across all their courses, with full
  read/write. That is a far bigger ask than the files, and most instructors
  should refuse.

Canvas push therefore only really works when AutoGrade is run **by the same
institution whose Canvas it is talking to**. That single fact rules out the
cross-university website more decisively than the trust argument does.

---

## 4. The three ways to run it

### Option 1 — Each instructor runs it on their own computer

**Nothing ever leaves their machine** (and with Ollama, nothing leaves at
all — no internet needed after setup).

- They install Docker Desktop once, then run one command.
- They are their own administrator. You never see their data.
- Realistically ~20 minutes of setup with `RUN_AND_SHARE.md`.

**Good for:** the privacy-maximalist colleague, anyone at another
institution, anyone who says "I'd rather not".

**Cost:** they must install Docker. Their laptop must be on while grading.
Canvas push works, because they use their own Canvas token in their own
`.env`.

### Option 2 — Your university or department runs one instance ⭐

One server inside the university, run by IT or by you on a university VM.
Everyone at the university signs in with a link and a password.

- **Student data never leaves the institution that already holds it.**
  It sits alongside Canvas, on university infrastructure, under university
  policy. That is a completely different conversation from "it's on
  Irfan's computer".
- Colleagues install nothing.
- Canvas push works properly — one institution, one Canvas, one token.
- IT can inspect the code and the deployment before approving it.

**Good for:** essentially everyone at your own university. **This is the
recommended option.**

**Cost:** you need a VM and, ideally, IT's blessing. That conversation is
much easier than it sounds, because you are not asking them to trust a
third party — you are asking to run software on their own hardware.

### Option 3 — You host a public website others sign up to

Easiest for users, hardest for you, and the one you were imagining.

**Good for:** nothing yet. Choose it only if this becomes a product you
intend to support.

**What it would actually require**, none of which exists today:

- A legal entity and a data-processing agreement with each institution
- A published privacy policy and retention schedule
- Encryption of submissions at rest, and an audit log of administrator
  access
- Per-instructor Canvas tokens (§3)
- Self-service account and data deletion
- Security response, uptime commitments, backups you are contractually
  on the hook for
- Somebody paying the AI bill, or per-user billing

That is a company, not a weekend project. Do not start here.

---

## 5. Side by side

| | 1. Their own computer | 2. University-hosted ⭐ | 3. Public website |
|---|---|---|---|
| Where student work is stored | Their laptop | University server | Your server |
| Who can read it | Only them | University IT + you | **You** |
| They install anything? | Docker, once | No | No |
| Canvas push | Works (own token) | Works | **Broken** (§3) |
| Works fully offline | Yes, with Ollama | If Ollama is on the LAN | No |
| Effort for you | Write a guide | One VM | Months |
| Effort for them | ~20 min | Zero | Zero |
| Trust needed in you | None | Some | **A lot** |

---

## 6. What to actually do

**Recommended plan:**

1. **Now — run one instance for your department at Hainan University.**
   Host it on a university machine, not your personal laptop. Invite the
   first 3–5 colleagues (see `RUN_AND_SHARE.md` §14). Their data stays on
   university infrastructure, which is where it already is. This removes
   almost all of the trust problem in one step.

2. **For anyone outside your university, or anyone hesitant — point them at
   Option 1.** "Here is the code and a 20-minute guide; run it yourself and
   I never see anything." Being *able* to say that is itself the strongest
   trust argument you have, whether or not they take it up.

3. **Do not build the public website** unless and until several
   institutions ask for it and someone is funding it properly.

---

## 7. Things that build trust, whichever option you pick

These are cheap and they genuinely help.

**Grade anonymously.** AutoGrade does not need real names to grade — it
judges the code and the output. An instructor can rename files
`s001.ipynb`, `s002.ipynb` before uploading and match names back from the
exported CSV on their own computer. Now even a compromised server holds
coursework with no names attached. **This is the single most effective
privacy measure available today, and it costs one spreadsheet column.**

**Use a local model for sensitive work.** With Ollama, step 5 of §2 never
happens. Grading is slower and small models are more lenient — spot-check
them — but nothing leaves.

**Show them the code.** It is open, readable, and heavily commented. "Read
it yourself, or have your IT read it" is an argument a closed SaaS cannot
make.

**Be specific about what you can see.** Do not say "it's secure". Say: *"I
run the server, so technically I can read files on it. I don't, and here is
how to run it yourself if you'd rather not take my word."* That sentence
earns more trust than any reassurance.

**Delete data when a term ends.** Deleting an assignment removes its
uploaded files. Make it a habit and tell people it is your habit.

**Say what the AI provider does with it.** Point at the provider's API
terms (§2) rather than paraphrasing them.

---

## 8. Quick decision guide

> **Is the instructor at your university?**
> **No** → Option 1. They run it themselves.
> **Yes** ↓
>
> **Can you get a university VM (or has IT agreed)?**
> **Yes** → **Option 2.** Recommended. Everyone signs in, nothing to install.
> **No, only my own laptop** ↓
>
> **Is this a real class's live grades?**
> **No, we're trialling on last term's work** → Fine, run it on your
> machine for the pilot, and be explicit that it is your machine.
> **Yes, live student records** → Do not host other people's live grading
> on a personal machine. Either get the VM, or have them use Option 1.

---

## 9. Sentences you can reuse

**To a cautious colleague:**

> AutoGrade runs on a university server, so your students' files stay on
> university infrastructure — the same place Canvas keeps them. The AI
> grading call goes to OpenAI's API, which under their API terms is not
> used to train their models; you can also use a local model, in which case
> nothing leaves the building. If you would rather not use my instance at
> all, the code is open and you can run it on your own computer in about
> twenty minutes — I have written the guide.

**To your IT department:**

> This is an open-source tool that runs entirely in Docker on one VM:
> a web frontend, an API, a background worker, and PostgreSQL. Only the
> reverse proxy is exposed; the database has no internet access at all.
> Student submissions stay on our infrastructure. The only outbound traffic
> is the grading call to the AI provider, and that can be pointed at a local
> model instead. Grades are proposals — no grade is published without an
> instructor approving it. I would like a VM and a DNS name.

**When someone asks "can you see my students' work?":**

> On my instance, yes — an administrator can read files on the server. I
> don't, but you should not have to take that on faith. Two options: grade
> with anonymised filenames so there are no names in what I hold, or run
> your own copy so I hold nothing at all.
