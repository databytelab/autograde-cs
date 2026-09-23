# AutoGrade CS

AI-assisted grading for computer-science assignments.

Upload a class's notebooks, HTML exports or Python files. AutoGrade reads each one — the code, the output it produced, and the figures it drew — and proposes a score for every criterion in *your* rubric, with written feedback. You check it, change what you disagree with, and approve. Then export to CSV, Excel, PDF, or straight into Canvas.

**Nothing reaches a student or a gradebook until you approve it.**

It runs on your own computer. Your students' work stays there.

---

## Get AutoGrade

There are two ways to get it. Most people want the first.

### 1. Download and run it (for teachers — no coding)

1. Go to the **[Releases page](../../releases/latest)**.
2. Under **Assets**, download **`autograde-v1.0.0.zip`**.
3. Right-click the ZIP → **Extract All…** into a folder you won't delete (Documents is fine).
4. Open the new folder and follow **[INSTALL.md](INSTALL.md)** — you install one free program (Docker Desktop) and double-click **Start AutoGrade**. About 30 minutes, most of it waiting for a download.

That's the whole installation. You never edit a settings file or type a command.

### 2. Run it from the source code (for developers)

```bash
git clone https://github.com/databytelab/autograde-cs.git
cd autograde-cs
```

Then either:
- **Docker (same as the ZIP):** double-click **Start AutoGrade** (Windows) or run `./autograde.sh start` (Mac/Linux).
- **From a Python virtualenv, with hot-reload for development:** double-click **Start Dev.bat**, or see **[docs/developer/DEVELOPMENT.md](docs/developer/DEVELOPMENT.md)**.

---

## The guides

| Read this | When |
|---|---|
| **[INSTALL.md](INSTALL.md)** | Setting AutoGrade up for the first time |
| **[AI_PROVIDERS.md](AI_PROVIDERS.md)** | Choosing and setting up the AI that grades — OpenAI, Claude, or a free local model |
| **[USER_GUIDE.md](USER_GUIDE.md)** | Actually grading. Click by click |
| **[CANVAS.md](CANVAS.md)** | Pushing approved grades into your Canvas gradebook |
| **[RUN_AND_SHARE.md](RUN_AND_SHARE.md)** | Starting, stopping, updating, adding a colleague |
| **[BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md)** | Not losing a term's work |
| **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** | Something went wrong |

---

## What it does

- **Reads** Jupyter notebooks, notebook HTML exports, and plain Python — including the outputs and figures a student's code actually produced.
- **Grades** against the rubric you wrote, with per-criterion scores, feedback written for the student, and the grader's reasoning kept as a record.
- **Checks its own arithmetic in Python.** Totals are recomputed, every score is capped at its criterion's maximum, and any criterion the model skipped is filled in and flagged. The model never does the arithmetic that counts.
- **Flags** notebooks that were never run, recorded errors, work that looks AI-generated, and submissions that try to instruct the grader.
- **Finds copying** using code structure rather than text, so renaming variables does not hide it.
- **Exports** CSV, Excel with a per-criterion sheet, per-student PDF feedback sheets, or a direct push to Canvas.
- **Keeps grading when you close the browser.** It runs on your machine, not in the tab.

## What it does not do

- Publish anything on its own. Every grade is a proposal until you approve it.
- Show anything to students. There is no student login.
- Replace your judgement. It is a very fast, very consistent assistant whose work you always check.

---

## Costs

| | |
|---|---|
| AutoGrade | Free |
| Docker Desktop | Free |
| OpenAI or Claude | About 2–4 US cents per submission — roughly $1 for a class of 30 |
| A local model instead | Free, but slower and needs 8 GB of spare memory |

See [AI_PROVIDERS.md](AI_PROVIDERS.md).

---

## Where your data goes

Everything — courses, rubrics, grades, uploaded files, your API key, your Canvas token — stays on your computer.

The one exception is the **text of each submission**, which is sent to whichever AI provider you chose so it can be graded. OpenAI and Anthropic both state that data sent through their APIs is not used to train their models. Choose the local Ollama option and even that stays on your machine.

Whoever gave you AutoGrade cannot see any of it.

---

## For developers

Working on AutoGrade itself, or running it as a department server for many people, is documented separately:

| | |
|---|---|
| **[docs/developer/DEVELOPMENT.md](docs/developer/DEVELOPMENT.md)** | Running from source, the test suite, building a release |
| **[docs/developer/DEPLOYMENT.md](docs/developer/DEPLOYMENT.md)** | The architecture, and the multi-user server deployment |
| **[docs/developer/HOSTING_OPTIONS.md](docs/developer/HOSTING_OPTIONS.md)** | Where to run it, and who can read the data |
| **[docs/developer/API_REFERENCE.md](docs/developer/API_REFERENCE.md)** | Every HTTP endpoint |
| **[docs/developer/RUBRIC_FORMAT.md](docs/developer/RUBRIC_FORMAT.md)** | The rubric JSON schema |

## Licence

MIT — see [LICENSE](LICENSE).
