# LeanDemoLogging

This project records the **actual C++ kernel execution** while Lean checks
`inj_comp`. It has its own copy of the demo and its own Lean source checkout and
executable. The original `../LeanDemo` project is not used as a build directory.

## View or regenerate the trace

Open **[traces/inj_comp.html](traces/inj_comp.html)** in a browser. All recorded
events appear in execution order, with each return after its nested calls.
The colored margins identify statement checking (ochre), proof checking (blue),
and the final type comparison (purple). Select a row to highlight its enclosing
call and inspect its expression beside the proof. Collapsing a call hides only
its interior events, shows their count and range, and leaves its return visible.

The fixed proof panel shows the recorded elaborated statement and proof, with
an **Original source** tab for the full Lean file. New recordings capture that
file in the metadata; older recordings explicitly label a current-file fallback.
A unique, exact text match is highlighted in the elaborated expression. This is
text matching, not a source map; ambiguous or absent matches are left unmarked.
“All arguments and universes” changes only the expression formatting.

From this directory, regenerate the trace with:

```sh
python3 scripts/trace.py
```

When this folder is open in VS Code, the task **Record the actual kernel trace**
runs the same command. The `.lean` file remains editable in the usual way.

Generated files:

- `traces/inj_comp.html`: chronological events with collapsible calls and a proof panel.
- `traces/inj_comp.txt`: complete indented event log.
- `traces/inj_comp.proof.txt`: only the proof-checking phase.
- `traces/inj_comp.jsonl`: original events written by the kernel.
- `traces/inj_comp.metadata.json`: executable version, invocation, and source snapshot.
- `traces/inj_comp.stdout.log`: ordinary Lean output, including the old replay.

The HTML and text views are generated from the recorded events. They do not run
a substitute checker or reconstruct an imagined sequence of checks.

## What the trace means

- `check`: validate an expression and return its type.
- `infer`: the kernel's internal inference-only path.
- `whnf` / `whnf_core`: reduce an expression to expose its outer form. The core
  routine has different reduction settings from the full routine.
- `unfold`: attempt to expand a named definition. “no unfolding” means that this
  attempt did not expand it.
- `defeq`: compare two expressions for definitional equality.
- `context`: record a variable or local definition entering the local context.
- `argument`: the actual and expected types of a function's argument.
- `cache`: reuse a previously computed type or reduction.

The kernel logs three phases: checking the theorem statement, checking the
proof, and comparing the inferred and declared types. It may revisit
expressions or use cached results. Those events are preserved.

The display printer traverses expressions without type-checking or reducing
them. It uses the local context to display names such as `h0`, `h1`, and `h2`.
The regular view uses equality and composition notation. “Show all arguments
and universes” exposes their explicit arguments and universe parameters. Both
views are readable renderings of core expressions, rather than a serialized
syntax-tree dump. Internal variable IDs are retained on context events in the
JSON file.

## Implementation

The source is pinned to Lean **v4.36.0-rc1**, commit
`c9afcddf514a6772bd4d649f7cfc04eff0b9f15e`.

- `instrumentation/demo_trace.h`: event writer, structural printer, and scoped
  logging. It never calls a type checker.
- `scripts/instrument.py`: adds logging to `lean4/src/kernel/type_checker.cpp`
  and `lean4/src/kernel/environment.cpp`. The original checking algorithms run
  inside the logging wrappers.
- `scripts/build.py`: builds the modified compiler using the installed release
  as its bootstrap compiler.
- `scripts/trace.py`: selects the declaration, runs the new executable, and
  renders its recorded events.

These two environment variables are **custom additions in this build**, not
standard Lean options:

```text
LEAN_KERNEL_TRACE_DECL=inj_comp
LEAN_KERNEL_TRACE_FILE=/absolute/path/to/events.jsonl
```

Logging is enabled only inside the kernel's original check of the selected
theorem declaration. Later calls from the demonstration replay are not included.
The event file is append-only at the C++ level; `trace.py` clears its chosen
output file before each run.

The project's `lean-toolchain` continues to name the official release for normal
editor operation. The tracing script explicitly invokes
`lean4/build/release/stage1/bin/lean`; it does not change the default toolchain.

## Rebuild

The local build needs a C++ compiler, CMake, pkg-config, GMP 6.3 or newer, and
libuv. On this Mac the existing GMP/libuv installations are used, pkg-config
was installed with Homebrew, and CMake 3.31.6 lives in `.build-tools`.

```sh
python3 scripts/build.py
```

The script supplies the macOS SDK path to both compilation and linking. Build
products remain under `lean4/build/release`. To recreate the source checkout:

```sh
git clone --depth 1 --branch v4.36.0-rc1 https://github.com/leanprover/lean4.git lean4
```

To recreate the local CMake installation if needed:

```sh
uv venv --python /usr/bin/python3 .build-tools
uv pip install --python .build-tools/bin/python cmake==3.31.6
```

## Verification

```sh
python3 scripts/verify.py
```

This checks that the original release and the modified executable produce the
same demo output, that logging does not change that output, that the recorded
calls and returns balance, and that the trace contains the intermediate proofs
and the expected unfolding. It also submits a deliberately wrong application
directly to the kernel and verifies its rejection. The declaration filter and
the original demo's saved file hashes are checked too.

The rejection test has its own trace at
`traces/rejected-application.html`. Its `exception` result is intentional.
