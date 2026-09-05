# Setting up the AI

AutoGrade needs one AI account to read submissions and propose grades. You set this up once, inside AutoGrade, under **Settings → AI providers**. You never edit a file.

## Which one should I choose?

| | **OpenAI** | **Claude** | **Ollama** |
|---|---|---|---|
| Cost | About 2–4 US cents per submission | About the same | Free |
| Setup time | 10 minutes | 10 minutes | 30 minutes |
| Needs a card | Yes | Yes | No |
| Student work leaves your computer | Yes, to OpenAI | Yes, to Anthropic | **No** |
| Grading speed (30 students) | 10–20 minutes | 10–20 minutes | 30–90 minutes |
| Quality of grading | Best | Best | Good, and more lenient |
| Needs a powerful computer | No | No | Yes — 8 GB of free memory |

**If you are not sure, choose OpenAI.** It is the quickest to get working, and a whole class costs less than a coffee. You can change your mind later, and you can set up more than one.

**Choose Ollama** if your department requires that student work never leaves the machine, or if you would rather not pay per use.

---

# Option 1 — OpenAI

## 1a. Create an API account

**Important:** a **ChatGPT Plus** subscription is *not* API access. They are separate products with separate bills. Paying for ChatGPT gives you nothing here, and setting this up does not require you to have ChatGPT.

1. Go to **<https://platform.openai.com>**
2. Click **Sign up**, or **Log in** if you already have an OpenAI account
3. Confirm your email address, and your phone number if it asks

## 1b. Add a payment method

An API account with no credit cannot grade anything.

1. Click your icon at the top-right → **Billing**
2. Click **Add payment details**
3. Add a card, and add **$10** of credit. That is far more than a term of grading for one class
4. *Optional but recommended:* set a monthly limit under **Limits** — $20 is plenty, and it means a mistake cannot become an expensive mistake

## 1c. Create the key

1. Go to **<https://platform.openai.com/api-keys>**
2. Click **Create new secret key**
3. Name it `AutoGrade`
4. Click **Create secret key**
5. **Copy it now.** It starts with `sk-` and is shown only once. If you close the box without copying, delete it and make another — nothing is lost

## 1d. Put it into AutoGrade

1. In AutoGrade, click **AI providers** under **Settings** in the sidebar
2. Click the **OpenAI** tab
3. Paste the key into **API key**
4. Leave **Model** as `gpt-4o` — it is the recommended one
5. Click **Save key**
6. Click **Test connection**

**Expected result:** a green message saying it worked, and the top of the page says *Grading is set up*.

### Which model?

| Model | When |
|---|---|
| `gpt-4o` | The default. Reads code, printed output and figures. Use this |
| `gpt-4o-mini` | About a tenth of the cost, slightly less careful. Fine for a first trial |

---

# Option 2 — Claude

**Important:** a **Claude Pro** subscription is *not* API access. They are separate products with separate bills.

## 2a. Create an API account

1. Go to **<https://console.anthropic.com>**
2. Click **Sign up**, or log in
3. Confirm your email address

## 2b. Add credit

1. Open **Billing** from the left-hand menu
2. Click **Add credit** and add **$10**

## 2c. Create the key

1. Open **API keys** from the left-hand menu
2. Click **Create key**
3. Name it `AutoGrade`
4. **Copy it now.** It starts with `sk-ant-` and is shown only once

## 2d. Put it into AutoGrade

1. In AutoGrade, click **AI providers** under **Settings**
2. Click the **Claude** tab
3. Paste the key into **API key**
4. Leave **Model** as `claude-opus-5`
5. Click **Save key**
6. Click **Test connection**

**Expected result:** a green message saying it worked.

### Which model?

| Model | When |
|---|---|
| `claude-opus-5` | The default. The most careful grader |
| `claude-sonnet-5` | Faster and cheaper, still very good |
| `claude-haiku-4-5-20251001` | Cheapest. Good for trying AutoGrade out |

---

# Option 3 — Ollama, on your own computer

Nothing leaves your machine, and there is nothing to pay. In exchange it is slower, and the grades need more checking.

## 3a. Check your computer is up to it

| Model | Free memory needed | Notes |
|---|---|---|
| `qwen2.5:3b` | about 4 GB | Fastest. Marks generously — check its work |
| `qwen2.5-coder:7b` | about 8 GB | **The sensible default** |
| `qwen2.5-coder:14b` | about 16 GB | Better, needs a strong machine |

To see how much memory you have: press **Ctrl+Shift+Esc**, click **Performance**, click **Memory**. You want at least 16 GB total to run the 7b model comfortably alongside everything else.

A graphics card (NVIDIA) makes this several times faster, but is not required.

## 3b. Install Ollama

1. Go to **<https://ollama.com/download>**
2. Click **Download for Windows**
3. Run the installer and accept the defaults
4. Ollama now runs in the background whenever your computer is on. Its icon appears in the system tray, near the clock

## 3c. Download a model

1. Press the **Windows key**, type `powershell`, press **Enter**
2. Type this and press Enter:

```bash
ollama pull qwen2.5-coder:7b
```

It downloads about 5 GB. This happens once. Leave the window open until it says `success`.

3. Check it arrived:

```bash
ollama list
```

**Expected result:** a list containing `qwen2.5-coder:7b`.

## 3d. Connect AutoGrade to it

1. In AutoGrade, click **AI providers** under **Settings**
2. Click the **Local model (Ollama)** tab
3. Leave the **Ollama address** exactly as it is: `http://host.docker.internal:11434/v1`
4. Click **Detect models**
5. Choose `qwen2.5-coder:7b` from the list that appears
6. Click **Save**
7. Click **Test connection**

**Expected result:** a green message, and the top of the page says *Grading is set up*.

### Why that odd address?

AutoGrade runs inside Docker, which is like a small separate computer inside yours. Inside it, `localhost` means *AutoGrade itself*, not your machine — so `http://localhost:11434` would look in the wrong place and find nothing.

`host.docker.internal` is the name Docker provides that means *the computer Docker is running on*. That is where Ollama is. This is why the address looks strange, and why you should not "fix" it to `localhost`.

### If Ollama runs on a different computer

Put that computer's address in instead, for example `http://192.168.1.20:11434/v1`. On that machine, Ollama must be started with `OLLAMA_HOST=0.0.0.0:11434` and port 11434 allowed through its firewall.

**Ollama has no password.** Only do this on a network you trust — never expose it to the internet.

### Check the grades before you trust them

Small local models are noticeably more generous than the hosted ones. In our own testing, `qwen2.5:3b` gave full marks to a submission that both hosted models marked down.

Grade five submissions you have already marked yourself, and compare. If the scores are consistently too high, use a larger model or switch to OpenAI for real coursework.

---

# Everyday questions

**Where is my key stored?**
Encrypted, in AutoGrade's database on your computer. After you save it, AutoGrade shows only the last four characters and there is no way to read it back. If you lose your copy, click **Replace this key** and paste a new one.

**How much will this cost?**
With `gpt-4o`, roughly 2–4 US cents per submission, so a class of 30 is about $1. Figures cost slightly more than code alone. You can watch the running total on your provider's usage page.

**Can I use more than one?**
Yes. Set up as many as you like, and click **Use this for grading** on whichever should be active. Switching takes one click.

**My key stopped working.**
Keys can be revoked, expire, or run out of credit. Click **Test connection** — the message says which. Then either add credit at the provider, or use **Replace this key**.

**Can I stop AutoGrade using my key?**
Click **Remove key**. AutoGrade forgets it. Also delete it at the provider if you no longer want it to exist at all.

**Does my key work for other people using my AutoGrade?**
No. Keys belong to the account that saved them. Nobody else on your AutoGrade can see or use yours, including anyone you add as a colleague.
