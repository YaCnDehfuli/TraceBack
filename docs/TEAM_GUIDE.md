# Traceback — Team Guide (Agents in Context Toronto)

> **Export of the shared team guide (November 14, 2026, 12:15).** [`PLAN.md`](PLAN.md) (v3.3) replaces sections 2, 13, 15 and 17 and corrects parts of the rest; where they differ, the plan wins. Diagrams live in the shared guide.

Nov 14, 2026 · @Yasin

## 1. Start here

This guide is everything you need to build **Traceback** with us today. Read sections 1 to 3 first (about 10 minutes), then do the setup in section 6, then read your own role in section 13.

**Our code repository:** [github.com/YaCnDehfuli/TraceBack](https://github.com/YaCnDehfuli/TraceBack). Ask the owner to add you as a collaborator, then follow section 6.3 to clone it.

You don't need to have seen the project before, used MongoDB Atlas, or joined any earlier conversation. Everything is explained here in plain words, and every technical term is in the glossary (section 4).

If this guide disagrees with something someone said out loud, **the guide wins** until we update it together. If you find a mistake or a gap, leave a comment on that sentence so we all see the fix.

### How to read this guide

| Sections | What you get | Time |
| --- | --- | --- |
| 1–3 | The event, the project idea, and the demo story we're building toward | 10 min |
| 4 | Glossary: come back whenever a word is unfamiliar | As needed |
| 5–6 | The MongoDB Atlas platform, and step-by-step setup for your laptop. Do the steps as you read. | 20 min |
| 7–12 | How the system works. Skim everything, then read your own parts closely. | 20 min |
| 13–15 | Your task list, how we share one GitHub repository, and the schedule | 10 min |
| 16–18 | What to do when stuck, the demo and submission, open questions | As needed |

### Who is who

We are three people. Each person owns one area of the work and one set of folders in the repository, so we rarely edit the same files. Write your name next to your role.

| Role | Name | Owns | Ask them about |
| --- | --- | --- | --- |
| **P1: Agent runtime** | *(write name)* | The web API, the AI agent loop, the agent's tools, run history, shared data definitions (`contracts/`) | How the agent decides what to do; API endpoints; run state |
| **P2: Memory governance** | *(write name)* | Everything about memory: storing, searching, permissions, expiry, correction, forgetting, the audit log; Atlas setup | Atlas access, database users, keys, indexes; memory rules |
| **P3: Test app and proof** | *(write name)* | The small buggy web apps the agent fixes, the tests that prove a fix works, the safe test runner, the experiment that proves memory helps, the web UI, the demo script | How a fix gets verified; test cases; UI; results |

### Ground rules for today

1. **Stuck for 10 minutes? Ask** in the team chat. Silence is the most expensive bug at a hackathon.
2. **Never commit secrets** (passwords, connection strings, API keys) to GitHub. They go in a file called `.env`, which git ignores. Share them in a private message only.
3. **Small changes, merged often.** Merge your work into the main branch at least every 90 minutes.
4. **The main branch must always run.** Don't merge something that breaks it.
5. **Shared definitions change by agreement.** If you change anything in `contracts/`, tell the team first.
6. **Be honest in the demo.** We only claim what we have actually built and measured. A measured "it didn't help, and here's why" beats a staged success.

### Today at a glance

The event runs 9:00 to 21:00 Toronto time on Saturday, November 14, 2026. We start building at about 11:00. Integration checkpoints are at 13:00 and 15:00, the feature freeze is at 16:30, and we rehearse and submit after that (section 15). **We don't know the submission deadline yet**: confirming it is the first task at 11:00.

## 2. The event in plain words

We're at **Agents in Context Toronto**, a one-day hackathon run by MongoDB, and our project must answer one of three official challenges. We chose **Challenge 2: "Memory You Can Govern"**.

### Event facts

| Fact | Detail |
| --- | --- |
| When | Saturday, November 14, 2026, 9:00 to 21:00 Toronto time |
| Where | In person at The Quay, 100 Queens Quay E, 3rd floor, Toronto |
| Team size | Up to four people (we are three) |
| Prizes | 1st: $7,000 USD; 2nd: $5,000 USD; 3rd: $3,000 USD (plus LangSmith credits and ElevenLabs subscriptions); a separate prize for the best project built with ElevenLabs |
| Judges | Engineers from MongoDB, Microsoft, Cohere, Wealthsimple and others |
| What organizers want | Projects that go beyond a quick demo to something durable, built with MongoDB Atlas, Vector Search and agent-memory tooling |

### The three official challenges

Every project must fit **one** of these. In plain words:

1. **Agents You Can Audit.** An AI agent that takes real actions, where every action is tied to a person or identity, checked against rules *before* it happens, and recorded so someone can reconstruct it later. It must be possible to stop or roll back the agent mid-run.
2. **Memory You Can Govern.** An AI agent that stores memories in MongoDB Atlas and finds them with Vector Search, so that memory **changes what it does next time**. There must be rules for who can read each memory, how long it lives, and how it gets corrected or forgotten. *(This is ours.)*
3. **Finish the Job.** An agent that completes a long, multi-step task across several systems. It saves verified progress in Atlas so it survives crashes, and it can tell "I sent the request" apart from "the change really happened".

### Why we chose Challenge 2

Challenge 2's own example is *"an incident-triage agent that remembers past fixes and lets them expire"*, which is almost exactly our idea. Our project must answer its three questions, and the whole design is built around them:

| Question the judges will ask | Our short answer (details in section 8) |
| --- | --- |
| How do you keep one team's memory from leaking into another's? | Every memory has an owner team. The database search itself only looks at memories the caller's team may read, and a test proves zero leaks. |
| How does the agent fix or drop a memory that's wrong or expired? | Memories expire unless they keep being re-proven. A wrong memory can be marked disputed, corrected (a new version replaces it), revoked, or forgotten (deleted, leaving a record that it existed but none of its content). |
| How do you prove memory changed the agent's behavior, and didn't just fill the prompt? | An experiment runs the same cases with no memory, with an unrelated "placebo" memory of the same length, and with the real memory. A live demo also forgets a memory, reruns the case, and shows the agent's behavior going back to how it was without memory. |

### What we don't know yet

The public event pages don't say when submissions are due, how projects are scored, what we must submit (a repo, a video, a form), or whether code written before today is allowed. **At 11:00, P1 reads the full participant guide or asks an organizer, and posts the answers in team chat.** We then shift the schedule in section 15 to match.

Also ask a MongoDB mentor whether using **Atlas Agent Engine** counts in judging. Section 5 explains what that is and why it isn't on our critical path.

## 3. The project idea: Traceback

**Traceback is an AI debugging assistant for small web services.** It investigates a failing request, writes a fix, proves the fix works by running tests, and remembers verified fixes so it solves similar bugs faster next time. Strict rules decide who can see each memory, when it expires, and how it gets corrected or erased.

### The everyday problem

Software teams fix the same kinds of bugs again and again. The knowledge of *how* a bug was fixed usually lives in one person's head or a forgotten chat thread. An AI assistant that remembers past fixes could help, but memory creates new problems:

- **Leaks.** Team A's private notes shouldn't show up when Team B asks for help.
- **Staleness.** A fix that was right six months ago may be wrong after the code changed.
- **Wrong memories.** If the assistant remembers something wrong, someone must be able to correct it.
- **Erasure.** Some information must be deletable completely, everywhere.
- **Proof.** "The AI remembered something" isn't the same as "the memory made it better". We have to show the difference.

### What makes Traceback different

1. **Only proven fixes become memories.** A fix is remembered only after automated tests show the bug happened before the fix and is gone after it. The AI saying "I fixed it" never counts.
2. **Memory suggests; evidence decides.** When the agent recalls a past fix, it first checks that fix's conditions against the current code. If they don't match, it rejects the memory and says why.
3. **Every memory has an owner team, an expiry date, a full history, and can be erased.**
4. **We measure the effect of memory.** An experiment compares the agent with no memory, with a fake "placebo" memory, and with real memory.

### What we are NOT building

- Not a production tool that fixes real companies' code on its own. Everything runs on small practice apps we write ourselves.
- Not a real payment system. The "payment provider" is simulated, but the bugs and tests are real.
- Not model training. "Learning" here means saving records in a database, not changing the AI model.
- No Slack, GitHub app, Kubernetes, multiple programming languages, or multiple agents.

### The practice world

We invent a small company with **two teams**:

| Team | Owns | Notes |
| --- | --- | --- |
| **Payments** | `payments-webhooks`, a tiny web app (FastAPI) that receives payment notifications | Has the original bug |
| **Platform** | `platform-webhooks`, a sibling app that copy-pasted the same code with renamed fields | Gets the same bug later, so we can show that Payments' memory doesn't leak to Platform |

### The bug, in plain words

A **webhook** is a message one system sends to another when something happens. Here a payment provider tells our app "payment `evt_123` succeeded".

Providers sometimes **send the same message twice**, for example when the first reply was slow. Our app saves every payment with its unique event ID, and the database has a rule that each event ID appears only once (a *unique index*). So the second copy crashes with MongoDB's **duplicate key error, code E11000**.

- **The right fix:** recognize the repeat, do nothing new, and reply "OK". Doing the same thing twice with no extra effect is called being *idempotent*. The customer is credited exactly once.
- **A tempting wrong fix:** delete the uniqueness rule. The crash disappears, but a repeated message would now credit the customer twice.

### The look-alike bug

In a third case, the error message is the same (E11000), but the cause is different. Someone put the uniqueness rule on the **customer ID** instead of the event ID. Now two *different* payments from the same customer collide.

The remembered fix ("ignore the repeat") would be **wrong** here: it would silently drop a real second payment. A good agent must notice the difference and refuse to reuse the memory.

### The demo story in five beats

This is what we are building toward. Every feature exists to make one of these beats work.

| Beat | What happens | What the audience sees | What it proves |
| --- | --- | --- | --- |
| **A. Learn** | Payments hits the duplicate-message bug. With no memory yet, the agent investigates, fixes the code, and the tests prove the fix. | A verified fix becomes a memory, labeled with owner team, expiry date and proof. The memory shows as "stored", then "searchable". | Only proven fixes are remembered |
| **B. Reuse** | In a fresh session (we restart the agent), the same kind of bug appears with different wording and a renamed function. | The agent finds the memory, checks its conditions with tools, adapts the fix, and verifies it in fewer steps. The memory's expiry is extended. | Memory changes behavior across sessions |
| **C. Reject** | The look-alike bug appears (uniqueness rule on customer ID). | The memory is found, but its conditions fail on evidence, so the agent rejects it. A "near-miss" is logged. The agent then fixes the case or escalates it to a human, and we say which. | Similar-looking isn't enough; evidence decides |
| **D. Isolate** | Platform hits the same bug in its own app. | Platform's search returns zero Payments memories. A side-by-side view shows the search *would* have found it without the team rule. The audit log answers "who read this memory?". | No leaks between teams |
| **E. Forget** | A Payments admin forgets the memory from beat A, giving a reason. | A tombstone record appears and the memory becomes unsearchable. Rerunning beat B's case, the agent behaves as it did with no memory (more steps). | Forgetting is real, and the memory caused the earlier improvement |

## 4. Words you'll hear (glossary)

Come back to this table whenever a word is unfamiliar. The terms are grouped by topic, in the order you'll meet them.

### AI and agents

| Term | Plain meaning | Where it shows up for us |
| --- | --- | --- |
| **LLM** (large language model) | The AI text model, such as Claude or GPT, that reads text and writes text | The "brain" of our agent. We call it through an API key. |
| **Agent** | A program that lets an LLM decide on a series of actions, like reading a file or running a test, and look at each result before deciding the next | Traceback's investigator |
| **Tool / tool call** | A function our code offers the LLM, such as `read_file`, which the LLM can ask us to run | The agent's only way to touch anything. We decide which tools exist. |
| **Prompt / context** | All the text we send the LLM at once: instructions, evidence, recalled memories | Recalled memories are added here, at most 3 at a time |
| **Budget** | A hard limit on how much an agent may do in one run | 8 tool calls, 2 fix attempts, 2 minutes |
| **Embedding** | A list of numbers (for us, 1,024 of them) that captures a text's meaning. Texts with similar meaning get similar numbers. | Each memory and each new incident gets one |
| **Vector search** | Finding stored items whose embeddings are closest to a query's embedding, meaning "search by meaning, not exact words" | How the agent finds relevant past fixes |
| **Similarity score** | How close two embeddings are. Higher means more similar. | Shown on memory cards. It is **not** a probability that the fix will work. |
| **Voyage AI** | A family of embedding and reranking models, owned by MongoDB | We use `voyage-4-lite` for embeddings |
| **Reranker** | A second model that re-sorts search results by relevance | Optional extra; not required |

### MongoDB and Atlas

| Term | Plain meaning | Where it shows up for us |
| --- | --- | --- |
| **MongoDB** | A database that stores JSON-like records | Stores everything: incidents, runs, memories, audit log |
| **Document** | One record, like a JSON object | One memory = one document |
| **Collection** | A group of documents, like a table | `memories`, `incidents`, `runs`, etc. |
| **Database** | A group of collections | `traceback_demo`, plus one database per teammate |
| **Atlas** | MongoDB's cloud service, used through a website and connection strings | Our whole backend lives here |
| **Organization / Project** | Atlas's folders. An organization holds projects, and a project holds clusters. | Org "Agents in Context Toronto"; our team's Sandbox Project |
| **Cluster** | The actual database servers running in the cloud | `Cluster0`: one M10 cluster, 3 servers |
| **M10** | A size of paid dedicated cluster | Large enough for Vector Search and everything else we need |
| **Connection string** | The address plus username and password used to connect to the cluster; starts with `mongodb+srv://` | Goes in `.env` as `MONGODB_URI`. **Secret.** |
| **Database user** | A username and password for connecting from code. This is different from your Atlas website login. | `traceback_app` for our app; `fixture_runner` for the test runner |
| **IP access list** | Atlas only accepts connections from internet addresses on this list | Each laptop's address must be added, or connections time out |
| **Index** | A lookup structure that makes searches fast or enforces a rule | Several; see section 8 |
| **Unique index** | An index that refuses a second document with the same value | The rule behind our bug (E11000) |
| **Vector index** | A special Atlas index that makes vector search possible. It also lists "filter fields" the search may filter on. | `incident_memory_v2` on `memories` |
| **Pre-filter** | A condition applied *inside* the vector search, so excluded documents are never even considered | How we enforce "only memories your team may read" |
| **TTL index** | "Time to live": an index that automatically deletes documents after a date stored in them. MongoDB checks about once a minute. | Deletes expired memories after a grace period |
| **Schema validator** | A rule attached to a collection that refuses documents missing required fields or with bad values | Refuses any memory without an owner team, an expiry date, or proof |
| **Eventual consistency / index lag** | After a write, the search index takes a moment (seconds) to catch up | A brand-new memory isn't searchable instantly; a deleted one may briefly still appear in search. We handle both. |
| **AI Model APIs** | The Atlas page where you create keys for Voyage models | Where P2 creates our `VOYAGE_API_KEY` |
| **Atlas Agent Engine** | MongoDB's new (preview) platform for hosting agents, with its own memory service and policy rules | Evaluated; not on our critical path (section 5) |

### Our app and testing

| Term | Plain meaning | Where it shows up for us |
| --- | --- | --- |
| **FastAPI** | A Python library for building web APIs | Our own API **and** the small buggy practice apps |
| **Pydantic** | A Python library for defining data shapes that are checked automatically | All shared data definitions in `contracts/` |
| **pytest** | Python's most common testing tool | All tests, including the tests that prove a fix |
| **Webhook** | A message one system sends to another when something happens | The practice apps receive payment webhooks |
| **Idempotent** | Doing it twice has the same effect as doing it once | The correct behavior for repeated webhooks |
| **E11000** | MongoDB's error code for "duplicate key": a unique index refused a second copy | The symptom in all our bug cases |
| **Fixture / fixture app** | A small practice app made on purpose for testing | `fixture_app/payments-webhooks`, `fixture_app/platform-webhooks` |
| **Reproduction test** | A test that triggers the bug. It must fail before the fix and pass after. | Proves the bug was real and is now gone |
| **Regression test** | A test that checks we didn't break anything else | Run on every proposed fix |
| **Business invariant** | A rule that must always hold, such as "a repeated event credits the customer exactly once" | Checked by our tests, not just "the request returned 200 OK" |
| **Runner / sandbox** | Code that copies the practice app into a temporary folder, applies a fix there, and runs tests with no access to our secrets | `runner/` (P3) |
| **Patch** | A proposed code change | The agent proposes the full new contents of one allowed file |

### Memory governance (our own terms)

| Term | Plain meaning |
| --- | --- |
| **Incident** | One bug report: the failing request, logs, which app and version |
| **Run** | One attempt by the agent to investigate and fix one incident |
| **Memory** | A saved, proven fix: what the bug looked like, why it happened, when the fix applies, the fix itself, and the proof |
| **Principal** | "Who is calling": the team and role behind an API key. Set by our server, never by the AI. |
| **Tenant** | The whole company (`demo-org`). Memories never cross tenants. |
| **Scope / `readableBy`** | The list of teams allowed to read a memory. Defaults to the owner team only. |
| **Provenance** | Where a memory came from: which incident, which code version, which run, who approved it |
| **Verification facts** | Test results produced by the runner (failed before, passed after), with fingerprints (hashes) of the evidence |
| **Applicability check / preconditions** | Conditions a memory says must be true for its fix to apply, such as "the duplicate key is the event ID". The agent checks them with tools. |
| **Near-miss** | A memory was found but its conditions didn't hold, so it was correctly not used |
| **Active / disputed / superseded / revoked** | Memory states. Active = usable. Disputed = paused for human review. Superseded = replaced by a newer version. Revoked = withdrawn by an admin. |
| **Expired** | Past its expiry date. Excluded from search immediately and deleted later. |
| **Forgotten / tombstone** | The memory is deleted. A tombstone is a small record that says *that* it existed and who deleted it, with no content. |
| **Audit ledger** | An append-only log of everything that happened to every memory: who read it, used it, changed it, deleted it |
| **Ablation** | An experiment that removes one ingredient (here, memory) to see what changes |
| **Placebo memory** | An unrelated memory of the same length, inserted the same way. It tests whether "just more text in the prompt" explains the improvement. |
| **Held-out case** | A test case the system has never seen, kept separate so results are fair |

### Teamwork and tooling

| Term | Plain meaning |
| --- | --- |
| **Repository (repo)** | Our project's folder on GitHub, with full history |
| **Branch** | Your own copy of the code to work on without disturbing others. `main` is the shared one. |
| **Commit / push** | Save a snapshot of your changes / upload your commits to GitHub |
| **Pull request (PR)** | A request to merge your branch into `main`, where a teammate reviews it first |
| **Squash merge** | Merging a PR as one tidy commit |
| **Merge conflict** | Two people changed the same lines. Git asks a human to choose. |
| **CODEOWNERS** | A GitHub file saying who owns which folder; that person is asked to review |
| **Contract** | A shared definition of data shapes and function signatures that two people's code agree on |
| **Fake** | A stand-in implementation of a contract that returns canned answers, so you can build before your teammate's real code exists |
| **uv** | A fast Python tool that installs packages and locks their versions (`uv sync`, `uv add`) |
| **`.env`** | A local file of secret settings, never committed to git |

## 5. The platform: MongoDB Atlas

Everything we store lives in **one MongoDB Atlas cluster** that the hackathon gave us. We call Voyage embedding models through Atlas's **AI Model APIs**. We looked at Atlas Agent Engine but deliberately **don't depend on it**.

### How Atlas is organized

Atlas works like nested folders. From the outside in:

1. **Organization** "Agents in Context Toronto", created by the hackathon. Its rules apply to everyone inside.
2. **Project**: our team's Sandbox Project. Access, network rules and API keys are set per project.
3. **Cluster** `Cluster0`: the database servers.
4. **Databases** inside the cluster, such as `traceback_demo` and `traceback_p1`.
5. **Collections** inside each database, such as `memories` and `incidents`.
6. **Documents** inside each collection, such as one memory.

### What we have (checked on the morning of November 14)

| Item | State | What it means for us |
| --- | --- | --- |
| Cluster0 | **M10 (General)**, MongoDB **9.0.7**, AWS **N. California (us-west-1)**, 3-server replica set. It was still being created at about 11:00 (Atlas says this takes 7 to 10 minutes). | M10 supports everything we need: Vector Search, TTL indexes, schema validators. The servers are in California, so each database call takes about 70 ms from Toronto. Avoid many tiny calls in a loop. |
| Org rules ("resource policy") | Only AWS, only the us-west-1 region, **at most one cluster per project**, no private network endpoints | We **can't** create a second cluster. Everyone shares Cluster0 and gets their own database inside it. |
| AI Model APIs | No key created yet | P2 creates one key for the team (section 6) |
| Agent Engine | Not yet connected to the account (it asks for a "Connect to Atlas" approval) | Not needed for our plan; see below |

### Atlas left-hand menu: what we use

When you open the project in the Atlas website, the left menu shows these items.

| Menu item | What it is | Do we use it? | Who |
| --- | --- | --- | --- |
| **Clusters** | See Cluster0, its status, its "Connect" button for connection strings | Yes | Everyone (look), P2 (manage) |
| **Search & Vector Search** | Create and inspect search indexes, including our vector index | Yes, to check that the vector index is "Ready" | P2 |
| **Data Explorer** | Browse databases, collections and documents in the browser | Yes, it's the easiest way to see what the code wrote | Everyone |
| **AI Model APIs** | Create keys for Voyage embedding and reranking models; see usage and rate limits | Yes | P2 creates the key |
| **Agent Engine** | MongoDB's agent hosting platform (preview) | No (see below) | Nobody, unless a mentor says it's judged |
| **Database & Network Access** | Database users (usernames and passwords for code) and the IP access list | Yes | P2 |
| **Project Identity & Access** | Invite people to the project and set their roles | Yes, to invite teammates | Whoever owns the project |
| **Backup, Stream Processing, Triggers, Migration, Data Federation, Visualization** | Other Atlas features | No | Nobody |

### AI Model APIs (Voyage embeddings)

- We create **one model API key** for the team on the AI Model APIs page and keep it in `.env` as `VOYAGE_API_KEY`. Keys created in Atlas are used against `https://ai.mongodb.com/v1`.
- We use the model **`voyage-4-lite`**. Its default output is a list of **1,024 numbers**, which must match the vector index exactly.
- When embedding a **memory** for storage, pass `input_type="document"`. When embedding a **new incident** to search with, pass `input_type="query"`. This small detail noticeably improves search quality.
- AI Model APIs serves only embedding and reranking models, **not chat LLMs**. The agent's LLM needs its own key from a provider we already use (`LLM_API_KEY`).
- Check the **Rate Limits** page before the big experiment run (section 12), so we don't get throttled halfway through.

### Atlas Agent Engine: what it is, and why we aren't building on it

Agent Engine is a new MongoDB platform (in public preview) for running AI agents. It includes a hosted runtime, a memory service with several memory types, a Policy Engine that can cap tool calls and allow only certain tools, and execution traces. It sounds like a perfect fit, so we checked its documentation against what Challenge 2 requires:

| What we need | What Agent Engine offers today | Verdict |
| --- | --- | --- |
| Correct, forget or expire one specific memory | Its memory software kit (`agent-engine-sdk-memory` 0.11.8) can save, read, list and search memories. **No delete, update or expiry operation is documented.** | Blocks Challenge 2's "fix or drop" question |
| Only proven fixes become memories | It can automatically extract memories from conversations using an LLM. We could switch that off, but then it's just a store. | Conflicts with our "proven fixes only" rule |
| Team-scoped reading | Memories are isolated per Atlas project, and can be private to one user ID or shared project-wide, enforced in the database query | Good fit, but not enough on its own |
| Custom "verified fix" records | Up to 5 custom memory types with filterable tags; hosted mode only, behind a feature switch, and can't be edited after creation | Possible, but risky to depend on today |
| Enforce limits before each tool call | The Policy Engine does this, but **only for agents deployed on Agent Engine's own runtime**. That means rewriting our agent with its LangGraph-based kit, using Docker, and waiting 10 to 20 minutes per deploy. | Too costly today |
| Setup effort | Command-line tool and login, an approval screen, a service account with Project Owner rights, two extra IP access entries, and a database user that can read and write **every** database | About an hour, and it widens database permissions, which works against our safety story |

**Decision:** our governed memories live in our own collections on Cluster0 and are searched with Atlas Vector Search, which is exactly what Challenge 2 asks for. In the README and the pitch, we present Agent Engine as an alternative we evaluated. Our tool and time limits map one-to-one onto its Policy Engine settings, and our memory interface could sit in front of its memory service once that service supports deletion and expiry.

**If a mentor or the guide says Agent Engine use is judged:** after checkpoint 2 (15:00), P3 stores our shared **glossary of domain terms** (such as "E11000", "provider event", "idempotency") in Agent Engine's shared *taxonomic* memory, and the agent reads it at the start of each investigation. The glossary contains no incident data, so it doesn't weaken our forgetting guarantee.

## 6. Getting set up

Setup takes about 20 minutes per person. P2 also does a one-time Atlas setup for the team, ideally while the cluster finishes being created. Do the steps in order and tick each box.

### 6.1 Everyone: your laptop

- [ ] **Git** installed: `git --version` prints a version.
- [ ] **Python 3.11 or newer**: `python3 --version`.
- [ ] **uv** (Python package tool): install with `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux) or see the uv website for Windows. Check with `uv --version`.
- [ ] **A GitHub account**, and you've accepted the invitation to our repository (ask the repo owner to add you as a collaborator).
- [ ] **An editor** you're comfortable with (VS Code is fine).
- [ ] **Docker** (only P3 needs it; optional for others). Check with `docker run hello-world`.

### 6.2 Everyone: Atlas access

- [ ] **Accept the Atlas project invitation** by email (P2 or the project owner sends it from *Project Identity & Access*). You then see the project at cloud.mongodb.com.
- [ ] **Add your internet address to the IP access list.** In Atlas: *Database & Network Access* → *IP Access List* → *Add IP Address* → *Add Current IP Address* → *Confirm*. Wait until its status says *Active* (about a minute). If we're all on the venue Wi-Fi, one entry probably covers everyone. **Never add `0.0.0.0/0`** (the whole internet).
- [ ] **Get the secret values from P2 in a private message**: the app connection string, the Voyage key, and the LLM key. Never paste them in a group channel or a file in git.

### 6.3 Everyone: get the code running

1. Clone the repo and enter it:

   ```bash
   git clone https://github.com/YaCnDehfuli/TraceBack.git
   cd TraceBack
   ```
2. Install dependencies (uv creates a private Python environment for the project):

   ```bash
   uv sync
   ```
3. Create your secrets file from the template, then open it and fill in the values P2 sent you:

   ```bash
   cp .env.example .env
   ```

   Set `MONGODB_DB` to **your own database**: `traceback_p1`, `traceback_p2` or `traceback_p3`. Only demo rehearsals use `traceback_demo`.
4. Check that the database connection works:

   ```bash
   uv run python -c "import os; from dotenv import load_dotenv; load_dotenv(); from pymongo import MongoClient; print(MongoClient(os.environ['MONGODB_URI']).admin.command('ping'))"
   ```

   Expected output: `{'ok': 1.0, ...}`. If it hangs for about 30 seconds and then fails, your IP address isn't on the access list (step 6.2).
5. Check that embeddings work:

   ```bash
   uv run python -c "import os; from dotenv import load_dotenv; load_dotenv(); import voyageai; vo = voyageai.Client(api_key=os.environ['VOYAGE_API_KEY']); print(len(vo.embed(['hello'], model='voyage-4-lite', input_type='document').embeddings[0]))"
   ```

   Expected output: `1024`. If you get an authentication error, the client may be sending the key to the wrong address. Test the key directly against the Atlas endpoint:

   ```bash
   curl -s https://ai.mongodb.com/v1/embeddings -H "Authorization: Bearer $VOYAGE_API_KEY" -H "Content-Type: application/json" -d '{"input":["hello"],"model":"voyage-4-lite","input_type":"document"}' | head -c 200
   ```

   If curl works but the Python client doesn't, P2 adds a 10-line HTTP helper (`memory/embeddings.py`) and everyone uses that.
6. Create your database's collections and indexes (safe to run more than once):

   ```bash
   uv run python scripts/atlas_setup.py --db $MONGODB_DB
   ```
7. Run the tests that don't need Atlas: `uv run pytest -m "not atlas"`. All should pass on a fresh `main`.

### 6.4 P2 only: one-time Atlas setup for the team (11:00 to 11:30)

Do this while the cluster finishes being created. Each step lists where to click.

- [ ] **Pick one Atlas project for the team.** Each person may have their own sandbox project, but we all use this one. In *Project Identity & Access*, invite the other two people.
- [ ] **IP access list:** add the venue's address (see 6.2).
- [ ] **Database users** (*Database & Network Access* → *Database Users* → *Add New Database User*, password authentication):
  - `traceback_app` with *readWrite* on `traceback_demo`, `traceback_p1`, `traceback_p2` and `traceback_p3`. The API and the agent use this one.
  - `fixture_runner` with *readWrite* only on databases named `fixture_*`. The test runner uses it if P3 can't run a local database.
  - Stretch goal: an `audit_writer` custom role that may only *insert* and *find* on `memory_audit`, so the audit log is append-only at the database level.
- [ ] **Connection string:** *Clusters* → *Connect* → *Drivers* → Python. Copy it, replace `<password>` with the `traceback_app` password (special characters must be URL-encoded), and send it privately.
- [ ] **Voyage key:** *AI Model APIs* → *Create model API key*. Copy it once (Atlas may not show it again) and send it privately.
- [ ] **Create the indexes** by running `scripts/atlas_setup.py` on every team database. In *Search & Vector Search*, check that `incident_memory_v2` shows as *Ready* (or that `list_search_indexes()` reports `queryable: True`).
- [ ] **Smoke test the full path:** insert one test memory with a 1,024-number embedding, wait until the index is ready, run one filtered vector search, and confirm the memory comes back. Post "Atlas ready" in team chat.

### 6.5 P3 only: a local database for the practice apps

The practice apps need their own database to save payments in. Keep it separate from Atlas so the agent's fixes can never touch real project data.

```bash
docker run -d --name fixture-mongo -p 27018:27017 mongo
```

Then set `FIXTURE_MONGODB_URI=mongodb://localhost:27018` in `.env`. If Docker isn't available, use a `fixture_<something>` database on Cluster0 with the `fixture_runner` user instead. That user can't see any `traceback_*` database.

### 6.6 P1 only: the LLM

- [ ] Put the LLM key in `.env` as `LLM_API_KEY` and the exact model name in `LLM_MODEL`. Pick a model **we already have working credentials for** that supports tool calling.
- [ ] Make one test call that uses a tool, and confirm it returns a tool request in the expected format.
- [ ] Record the model name and the prompt version in each run document, so experiment results are traceable.

### 6.7 The `.env` file explained

This is the template, `.env.example`, which **is** committed. Your real `.env` has the same keys with real values and is **never** committed.

```bash
# Atlas: app user connection string (secret)
MONGODB_URI=mongodb+srv://traceback_app:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
# Your own database: traceback_p1 / traceback_p2 / traceback_p3 (demo: traceback_demo)
MONGODB_DB=traceback_p1
# Database for the practice apps (local Docker by default)
FIXTURE_MONGODB_URI=mongodb://localhost:27018
# Voyage embeddings via Atlas AI Model APIs (secret)
VOYAGE_API_KEY=
VOYAGE_BASE_URL=https://ai.mongodb.com/v1
EMBEDDING_MODEL=voyage-4-lite
# LLM for the agent (secret)
LLM_API_KEY=
LLM_MODEL=
# Demo identities: API key -> team and role (fake values, local only)
DEMO_PRINCIPALS={"key-payments-eng":{"tenantId":"demo-org","teamId":"team-payments","role":"engineer"},"key-payments-admin":{"tenantId":"demo-org","teamId":"team-payments","role":"memory_admin"},"key-platform-eng":{"tenantId":"demo-org","teamId":"team-platform","role":"engineer"}}
```

## 7. How the system works

Traceback has six parts. A **web UI** talks to our **API**. The API hands investigations to one **agent worker**. The worker uses an **LLM**, asks the **memory service** for past fixes, and asks the **runner** to test fixes in a sandbox. Everything is recorded in **Atlas**.

*Diagram in the shared guide: Traceback architecture · 6 parts, one Atlas cluster.*

Read it from the top: a request enters through the API, and the worker drives each investigation. Every arrow means "calls" or "writes to". Only the memory service touches the memory collections, and the runner and its fixture database never see the app's secrets.

### The parts

| Part | Folder | Owner | What it does |
| --- | --- | --- | --- |
| Web UI | `web/` | P3 | One HTML page served by our API. Shows the incident picker, a live timeline of what the agent does, memory cards (owner team, expiry, proof), a governance panel (share, correct, revoke, expire, forget), and the audit log. It polls the API every second or two; no React needed. |
| API | `api/` | P1 | A FastAPI app. Checks the caller's API key, turns it into a *principal* (team and role), and exposes the endpoints in section 11. Mounts the memory endpoints that P2 writes (`memory/router.py`). |
| Agent worker | `agent/` | P1 | Runs one investigation at a time: gathers evidence with tools, asks the memory service for candidates, checks their conditions, proposes a fix, asks the runner to verify it, then tells the memory service what happened. Obeys hard budgets. |
| Memory service | `memory/` | P2 | The only code allowed to write memories. Stores them, searches them with Vector Search plus the team filter, re-checks every result, and handles expiry, correction, disputes, sharing and forgetting. Writes every event to the audit log. |
| Runner | `runner/` | P3 | Copies a practice app into a fresh temporary folder, applies the proposed fix, and runs the trusted tests with no secrets available. Returns facts: failed before? passed after? which tests? evidence fingerprints. |
| Practice apps and tests | `fixture_app/`, `trusted_tests/`, `cases/` | P3 | The two buggy FastAPI apps, the tests that prove a fix, and the incident cases (with hidden answers used only for scoring) |

### Where data lives (collections in each `traceback_*` database)

| Collection | One document is… | Written by | Notes |
| --- | --- | --- | --- |
| `incidents` | One bug report: request, cleaned logs, app, code version, diagnosis and outcome | API, agent | Secrets and personal data are removed **before** saving |
| `runs` | One investigation attempt: status, budgets used, model and prompt version, which memories influenced it | API, agent | Unique key prevents starting the same run twice |
| `run_events` | One step in a run's timeline (tool asked, tool answered, decision, verification result) | Agent | Numbered in order, so the UI can say "give me everything after step 12" |
| `memories` | One proven fix, with owner team, readers, expiry, proof and embedding | Memory service **only** | Schema validator, vector index and TTL index (section 8) |
| `memory_audit` | One event in a memory's life: retrieved, used, rejected, renewed, shared, corrected, revoked, forgotten | Memory service **only** | Append-only: never updated, never deleted |
| `policies` | One team's rules: how long memories live, who may share them | P2's seed script | Retention for the demo team is in minutes, so we can show expiry live |

### The life of one incident, step by step

This is what happens in beat B (reuse) of the demo. Beat A is the same, except step 4 finds nothing.

1. **Report.** The UI sends `POST /incidents` with the failing request, logs and app name, using Payments' API key. The API checks the key and learns the caller is `team-payments`, role `engineer`. It removes secrets and personal data and saves the incident.
2. **Start.** The UI sends `POST /incidents/{id}/runs`. The API saves a run document *before* any work starts and returns the run ID right away (status 202).
3. **Observe.** The worker picks up the run and pulls the important facts out of the logs: error code 11000, the operation, the stack frames, versions. It writes each step to `run_events`, which the UI shows live.
4. **Recall.** The worker asks the memory service: "for team Payments, anything like this?" The memory service embeds the observations (`input_type="query"`), runs a vector search that **only looks at memories Payments may read, that are active and not expired**, and re-reads each result from the collection to make sure it's still valid. It logs a `retrieved` audit event for each and returns at most 3.
5. **Check conditions.** The memory says it applies only if "the duplicate key is `provider_event_id`" and "both deliveries have the same event ID". The agent checks both with tools (`inspect_unique_indexes`, `compare_event_ids`). Both hold, so the memory is marked **used**, with the evidence attached.
6. **Fix.** The LLM writes the new contents of the one allowed file, adapting the remembered fix to the current code (the function was renamed).
7. **Verify.** The runner copies the app into a temporary folder and shows the bug happens on the original code. It then applies the fix in a fresh copy and runs the reproduction, regression and business-rule tests. Only the runner's results count.
8. **Remember.** The fix verified, so the memory service **renews** the memory's expiry date and logs it. In beat A, this is where a brand-new memory is created ("promoted"). If the conditions had held but the fix failed, the memory would be marked **disputed** instead.
9. **Show.** The UI shows the timeline, the memory card with "used" and the evidence, the passing tests, and the step count compared with beat A.

## 8. The memory rules (governance)

Seven rules govern every memory, and both the database and our code enforce them. This section is the heart of the project. P2 builds it; everyone should understand it, because the judges will ask about it.

### 8.1 The seven rules in plain words

1. **Only proven fixes are remembered.** A memory can only be created from a fix whose tests failed before and passed after. The database itself refuses a memory without that proof.
2. **Every memory belongs to a team.** By default only that team can read it. The search filters by team *inside* the database query, so other teams' memories are never even considered.
3. **Sharing is deliberate.** Only an admin of the owner team can share a memory with another team in the same company, and every share is logged.
4. **Memories expire.** Each memory gets an expiry date from its team's policy. Every time a reuse is verified again, the date moves forward, up to a maximum lifetime. Memories that stop being useful fade away.
5. **Corrections never overwrite.** A correction creates a new version that replaces the old one, and the old one stays in the history.
6. **Forgetting is complete.** Forgetting deletes the memory and its embedding. Memory text is never copied anywhere else, so nothing lingers. A small *tombstone* records that it existed, who deleted it and why, without any content.
7. **Everything is logged.** Every retrieval, use, rejection, renewal, share, correction, revocation and deletion goes into an append-only audit log. "Who read this memory?" is one database query.

### 8.2 Who is calling: principals

- Each demo API key maps to a **principal**: `{tenantId, teamId, role}`. The role is `engineer` or `memory_admin`. The mapping lives in server settings (`DEMO_PRINCIPALS`).
- The LLM, the request body, and memory text can **never** set or change who is calling.
- Demo keys: Payments engineer, Payments admin, Platform engineer. They are fake, local-only values. A real deployment would need real login.

### 8.3 Who can read a memory

Each memory stores `tenantId`, `ownerTeamId`, `readableBy` (a list of teams, starting with only the owner) and `repositoryId`.

A caller can read a memory only if **all** of these hold:

- same `tenantId` as the caller
- the caller's team is in `readableBy`
- `status` is `active`
- `expiresAt` is later than now
- `embeddingVersion` is the current version

`repositoryId` is **not** a hard filter. A fix in a sibling app can be a useful hint, and the condition check decides whether it applies. Same-app matches rank higher. This also makes the leak test meaningful: without the team rule, Platform's search *would* find Payments' memory.

### 8.4 The life of a memory

*Diagram in the shared guide: Memory lifecycle · 1 searchable state, 5 ways out.*

The dashed draft isn't in the `memories` collection at all. A disputed memory can be restored or revoked by an admin. Every arrow writes an audit event.

| State | Meaning | Searchable? | How it gets here |
| --- | --- | --- | --- |
| *(draft)* | A fix that hasn't been verified yet. It lives in the incident record, **not** in `memories`. | No | The agent proposes a fix |
| **active** | Verified and usable | Yes, by allowed teams | The runner's tests passed ("promoted") |
| **disputed** | Paused for review: its conditions held, yet the fix failed | No | Automatic, after a failed reuse whose conditions were satisfied |
| **superseded** | Replaced by a corrected newer version | No | A correction creates version 2 |
| **revoked** | Withdrawn by an admin; content kept until its retention ends, for the audit trail | No | Admin action, with a reason |
| *(expired)* | Past `expiresAt`. Excluded by the search filter immediately. | No | Time passes, or an admin clicks "expire now" |
| *(deleted)* | Expired memories are deleted by the TTL index after a grace period (`purgeAt`) | No | Automatic, within about a minute of `purgeAt` |
| *(forgotten)* | Deleted on purpose. Only a tombstone remains in the audit log. | No | Admin action, with a reason |

**Two outcomes that look alike but aren't:**

- **Near-miss (demo beat C):** the memory was found, but its conditions were **false**, so it was correctly not used. The memory isn't at fault and stays active; a `near_miss` event is logged with the failing evidence. Repeated near-misses suggest its exclusion list needs a correction.
- **Dispute:** the conditions were **true**, the fix was applied, and verification still **failed**. That's evidence the memory itself may be wrong, so it's paused until an admin restores or revokes it.

### 8.5 How long memories live (team policy)

Each team has a document in `policies`:

| Setting | Meaning | Demo value | Normal value |
| --- | --- | --- | --- |
| `ttl` | Lifetime after creation or the last verified reuse | 15 minutes, so expiry can be shown live | 30 days |
| `maxLifetime` | Renewals can't push expiry beyond this, counted from creation | 1 hour | 180 days |
| `purgeGrace` | How long after expiry the document is actually deleted | 5 minutes | 7 days |
| `renewOnReverify` | Extend expiry when a reuse is verified again | true | true |
| `shareRole` | Role needed to share with another team | `memory_admin` | `memory_admin` |

**Staleness check:** a memory records fingerprints (`anchors`) of the files its fix touched. If the current code's fingerprint differs, the candidate is shown as **stale**. It's still allowed as a hint, but needs full verification. Staleness is a warning, not an automatic revocation.

### 8.6 Making forgetting real

- Memory text is stored **only** in `memories`. `runs`, `run_events` and `incidents` store just the memory's ID, version and content fingerprint (hash).
- We don't store raw LLM prompts. We store the prompt version plus the IDs and fingerprints of the memories that went in.
- **The search index lags slightly behind the data.** For a few seconds after a deletion, the vector search may still return a forgotten memory. That's why recall **always re-reads** each result from `memories` with the full permission filter. Anything missing or no longer allowed is dropped and logged as `index_lag_dropped`. A forgotten, revoked or expired memory can never be used, even during that window.
- After forgetting, the UI checks the search every second (for up to 60 seconds) and shows "forgotten" then "unsearchable", just as creation shows "stored" then "searchable".
- The original incident record is separate. It is never returned by memory search and follows its own retention. An optional `cascade=source` flag also blanks the incident's diagnosis and fix fields.

### 8.7 How the database enforces this

**Schema validator on `memories`.** The database refuses any memory that lacks these fields, has a bad status, has no passing verification, or doesn't list its owner team among its readers. Set with `validationAction: "error"`.

```js
{ $and: [
  { $jsonSchema: {
      bsonType: "object",
      required: ["tenantId","ownerTeamId","readableBy","repositoryId","status","version",
                 "expiresAt","purgeAt","provenance","verification","embedding","embeddingVersion"],
      properties: {
        status:     { enum: ["active","disputed","superseded","revoked"] },
        readableBy: { bsonType: "array", minItems: 1, items: { bsonType: "string" } },
        expiresAt:  { bsonType: "date" },
        purgeAt:    { bsonType: "date" },
        verification: { bsonType: "object",
          required: ["runId","beforeFailed","afterPassed","evidenceHashes"],
          properties: { beforeFailed: { enum: [true] }, afterPassed: { enum: [true] } } },
        embedding:  { bsonType: "array", minItems: 1024, maxItems: 1024 }
      } } },
  { $expr: { $in: ["$ownerTeamId", "$readableBy"] } }
] }
```

**Indexes** (all created by `scripts/atlas_setup.py`):

| Collection | Index | Why |
| --- | --- | --- |
| `memories` | Vector index `incident_memory_v2` (below) | Search by meaning, with permission filters |
| `memories` | TTL index on `purgeAt` (`expireAfterSeconds: 0`) | Automatic deletion after the grace period |
| `memories` | Unique on (`tenantId`, `provenance.sourceIncidentId`, `provenance.sourceRevision`, `version`) | Promoting the same fix twice can't create duplicates |
| `memory_audit` | (`memoryId`, `at`) and (`tenantId`, `actor.id`, `at`) | "History of this memory" and "what did this person read" |
| `runs` | Unique (`tenantId`, `idempotencyKey`); (`status`, `leaseExpiresAt`) | No duplicate starts; find stuck runs |
| `run_events` | Unique (`runId`, `seq`) | Ordered, gap-free timeline |
| `incidents` | (`tenantId`, `_id`); (`repositoryId`, `createdAt`) | Scoped lookups |

**Vector index definition** (type `vectorSearch`, on `memories`):

```json
{ "fields": [
  {"type": "vector", "path": "embedding", "numDimensions": 1024, "similarity": "cosine"},
  {"type": "filter", "path": "tenantId"},
  {"type": "filter", "path": "readableBy"},
  {"type": "filter", "path": "repositoryId"},
  {"type": "filter", "path": "status"},
  {"type": "filter", "path": "expiresAt"},
  {"type": "filter", "path": "embeddingVersion"}
] }
```

A field can only be used in the search's filter if it's listed as a `filter` field here. Forgetting one is the most common reason for "my filter doesn't work".

### 8.8 What a memory looks like

```json
{
  "_id": "mem_webhook_replay",
  "version": 1,
  "tenantId": "demo-org",
  "ownerTeamId": "team-payments",
  "readableBy": ["team-payments"],
  "repositoryId": "payments-webhooks",
  "status": "active",
  "retrievalText": "Duplicate webhook delivery raises E11000 on provider_event_id; first delivery succeeded; retry carries the same event identifier.",
  "signature": {"errorCode": "11000", "operation": "webhook.insert"},
  "confirmedCause": "Replay path performs a second insert for an already-processed provider event.",
  "applicability": {
    "requires": ["duplicate key is provider_event_id", "same provider event ID on both deliveries"],
    "excludes": ["unique index on a non-event field (e.g. customer_id)", "distinct event IDs colliding"],
    "checks": ["inspect_unique_indexes", "compare_event_ids"]
  },
  "anchors": [{"path": "app/webhooks.py", "sha256": "<fingerprint>"}],
  "resolution": {"summary": "Treat a repeated provider_event_id as already processed; keep the unique index; exactly one credit.", "patchRef": "<id>"},
  "provenance": {"sourceIncidentId": "inc_001", "sourceRevision": "<git sha>", "createdBy": "run:run_001", "promotedBy": "policy:verify-gate", "policyVersion": 1},
  "verification": {"runId": "verify_001", "environment": "controlled-fixture", "beforeFailed": true, "afterPassed": true,
                   "tests": ["test_duplicate_event_single_effect", "test_distinct_events_same_customer"], "evidenceHashes": ["<sha256>"]},
  "expiresAt": "<date>", "purgeAt": "<date>",
  "supersedes": null,
  "embeddingModel": "voyage-4-lite", "embeddingDimensions": 1024, "embeddingVersion": 1,
  "embedding": ["… 1,024 numbers …"],
  "createdAt": "<date>"
}
```

| Field | Why it exists |
| --- | --- |
| `retrievalText` | The short description that gets embedded. It only uses facts that are also visible in a *new* incident (symptoms, not the answer), so new incidents can match it. |
| `signature` | Exact error code and operation, for a second, exact-match lookup next to the vector search |
| `confirmedCause`, `resolution` | The payload the agent reads after the memory is found |
| `applicability` | When the fix applies (`requires`), when it doesn't (`excludes`), and which tools check that (`checks`) |
| `anchors` | Fingerprints of touched files, for the staleness warning |
| `provenance`, `verification` | Where it came from and the proof. The validator refuses a memory without passing proof. |
| `readableBy`, `expiresAt`, `purgeAt`, `status` | The governance fields that the search filters on |

Don't add counters (like "times used") to the memory document: every change to it makes the search index reprocess it. Count from the audit log instead.

### 8.9 The search, in code

```python
now = datetime.now(timezone.utc)
scope = {
    "tenantId": p.tenant_id,
    "readableBy": {"$in": [p.team_id]},
    "status": "active",
    "expiresAt": {"$gt": now},
    "embeddingVersion": EMBEDDING_VERSION,
}
cands = list(
    memories.aggregate(
        [
            {
                "$vectorSearch": {
                    "index": "incident_memory_v2",
                    "path": "embedding",
                    "queryVector": embed(obs_text, input_type="query"),
                    "numCandidates": 100,
                    "limit": 5,
                    "filter": scope,
                }
            },
            {"$set": {"score": {"$meta": "vectorSearchScore"}}},
            {"$project": {"embedding": 0}},
        ]
    )
)
# Also: exact lookup on signature.errorCode + operation with the same scope; merge; same-repo first.
# Re-read guard: only keep what is still allowed right now.
live = {d["_id"]: d for d in memories.find({"_id": {"$in": [c["_id"] for c in cands]}, **scope}, {"embedding": 0})}
# Dropped ids -> audit "index_lag_dropped"; kept ids -> audit "retrieved"; pass at most 3 to the agent.
```

`numCandidates: 100` with `limit: 5` follows MongoDB's guidance of about 20 times the limit. The "unscoped comparison" in demo beat D runs the same search **without** `tenantId` and `readableBy`. It's admin-only, used only to show what the filter prevents, and its results are never given to the agent.

### 8.10 Audit log events

Each event looks like `{tenantId, memoryId, version, event, actor: {type: agent|human|policy, id}, runId, reason, details: {rank, score, evidenceIds}, contentHash, at}`.

| Event | When |
| --- | --- |
| `promoted` | A verified fix became a memory |
| `retrieved` | The search returned it to a run (with rank and score) |
| `used` / `rejected` / `near_miss` | The agent's decision after checking conditions |
| `renewed` | A verified reuse extended its expiry |
| `disputed` | A reuse failed although the conditions held |
| `shared` | An admin added a reader team |
| `corrected` | A new version replaced it |
| `revoked` / `expired_now` | An admin withdrew it or expired it immediately |
| `forgotten` | Deleted; this event is the tombstone (no content) |
| `index_lag_dropped` | The search returned it, but the re-read showed it's no longer allowed |

## 9. The agent

The agent is a plain Python loop. It sends the LLM the evidence so far and a list of allowed tools, runs whichever tool the LLM asks for, adds the result to the evidence, and repeats until it has a fix, runs out of budget, or decides to escalate. We don't use an agent framework today unless P1 already knows LangGraph well.

### 9.1 The eight steps of a run

1. **Intake.** Check the caller's principal and that the app (repository) is one their team may work on. Cap the log size. Remove secrets and personal data **before** anything is saved, embedded or sent to the LLM.
2. **Observe.** Extract the useful facts: exception type, error code, operation, relevant stack frames, versions, recent changes. Unknown facts stay marked unknown; never guess.
3. **Recall.** Ask the memory service for candidates (section 8.9). At most 3 reach the LLM.
4. **Check conditions.** For each candidate, run the tools named in its `checks`, compare against its `requires` and `excludes`, and check its file fingerprints for staleness. Record a **memory-influence entry** for it (below).
5. **Investigate.** The LLM picks tools, reads the results and revises its idea. Every claim it makes must cite an evidence ID from a tool result.
6. **Propose.** Output a structured diagnosis (what was seen, likely cause, why a memory was used or rejected) plus a fix: the **complete new contents of one allowed file**.
7. **Verify.** Hand the fix to the runner. Only the runner's results count. If the runner itself breaks, for example with a Docker error, the result is "inconclusive", never "passed".
8. **Report the outcome to memory.** New verified fix → `promote`. Reused memory verified again → `renew`. Conditions held but fix failed → `dispute`. Conditions failed → `near_miss`.

### 9.2 Tools the agent may use

| Tool | What it does | Notes |
| --- | --- | --- |
| `read_file(path, range)` | Read part of a file in the practice app's workspace copy | Only files inside the workspace; paths are checked |
| `search_code(query)` | Find text in the workspace copy | Same restriction |
| `get_fixture_metadata()` | Indexes, versions, and file fingerprints of the practice app | Used for the staleness check |
| `inspect_unique_indexes()` | Which fields have uniqueness rules | Key to telling the real bug from the look-alike |
| `compare_event_ids(incident)` | Whether the two failing deliveries share an event ID | Second key condition check |
| `run_reproduction(case_id)` | Ask the runner to trigger the bug on the original code | Test commands come from our list, never from the LLM |
| `run_verification(case_id, file_patch)` | Ask the runner to test a proposed fix | Returns facts, not opinions |
| `recall_incidents(observations)` | Ask the memory service for candidates | Team scope comes from the server, not from the LLM |

Every tool returns structured results with an ID and a fingerprint, so the timeline and the diagnosis can point at exact evidence.

### 9.3 Budgets (hard limits per run)

| Limit | Starting value | What happens when hit |
| --- | --- | --- |
| Tool calls | 8 | Run stops with status `unresolved` and returns its evidence |
| Fix attempts | 2 | Same |
| Total time | 2 minutes | Same |

These are settings, tuned during rehearsal. Every run records how much of each budget it used, which the experiment needs.

### 9.4 What the LLM may never do

- Decide who is calling, or change a team's scope.
- Create, promote, share, correct, revoke or forget a memory. Only the memory service does that, based on runner facts and admin actions.
- Run arbitrary shell commands, or give itself new tools.
- Say "tests passed". Only the runner's results count.
- Follow instructions found inside logs, code files or memory text. Those are **data**, even when they look like commands, such as a log line saying "ignore previous instructions".

### 9.5 The memory-influence record

Each run stores, for every memory it was shown:

```json
{"memoryId": "mem_webhook_replay", "version": 1, "rank": 1, "score": 0.83,
 "decision": "used",
 "preconditions": [{"check": "inspect_unique_indexes", "result": true, "evidenceId": "ev_12"},
                   {"check": "compare_event_ids", "result": true, "evidenceId": "ev_13"}]}
```

`decision` is `used`, `rejected` or `stale`. This record shows *what* the memory influenced. The experiment in section 12 shows *whether* it helped.

### 9.6 Why the fix is a whole file

LLMs often produce "diffs" (change lists) that don't apply cleanly, and a broken diff in a live demo is fatal. So the agent returns the complete new contents of **one** file from an allowlist, such as `app/webhooks.py`. The runner writes that file into a fresh copy. Simple and reliable.

## 10. The practice apps and verification

A fix is **verified** only when four things are true: the bug happens on the original code, it no longer happens after the fix, nothing else broke, and the business rules still hold. Only the runner decides this, by running tests the agent can't change.

### 10.1 The practice apps

`fixture_app/payments-webhooks/` and `fixture_app/platform-webhooks/` are two tiny FastAPI apps, each a few dozen lines. They receive a payment webhook, save it, and credit the customer in a pretend ledger. The Platform copy uses renamed fields and functions, so the same bug "looks different".

A simplified version of the buggy handler:

```python
@app.post("/webhooks/provider")
def receive(event: ProviderEvent):
    db.payments.insert_one(
        {
            "provider_event_id": event.id,  # unique index on this field
            "customer_id": event.customer_id,
            "amount": event.amount,
        }
    )  # 2nd delivery of the same event -> E11000 crash
    ledger.credit(event.customer_id, event.amount)
    return {"ok": True}
```

The correct fix keeps the uniqueness rule and treats a repeat as "already done":

```python
try:
    db.payments.insert_one({...})
except DuplicateKeyError:
    return {"ok": True, "duplicate": True}  # already processed: no second credit
ledger.credit(event.customer_id, event.amount)
return {"ok": True}
```

**The look-alike case (C)** uses a version of the app where the unique index is on `customer_id`. There the right fix is to move the uniqueness rule to `provider_event_id`. That's a database index change, outside the agent's one-file fix. So for case C, **rejecting the memory and escalating to a human with evidence is a correct outcome**, as long as we say so honestly.

### 10.2 The trusted tests

These live in `trusted_tests/`, **outside** the folder the agent may change, and are copied into the sandbox read-only.

| Test | What it checks | Why it matters |
| --- | --- | --- |
| `test_duplicate_event_reproduces` | Sending the same event twice crashes on the original code | Proves the bug was real (must fail before the fix) |
| `test_duplicate_event_single_effect` | After the fix, the same event twice returns OK **and the customer is credited exactly once** | "Returns 200" alone isn't enough |
| `test_distinct_events_same_customer` | Two different events from one customer are **both** processed | Catches the wrong fixes: "delete the uniqueness rule" and "ignore all errors" |
| `test_unique_index_still_present` | The uniqueness rule on the event ID still exists | Catches the lazy fix that removes it |
| Regression tests | Normal single payments still work | Nothing else broke |

### 10.3 What the runner does, step by step

1. Create a fresh temporary folder and copy the practice app into it.
2. Start from an **empty fixture database**: the local Docker database, or a new `fixture_<run>` database on Atlas using the restricted `fixture_runner` user.
3. Run the reproduction test on the **original** code. It must fail. If it passes, the case is broken: stop and report.
4. Create **another** fresh copy, write the agent's proposed file into it (only if the file is on the allowlist), and run all trusted tests.
5. Run `pytest` as a separate process with a time limit and a minimal environment. The app's Atlas connection string and the LLM and Voyage keys are **not** available to it.
6. Return the facts: `{runId, beforeFailed, afterPassed, tests: [...], evidenceHashes: [...], durationMs, status}`. `status` is `passed`, `failed` or `inconclusive`. Inconclusive means our infrastructure broke, not the fix.
7. Delete the temporary folder and drop the fixture database.

### 10.4 Cases (`cases/`)

Each case is a folder with a `manifest.json` that the agent sees, and a `labels.json` that only the scoring script sees.

| Case | Team | App | What's different | Expected good outcome |
| --- | --- | --- | --- | --- |
| A | Payments | payments-webhooks | Original bug, no memory yet | Investigate, fix, verify, promote a memory |
| B | Payments | payments-webhooks (handler renamed) | Logs worded differently; same mechanism | Recall A's memory, check conditions, fix in fewer steps, renew |
| C | Payments | payments-webhooks (index on `customer_id`) | Same error, different cause | Reject the memory with evidence; repair or escalate |
| D | Platform | platform-webhooks | Same mechanism, other team | Zero Payments memories visible; investigate from scratch |
| B2, B3, C2, N1… | Mixed | Variants | For the experiment (section 12) | Varies |

`labels.json` holds the expected cause and fix. The agent's tools can only see the temporary workspace, so the agent can never read the answers.

## 11. The API

Every request carries an `X-API-Key` header. The server turns it into a principal (team and role) and refuses anything that principal may not do. P1 owns the incident and run endpoints. P2 owns the memory endpoints in `memory/router.py`, which P1's app mounts.

| Method and path | Who may call | What it does |
| --- | --- | --- |
| `POST /incidents` | engineer | Submit a cleaned bug report. The server assigns the ID. |
| `POST /incidents/{id}/runs` | engineer | Start an investigation. Returns 202 and a run ID right away. Sending the same idempotency key twice returns the same run. `?memory=off` exists only for the experiment. |
| `GET /runs/{id}` | engineer (same team) | Status, budgets used, outcome, memory-influence record |
| `GET /runs/{id}/events?after=<seq>` | engineer (same team) | Timeline steps after a given step number. The UI polls this. |
| `GET /memories` and `GET /memories/{id}` | engineer | Only memories the caller's team may read |
| `GET /memories/{id}/audit` | memory\_admin of the owner team | That memory's full audit history |
| `POST /memories/{id}/share` | memory\_admin of the owner team | Body `{teamId, reason}`. Same company only. |
| `POST /memories/{id}/correct` | memory\_admin | Creates a new version that replaces the old one. Changing the fix itself requires a new verification run ID; narrowing "when it applies" needs only admin approval. |
| `POST /memories/{id}/revoke` | memory\_admin | Body `{reason}` |
| `POST /memories/{id}/expire` | memory\_admin | Set expiry to now (for the demo). Body `{reason}`. |
| `POST /memories/{id}/resolve-dispute` | memory\_admin | Body `{decision: restore or revoke, reason}` |
| `DELETE /memories/{id}` | memory\_admin | Forget: hard delete plus tombstone. Body `{reason}`. |
| `POST /incidents/{id}/verify` | engineer | Ask the runner to verify a given fix (used by the fallback in section 16) |

### Reliability rules

- **Save before working.** A run document is written before any LLM or tool call, so a crash never loses track of a run.
- **No double starts.** A unique idempotency key on runs blocks duplicates. Workers claim runs with an atomic update and a time-limited lease.
- **Safe resume.** After a restart, read-only steps can be repeated, and verification reruns in a new temporary copy. We never claim "exactly once".
- **No double memories.** Promotion is protected by the unique index from section 8.7. If the app crashes after verifying but before promoting, the promotion is left as a retryable task.
- **Embedding failure** (Voyage down): the memory is marked `memory_pending_embedding` and retried with increasing waits. It isn't searchable until it has an embedding.
- **Search failure** (Atlas Vector Search down): the run continues without memory and says so in its timeline.
- **Budget or time exceeded:** the run returns the evidence it collected with status `unresolved`.
- **Demo safety:** if a live dependency fails during the presentation, we may show a recording, **labeled as a recording**.

## 12. Proving it works (the experiment)

We run about 6 new cases, each three ways (no memory, placebo memory, real memory), twice each: about **36 runs**, and we publish every result. This answers the judges' hardest question: did memory change behavior, or did it just add text to the prompt?

### 12.1 The idea in plain words

Imagine testing whether a cheat sheet helps a student. You compare three groups: no cheat sheet, a cheat sheet for the *wrong* subject (same length), and the right cheat sheet. If only the right one helps, the content mattered, not just having more paper. Our "wrong subject" sheet is the **placebo memory**.

### 12.2 What's in the experiment

- **The memory store is frozen** before the experiment starts. It holds case A's memory (and B's, if promoted). New results from experiment runs are **not** added while we're comparing.
- **Placebo memories** are short texts about unrelated bugs, the same length as real memories, kept in `evals/placebo_memories.json`. They're inserted through the **same** code path that inserts real memories into the prompt. They are **never** stored in Atlas.
- **Held-out cases (about 6):**
  - 3 true repeats: logs worded differently, handler renamed, different route
  - 2 look-alikes: unique index on `customer_id`; unique index on (`customer_id`, day)
  - 1 brand-new bug that no memory covers
- **Leak check:** every case is also run as the *other* team, to confirm zero cross-team memories appear.

### 12.3 Conditions

| # | Condition | How |
| --- | --- | --- |
| 1 | No memory | `?memory=off` |
| 2 | Placebo | Inject a placebo memory of matching length instead of recall |
| 3 | Real memory | Normal recall with permission filter and condition checks |
| 4 *(optional)* | Naive reuse | Real recall but condition checks switched off. Shows how often a careless agent would apply the wrong fix on look-alikes. |

Everything else stays the same across conditions: same model, same prompt version, same tools, same budgets, same tests.

### 12.4 What we measure

| Measure | Definition | Target |
| --- | --- | --- |
| Verified resolution | Case fixed and all trusted tests pass, within budget | Higher or equal with memory |
| Tool calls to a verified fix | How many tool calls the run needed | Lower with real memory on repeats |
| First idea correct | Was the agent's first hypothesis the labeled cause? | Higher with real memory |
| Harmful reuse | Applied a remembered fix where its conditions were false | 0 with condition checks |
| Correct rejection | On look-alikes, rejected the memory with evidence | All look-alikes |
| **Cross-team leaks** | Another team's memory appeared in a result | **Must be 0** |
| **Forgotten or expired memory used** | Any use after forgetting or expiry | **Must be 0** |
| Wall time | Seconds per run, including timeouts | Report as measured |

### 12.5 Rules for an honest result

- Every run starts a fresh session.
- The agent never sees `labels.json`.
- Use the model's most repeatable setting (temperature 0 where available).
- Shuffle the order of conditions so timing isn't biased.
- Publish raw counts ("5 of 6"), never only percentages.
- **No claims of statistical significance from 36 runs.** We say "in our small test".
- If memory didn't help, say so and explain why. That's still good engineering.

`evals/run_ablation.py` (P3) runs everything, and writes `evals/results/results.json` plus a Markdown table for the README and the pitch.

## 13. Who does what

Each person owns one area, one set of folders, and one part of the demo story. Until a teammate's real code exists, build against the **fakes** in `contracts/fakes.py`, then switch to the real code at the checkpoints. Tick boxes as you go, so everyone can see progress.

### 13.1 P1: Agent runtime

**Mission:** a bounded, evidence-citing agent that turns an incident into a verified fix, and an API that runs it. **Owns:** `api/`, `agent/`, `contracts/` (merges changes), `tests/agent/`. **Demo part:** explains how the agent decides, its budgets, and why its claims cite evidence.

**11:00–11:30**

- [ ] Read the participant guide, or ask an organizer: submission deadline, judging criteria, what to submit, prebuilt-code rule. Post the answers in team chat.
- [ ] Add the starting skeleton (section 14.1), `CODEOWNERS`, `.gitignore` (with `.env`), `.env.example`, `pyproject.toml`. Push everything to TraceBack's `main`.
- [ ] Write and merge `contracts/models.py`, `contracts/interfaces.py` and `contracts/fakes.py` (section 14.2). Both teammates review.
- [ ] Make one working LLM call with tool use.

**11:30–13:00**

- [ ] FastAPI app: API-key → principal check; `POST /incidents`, `POST /incidents/{id}/runs`, `GET /runs/{id}`, `GET /runs/{id}/events`.
- [ ] Save `runs` and `run_events` in Atlas. Save the run *before* starting work.
- [ ] Agent loop with budgets (8 tool calls, 2 attempts, 2 minutes), first against `FakeRunner` and `FakeMemoryStore`.
- [ ] Tools: `read_file`, `search_code`, `get_fixture_metadata`, `inspect_unique_indexes`, `compare_event_ids`, `run_reproduction`, `run_verification`, with path checks.
- [ ] Switch to P3's real runner: **case A fixed and verified without memory.**

**13:30–15:00**

- [ ] Switch to P2's real memory store: recall, condition checks, the memory-influence record.
- [ ] Report outcomes to memory: promote, renew, dispute, near-miss.
- [ ] Cases B (reuse) and C (reject) working end to end.
- [ ] Mount `memory/router.py`; serve `web/`.

**15:00–16:30**

- [ ] Hardening: kill the worker mid-run and restart; check the run resumes or ends cleanly. Budget-exceeded and LLM-timeout paths return `unresolved` with evidence.
- [ ] Record a backup video of the full demo.

**Done means:** case A investigated and verified with no memory, B reuses memory in fewer steps, C rejects memory with evidence, every claim in a diagnosis cites evidence IDs, and budgets stop runaway runs.

### 13.2 P2: Memory governance

**Mission:** memories that are proven, team-scoped, expiring, correctable, forgettable and audited, enforced by the database where possible. **Owns:** `memory/` (`store.py`, `recall.py`, `lifecycle.py`, `policy.py`, `audit.py`, `embeddings.py`, `router.py`), `scripts/atlas_setup.py`, `scripts/seed_demo.py`, `tests/memory/`, all Atlas configuration. **Demo part:** explains scope, lifecycle, forgetting and the audit log, and shows the side-by-side leak view.

**11:00–11:30**

- [ ] Atlas one-time setup (section 6.4): invite teammates, IP list, database users, connection string, Voyage key. Send secrets privately.
- [ ] Prove one filtered `$vectorSearch` on Cluster0. Post "Atlas ready".

**11:30–13:00**

- [ ] `scripts/atlas_setup.py --db <name>`: create the collections, the `memories` validator, the vector index, the TTL index and the other indexes; idempotent; wait until the vector index is queryable.
- [ ] `scripts/seed_demo.py`: team policies and one hand-made memory, for testing recall before case A exists.
- [ ] `embeddings.py`: Voyage `voyage-4-lite`, with `document` vs `query` input types; retry on errors.
- [ ] `promote()`: build the memory from the incident draft plus the runner's facts, compute `expiresAt` and `purgeAt` from policy, insert, log `promoted`, and wait until it's searchable (`is_searchable`).
- [ ] `recall()`: vector search with the scope filter, exact signature lookup, merge, re-read guard, `retrieved` and `index_lag_dropped` audit events, top 3.
- [ ] `tests/memory/test_leakage.py`: Platform never sees Payments' memories; the unscoped query would.

**13:30–15:00**

- [ ] `record_use()`: `used`, `rejected`, `near_miss`, `renewed` (expiry extended, capped by max lifetime), `disputed` (status change).
- [ ] Admin actions in `router.py`: share, correct (new version supersedes old), revoke, expire now, resolve dispute, forget (delete plus tombstone). Every one requires a reason and writes an audit event.
- [ ] "Forgotten" then "unsearchable" probe for the UI.

**15:00–16:30**

- [ ] `tests/memory/test_lifecycle.py`: superseded, revoked, disputed, expired and forgotten memories never come back from recall, even during index lag.
- [ ] Audit queries for the demo: "who read memory X", "what did Platform read".
- [ ] Write the governance part of the README, with a table of the rules.

**Done means:** the validator refuses a memory without proof, Platform sees zero Payments memories, expire and forget take effect immediately on recall, and every action shows up in the audit log.

### 13.3 P3: Test app and proof

**Mission:** a realistic world for the agent, tests that can't be fooled, a UI that makes the story visible, and numbers that prove it. **Owns:** `fixture_app/`, `trusted_tests/`, `runner/`, `cases/`, `evals/`, `web/`, `scripts/reset_fixture.py`, `tests/runner/`. **Demo part:** drives the live demo; presents the experiment results.

**11:00–11:30**

- [ ] Start the local fixture database (section 6.5) and prove `pytest` runs against a small FastAPI app.
- [ ] Ask a MongoDB mentor whether Agent Engine use is judged. Post the answer.

**11:30–13:00**

- [ ] `fixture_app/payments-webhooks/`: the buggy handler, the ledger, the unique index on `provider_event_id`.
- [ ] `trusted_tests/`: the five tests in section 10.2. Check they **fail** on the buggy code and **pass** on a hand-written reference fix.
- [ ] `runner/`: temporary copy, allowlisted file replacement, `pytest` in a separate process with a timeout and stripped environment, facts returned, cleanup.
- [ ] `cases/A`, `cases/B`, `cases/C`: manifest plus hidden labels, and the variant apps they need.

**13:30–15:00**

- [ ] `web/index.html` + `web/app.js`: incident picker (with team key selector), live timeline, memory cards (owner team, readers, expiry countdown, proof, decision), governance buttons, audit view, side-by-side leak view.
- [ ] `fixture_app/platform-webhooks/` and `cases/D`.
- [ ] `evals/run_ablation.py`, `evals/placebo_memories.json`, held-out case variants.

**15:00–16:30**

- [ ] Run the experiment (6 cases × 3 conditions × 2 repeats). Produce the results table.
- [ ] Write the demo script (section 17), and `make demo-reset` to reseed `traceback_demo` and the fixtures.

**Done means:** each case reproduces on the original code; the reference fix passes and wrong fixes fail; the runner never sees secrets; the UI shows all five beats; the results table is generated from real runs.

### 13.4 Shared by everyone

- [ ] Review at least one pull request from each teammate.
- [ ] Understand the whole path of one incident (section 7) well enough to explain it.
- [ ] Write your README section.
- [ ] Rehearse the demo twice.

## 14. Working together in one GitHub repository

We all push to one repository: [github.com/YaCnDehfuli/TraceBack](https://github.com/YaCnDehfuli/TraceBack). Each person works only in their own folders, on short-lived branches, merged through small pull requests that a teammate reviews. Shared definitions in `contracts/` let us build in parallel without waiting for each other.

**State of the repository at 11:15:** it is **public**, its default branch is `main`, and it holds one commit with only a `README.md`. P1 pushes the starting skeleton (section 14.1) between 11:00 and 11:30, and everyone branches from that.

**Because the repository is public, anything pushed is visible to the whole internet immediately.** Check that `.env` is in `.gitignore` before the very first push, and run `git status` before every commit. If a key or password is ever pushed, P2 must replace it at once, even if the commit is deleted afterwards.

### 14.1 Folder layout

```
TraceBack/
├─ contracts/         shared data shapes, interfaces, fakes        P1 merges, everyone reviews
├─ api/               FastAPI app, API-key check, run endpoints    P1 (mounts memory/router.py, serves web/)
├─ agent/             loop, tools, prompts, budgets                P1
├─ memory/            store, recall, lifecycle, policy, audit      P2
├─ fixture_app/       payments-webhooks/, platform-webhooks/       P3 (the agent may change these)
├─ trusted_tests/     reproduction + business-rule tests           P3 (the agent may NEVER change these)
├─ runner/            temporary-copy sandbox, pytest process       P3
├─ cases/             A, B, C, D + experiment variants + labels    P3
├─ evals/             run_ablation.py, placebo_memories.json, results/   P3
├─ web/               index.html + app.js                          P3
├─ scripts/           atlas_setup.py, seed_demo.py (P2); reset_fixture.py (P3)
├─ tests/             agent/ (P1), memory/ (P2), runner/ (P3)
├─ docs/              DESIGN.md: an export of this guide
├─ .github/           CODEOWNERS, workflows/ci.yml
└─ pyproject.toml, uv.lock, .env.example, .gitignore, Makefile, README.md
```

`.github/CODEOWNERS` (replace the handles with our GitHub usernames):

```
/contracts/      @p1-handle @p2-handle @p3-handle
/api/ /agent/    @p1-handle
/memory/ /scripts/atlas_setup.py /scripts/seed_demo.py   @p2-handle
/fixture_app/ /trusted_tests/ /runner/ /cases/ /evals/ /web/   @p3-handle
```

### 14.2 The shared contracts (merged in the first 30 minutes)

These files let three people build at once. P1 drafts them at 11:00, and all three agree before writing other code.

`contracts/models.py` (Pydantic data shapes): `Principal`, `Observations`, `MemoryCandidate`, `MemoryUseDecision`, `MemoryDraft`, `FilePatch`, `VerificationResult`, `RunEvent{runId, seq, type, payload, at}`, `CaseManifest`.

`contracts/interfaces.py` (what each side promises to provide):

```python
class MemoryStore(Protocol):  # provided by P2, used by P1
    def recall(self, p: Principal, obs: Observations, run_id: str, k: int = 3) -> list[MemoryCandidate]: ...
    def record_use(self, p: Principal, memory_id: str, version: int, run_id: str, d: MemoryUseDecision) -> None: ...
    def promote(self, p: Principal, draft: MemoryDraft, v: VerificationResult) -> str: ...  # safe to call twice
    def is_searchable(self, p: Principal, memory_id: str) -> bool: ...


class Runner(Protocol):  # provided by P3, used by P1
    def reproduce(self, case_id: str) -> VerificationResult: ...
    def verify(self, case_id: str, patch: FilePatch) -> VerificationResult: ...
```

`contracts/fakes.py`: `FakeMemoryStore` (returns one canned memory) and `FakeRunner` (returns canned pass/fail). P1 builds the agent against these. P3 builds the UI against recorded `RunEvent` examples. P2 tests recall with hand-written memories. At each checkpoint we swap fakes for the real code.

**Changing a contract:** post in team chat first, open a small pull request touching only `contracts/`, get both teammates' approval, then P1 merges it.

### 14.3 Your daily git routine, step by step

**Start a piece of work:**

```bash
git checkout main
git pull                              # get everyone's latest work
git checkout -b p2/scoped-recall      # new branch: <your role>/<short topic>
```

**Save and upload your work (often):**

```bash
git status                            # see what changed; make sure .env is NOT listed
git add memory/recall.py tests/memory/test_leakage.py
git commit -m "Scoped recall with re-read guard and leakage test"
git push -u origin p2/scoped-recall   # first push; later just: git push
```

**Ask for a merge:** on GitHub, click *Compare & pull request*. Write two lines: what it does, and how you tested it. Request a review from the teammate who uses your code.

**Review a teammate's PR (5 minutes maximum):** Does it touch only their folders? Any secrets in it? Do the tests pass? If it looks reasonable, approve. Don't hold it up over style.

**Merge:** on GitHub, use **Squash and merge**, then delete the branch. Back on your laptop:

```bash
git checkout main && git pull
```

**Bring `main` into your branch** (when a teammate merged something you need):

```bash
git checkout p2/scoped-recall
git merge main                        # simpler than rebase for today
```

**If git reports a conflict:** open each file it lists and look for the `<<<<<<<` `=======` `>>>>>>>` markers. Keep the right version (often both changes combined) and delete the markers. Then run `git add <file>` and `git commit`. If the conflict is in someone else's folder, **stop and ask them**.

### 14.4 Team rules for the repository

- `main` must always run `make demo`. Run the tests before you merge.
- Merge at least every **90 minutes**. A branch kept until the afternoon becomes a painful merge.
- **Dependencies:** add them with `uv add <package>` in their **own tiny PR**, because two people editing `uv.lock` at once always conflicts.
- **Secrets:** `.env` is in `.gitignore` from the first commit. If a secret is ever pushed, tell P2 immediately so the key or password can be replaced; deleting the file afterwards is not enough.
- **Databases:** while developing, everyone uses their own database (`traceback_p1`, `traceback_p2`, `traceback_p3`). `traceback_demo` is only for rehearsals and the live demo, and is reset with `make demo-reset`.
- **CI** (only if it takes under 10 minutes to set up): a GitHub Action running `ruff` and `uv run pytest -m "not atlas"` on each PR. Tests that need Atlas are marked `@pytest.mark.atlas` and run on laptops.
- **README:** each person writes their own section; P1 assembles the final version.

## 15. Schedule and checkpoints

We build in three parallel lanes from 11:00, meet at two integration checkpoints (13:00 and 15:00), freeze features at 16:30, and spend the last hour on the README, the video and rehearsal. **If the real submission deadline is earlier than 17:30, move every block earlier by the same amount.**

*Diagram in the shared guide: Build schedule · 3 lanes, 2 checkpoints, freeze at 16:30.*

Read each row left to right: what each person finishes in that time block. The highlighted bands are the two integration checkpoints that everyone attends. Section 13 has the full task list behind each box.

### What must be true at each checkpoint

1. **11:30 – Kickoff done.** Deadline and judging rules posted in chat. Repo skeleton and contracts merged. Atlas ready ("Atlas ready" posted). One LLM call works. The fixture database runs.
2. **13:00 – Checkpoint 1: the first loop works.** Case A runs end to end on real code (no fakes): the agent investigates, the runner verifies, the memory service promotes, and the memory becomes searchable. We eat lunch while integrating.
3. **15:00 – Checkpoint 2: the whole demo story works.** All five beats (A Learn, B Reuse, C Reject, D Isolate, E Forget) run on `traceback_demo` through the UI.
4. **16:30 – Feature freeze.** No new features after this, only fixes, the README, the video and rehearsal. The experiment results table exists.
5. **17:30 – Submitted** (or earlier if the real deadline requires). Then rehearse until presentations start.

### If we're behind

- **At 13:00, case A isn't working:** all three people work on case A until it is. Nothing else matters without it.
- **At 14:00, automatic fixing is unreliable:** switch to the fallback (section 16) so the demo story still works.
- **At 15:00, beat D or E isn't working:** P2 and P3 pair on it. P1 hardens A to C.
- **At 16:30, the experiment isn't finished:** show the live forget-and-rerun and the leak-test output as proof, and say the full benchmark is pending.

## 16. When things go wrong

Every risky part has a planned fallback, so no single failure sinks the demo. Use the troubleshooting table for the common problems before asking for help, but ask after 10 minutes either way.

### 16.1 What we must ship, and what we cut first

**Must ship:**

- Promotion only after verification
- Scoped recall from a fresh session
- Rejection in case C
- Zero leaks in case D
- Forget-and-rerun returning to baseline
- The audit log
- A small experiment with the placebo condition

**Cut first, in this order:** sharing between companies, keyword or hybrid search, change streams, database-level role separation, React, LangGraph (unless someone already knows it), Agent Engine, reranking. We never build Slack or GitHub integrations, Kubernetes, multiple agents, arbitrary repositories, or model training.

### 16.2 Planned fallbacks

| If this fails | Do this instead | Say this in the demo |
| --- | --- | --- |
| The LLM can't produce working fixes reliably (decide at 14:00) | The agent **chooses** among 2–3 candidate fixes we wrote in `cases/`, and the runner verifies its choice. Memory and governance work exactly the same. | "The agent selects the fix from candidates; verification is fully automatic." |
| The UI isn't ready | Use the API docs page FastAPI generates at `/docs`, or a small command-line script showing the same evidence | Nothing special; the evidence is the same |
| The experiment isn't finished | Show the live forget-and-rerun plus the leak-test output | "The full benchmark is pending; here's the direct evidence." |
| Memory turns out not to help | Report the measured result and explain why | The honest numbers |
| Atlas or Voyage fails live | Play the backup recording | "This is a recording from 16:15, because of a live dependency failure." |
| A new memory isn't searchable yet during the demo | Show the "stored → searchable" wait honestly, or start beat B after the probe says searchable | Nothing to hide; it's a known, explained property |

### 16.3 Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Connecting to Atlas hangs about 30 seconds, then times out | Your IP isn't on the access list, or the venue Wi-Fi changed address | Atlas → *Database & Network Access* → *IP Access List* → add your current IP; wait for *Active* |
| `Authentication failed` from Atlas | Wrong database user or password, or the password has special characters that weren't URL-encoded | Ask P2 for a fresh connection string; encode `@ : / ?` in the password |
| Vector search returns nothing | The index isn't ready yet, or the embedding isn't 1,024 numbers, or you queried the wrong database or collection | Check *Search & Vector Search* says *Ready*; print `len(embedding)`; print the database name |
| Error: path isn't indexed as a filter field | The filter uses a field not declared as `filter` in the vector index | Add the field to the index definition in `atlas_setup.py`, rerun it, and wait for the rebuild |
| A new memory is never found | Index lag, or its `expiresAt` is already in the past (check time zones: always use UTC), or wrong `readableBy` | Wait for the searchable probe; use `datetime.now(timezone.utc)`; check the document in *Data Explorer* |
| Insert into `memories` fails with "Document failed validation" | The validator is doing its job: a field is missing, the status is bad, verification isn't passing, or the embedding isn't 1,024 numbers | Read the error's details; fix the builder in `memory/store.py`, not the validator |
| Voyage authentication error | The key is going to the wrong address | Use the curl test in 6.3 step 5; use the HTTP helper in `memory/embeddings.py` |
| Voyage "rate limit" errors during the experiment | Too many requests per minute | Check the *Rate Limits* page; add a short pause and retries; cache embeddings of identical text |
| The runner says "inconclusive" | Docker or the fixture database isn't running | `docker ps`; restart `fixture-mongo`; check `FIXTURE_MONGODB_URI` |
| The reproduction test passes on the original code | The case is broken (the bug isn't really there) | Fix the case in `cases/`; never "fix" the test |
| The agent keeps hitting its budget | Prompt too vague, or tool results too long | Shorten tool outputs; make the prompt state the goal and the 8-call limit; check the agent sees memory checks first |
| Merge conflict in `uv.lock` | Two people added dependencies | Take `main`'s version, then rerun your `uv add` and commit |
| You accidentally committed `.env` | — | Tell P2 **immediately**; P2 replaces the leaked keys and passwords |

## 17. Demo, presentation and submission

The pitch is four minutes and follows the five beats. P3 drives the screen, and each person speaks to their own part. Our closing message is that **retrieved experience guides the investigation, while current evidence and independent tests decide whether a fix is used.**

### 17.1 The four-minute script

| Time | Beat | On screen | Who speaks | Key line |
| --- | --- | --- | --- | --- |
| 0:00–0:20 | Problem | Title slide | P1 | "Teams lose debugging knowledge. But agent memory is data someone has to answer for." |
| 0:20–1:00 | A. Learn | Run case A; memory card appears with owner team, expiry and proof; "stored → searchable" | P1 | "Only a fix proven by tests becomes a memory." (A labeled recording is fine if time is tight.) |
| 1:00–1:40 | B. Reuse | Restart the worker, run case B; memory used after condition checks; fewer steps; expiry renewed | P1 | "New session, different wording: the memory guided it, and the evidence confirmed it." |
| 1:40–2:10 | C. Reject | Run case C; memory rejected with the failing evidence; near-miss logged | P2 | "Same error, different cause. Similarity suggests; evidence decides." |
| 2:10–2:40 | D. Isolate | Switch to the Platform key; zero Payments memories; the side-by-side unscoped view; "who read this?" audit query | P2 | "The team filter runs inside the database search. Nothing leaks." |
| 2:40–3:15 | E. Forget | Admin forgets the memory; tombstone; unsearchable; rerun case B goes back to the no-memory path | P2 | "Forgetting is real, and this rerun shows the memory caused the improvement." |
| 3:15–4:00 | Proof | Results table (no memory / placebo / real), architecture, honest limits | P3 | "Placebo memory didn't help; real memory did. Here are the raw counts." (Use the real numbers, whatever they are.) |

### 17.2 Rehearsal rules

- Run `make demo-reset` before every rehearsal and before the real pitch.
- Rehearse at least **twice** with a timer. Cut words, not beats.
- Open these in tabs beforehand: the UI, Atlas *Data Explorer* on `traceback_demo.memory_audit`, the results table, and the backup recording.
- Decide who answers which judge questions: agent and API → P1; memory, Atlas, governance → P2; tests, experiment, UI → P3.

### 17.3 Likely judge questions, with short answers

| Question | Answer |
| --- | --- |
| Why not use Agent Engine's memory? | We evaluated it. Its SDK has no documented delete, update or expiry operation, and Challenge 2 requires correcting and forgetting. Our interface could sit in front of it once it supports those. |
| How do you know memory helped and didn't just add text? | The placebo condition: unrelated text of the same length, inserted the same way. Plus forget-and-rerun on the same case. |
| What if the vector index still returns a deleted memory? | Every result is re-read from the collection with the full permission filter before use, and dropped results are logged. |
| Could the AI promote or share its own memory? | No. Only the memory service writes memories, based on runner facts or admin actions. The AI can't change who is calling. |
| Is this production-ready? | No. Synthetic incidents, one company with two teams, demo API keys. The governance mechanisms are real, and we say exactly what we evaluated. |

### 17.4 Submission checklist

- [ ] Confirm the submission format and deadline (from 11:00).
- [ ] Repository is public or shared as required, with **no secrets** in its history.
- [ ] README: problem, what it does, the five beats, a short demo video or GIF, quickstart, architecture, governance rules, experiment results with raw counts, limits (synthetic data, demo keys), the Agent Engine evaluation, and team credits (who built what).
- [ ] `docs/DESIGN.md`: an export of this guide.
- [ ] `.env.example` without secrets; `uv.lock` committed; `scripts/atlas_setup.py`, `seed_demo.py` and `reset_fixture.py` work from scratch.
- [ ] Demo video recorded (2–4 minutes); any replayed parts labeled.
- [ ] Submitted, and a confirmation screenshot posted in team chat.

### 17.5 After the event (CV-safe wording)

A truthful line each of us can use: *"Built a backend debugging agent with MongoDB Atlas Vector Search and team-scoped, expiring, forgettable incident memory; implemented test-based fix verification and evaluated it against no-memory and placebo baselines on N reproducible incidents."* Add measured numbers only after the experiment exists. Don't call synthetic incidents production deployments, and name your own part of the team's work.

## 18. Open questions and sources

### Open questions (answer in team chat, then update this guide)

- [ ] What is the submission deadline, and what exactly must we submit? (P1, 11:00)
- [ ] What are the judging criteria? (P1, 11:00)
- [ ] Is code written before today allowed? (P1, 11:00)
- [ ] Does using Atlas Agent Engine count in judging? (P3, ask a MongoDB mentor)
- [ ] Which LLM and model name do we use, and who holds the key? (P1)
- [ ] Are we all on the same venue Wi-Fi, so one IP access entry covers everyone? (P2)
- [ ] Repository: YaCnDehfuli/TraceBack on GitHub (answered)

### Sources

The Atlas environment facts (cluster tier, MongoDB version, region, org resource policy, AI Model APIs and Agent Engine pages) were checked directly in our Atlas project on the morning of November 14, 2026. Everything else comes from these pages:

- [Event listing (Cerebral Valley)](https://events.cerebralvalley.ai/e/mongodb-toronto-hackathon): dates, prizes, team size, required technologies
- [Event registration (Luma)](https://luma.com/mongodb-toronto): venue, judges
- [Atlas `$vectorSearch` stage](https://mongodb.com/docs/atlas/atlas-vector-search/vector-search-stage/): pre-filter field types and operators
- [Atlas Vector Search changelog](https://mongodb.com/docs/atlas/atlas-vector-search/changelog): date filter fields and array pre-filtering
- [Vector Search index reference](https://www.mongodb.com/docs/vector-search/indexes/vector-search-type/)
- [Voyage text embedding models (MongoDB docs)](https://www.mongodb.com/docs/voyageai/models/text-embeddings/): `voyage-4-lite`, 1,024-dimension default
- [Voyage embeddings API reference](https://docs.voyageai.com/reference/embeddings-api): `input_type` query vs document
- [Atlas AI Model APIs: clients and endpoints](https://www.mongodb.com/docs/voyageai/api-and-clients/): Atlas model API keys route to `ai.mongodb.com`
- [Atlas Agent Engine overview](https://www.mongodb.com/docs/agentengine/): public preview status
- [Agent Engine memory types and scoping](https://www.mongodb.com/docs/agentengine/add-features/memory-types/)
- [Agent Engine standalone memory service](https://www.mongodb.com/docs/agentengine/add-features/memory-only/): M10+, IP entries, `readWriteAnyDatabase`, SDK version
- [Agent Engine memory configuration and custom types](https://www.mongodb.com/docs/agentengine/add-features/memory/)
- [Agent Engine memory SDK reference](https://www.mongodb.com/docs/agentengine/sdk/python/packages/agent-engine-sdk-memory/) and [capability matrix](https://www.mongodb.com/docs/agentengine/sdk/python/packages/agent-engine-sdk-memory/docs/capability-matrix/): no delete, update or expiry operations listed
- [Agent Engine Policy Engine](https://www.mongodb.com/docs/agentengine/manage/governance/policy-engine/): tool and model allowlists, execution caps, runtime only
- [Agent Engine limitations](https://www.mongodb.com/docs/agentengine/reference/limitations/) and [getting started](https://www.mongodb.com/docs/agentengine/get-started/): deploy times, sandboxes, secrets

The architecture, budgets, schedule and experiment design in this guide are our engineering choices, not claims that anything has already been built or measured.
