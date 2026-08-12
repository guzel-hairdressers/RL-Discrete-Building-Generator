# Agent Notes Management Guide (`AGENT_NOTES_GUIDE.md`)

This guide defines the mandatory rules and instructions for human developers and AI coding agents on how to maintain, update, and manage the [`agent_notes/`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/README.md) folder in the **RL-Discrete-Building-Generator** (Module Lab) codebase.

---

## 1. Directory Purpose & Governance

The [`agent_notes/`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/README.md) folder is the authoritative repository of design decisions, research proposals, benchmark timing matrices, architectural guides, historical implementation records, and development roadmaps.

Whenever a major feature is designed, a bug is fixed, a benchmark is run, or an architectural proposal is discussed, it **MUST be documented inside `agent_notes/`**.

---

## 2. Folder Organization & File Rules

All files added to `agent_notes/` must be placed in their appropriate subdirectory:

```
agent_notes/
├── README.md                          # Central index
├── issues.md                          # Active issues, bug tracebacks & resolution logs
├── roadmap.md                         # Project development roadmap & milestone status
├── historical_approaches.md          # Implemented achievements & discarded/failed approaches ledger
├── proposals/                         # Research & architectural proposals with ratings
├── reports/                           # Deep technical reports & benchmark analyses
├── benchmarks/                        # Benchmark results & speedup timing matrices
└── guides/                            # Component guides & architectural documentation
```

### Where to Store New Artifacts:
* 📜 **Implemented & Discarded Approaches Ledger**: Maintain [`agent_notes/historical_approaches.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/historical_approaches.md). Document what was achieved by successful releases and **which approaches were useless/discarded** (along with exact failure reasons and conditions), preventing developers from repeating past mistakes.
* 🐛 **Bug Fixes & Troubleshooting**: Append to [`agent_notes/issues.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/issues.md). Include problem statement, log tracebacks, root cause analysis, and verification steps.
* 💡 **Ideas & Technical Proposals**: Create a markdown file in [`agent_notes/proposals/`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/proposals/). You **MUST include a Relevancy & Feasibility Rating Matrix** (HIGH, MEDIUM, LOW, DUMB / NOT RECOMMENDED) with concise justifications.
* ⚡ **Performance & Timing Data**: Record output in [`agent_notes/benchmarks/`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/benchmarks/). Include mean step time, mean episode time, speedup vs baseline, and hardware details.
* 🗺️ **Roadmap Updates**: When a phase in [`agent_notes/roadmap.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/roadmap.md) is started or completed, update its status tag (`[COMPLETED]`, `[IN PROGRESS]`, `[PLANNED]`).
* 📖 **System Documentation**: Add specialized architectural guides (e.g. C extensions, GNN models, BPE merge rules) to [`agent_notes/guides/`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/guides/).

---

## 3. Mandatory Safety & Editing Rules

1. **Verify Before Deleting Any File**:
   Never delete any source file or documentation file until you are 100% certain that **all relevant information, tracebacks, and rationale have been fully copied and indexed** into `agent_notes/`.

2. **Always Update `agent_notes/README.md` Index**:
   When adding a new file to any subdirectory inside `agent_notes/`, immediately update the index links in [`agent_notes/README.md`](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/README.md).

3. **Use Clickable Markdown Links with `file://` Scheme**:
   Whenever referencing code files or notes in markdown, use clickable file links:
   `[historical_approaches.md](file:///Users/ruslan_faz/Desktop/Work/Thesis/agent_notes/historical_approaches.md)`

4. **Preserve Historical Traceability**:
   Do not delete old resolution logs or historical benchmarks. Mark completed tasks as resolved rather than deleting their documentation.

5. **Synchronize Across Release Branches**:
   When promoting changes across release branches (`main`, `version/v0.8.1`), ensure corresponding `agent_notes/` documentation is updated and synced.
