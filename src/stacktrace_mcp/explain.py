"""Embedded reference of common exception types: meaning, likely causes, what to check first."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    language: str
    names: tuple[str, ...]
    meaning: str
    causes: tuple[str, str, str]
    check: str


def _e(lang: str, names: str, meaning: str, c1: str, c2: str, c3: str, check: str) -> Entry:
    return Entry(lang, tuple(n.strip() for n in names.split("|")), meaning, (c1, c2, c3), check)


TABLE: tuple[Entry, ...] = (
    # ------------------------------------------------------------------ Python
    _e("python", "ZeroDivisionError", "Division or modulo by zero.",
       "A denominator computed from empty data (len(x) == 0, a sum of zero).",
       "A config or input value defaulting to 0.", "Integer vs float confusion in a rate calculation.",
       "The divisor's value at the failing line; guard empty collections."),
    _e("python", "KeyError", "A dict (or mapping) lookup used a key that is not present.",
       "Missing field in JSON/API data.", "Key built with different casing, type (int vs str) or whitespace.",
       "Dict mutated or never populated on this code path.",
       "The exact key in the message versus the dict's keys; use .get() only if absence is legitimate."),
    _e("python", "IndexError", "A sequence index is outside the sequence.",
       "Empty list/string indexed with [0].", "Off-by-one in a loop bound.", "Parallel lists of different length.",
       "len() of the sequence at the failing line."),
    _e("python", "TypeError", "An operation got a value of the wrong type or the wrong arguments.",
       "None where a value was expected ('NoneType' is not subscriptable/iterable).",
       "Wrong number or kind of arguments to a call.", "Mixing str and int, or awaiting/calling a non-callable.",
       "Which variable has an unexpected type; trace where it was assigned."),
    _e("python", "ValueError", "The type is right but the value is not acceptable.",
       "Parsing user input (int('abc'), bad date format).", "Unpacking the wrong number of values.",
       "Out-of-range or empty argument to a function.", "The offending value in the message and where it came from."),
    _e("python", "AttributeError", "An object has no such attribute.",
       "The object is None (a lookup or function returned nothing).", "Typo or API changed between library versions.",
       "Wrong object type (list instead of dict, class instead of instance).",
       "type() of the object and the installed library version."),
    _e("python", "NameError|UnboundLocalError", "A name is not defined in the current scope (UnboundLocalError: assigned later in the same function).",
       "Typo or missing import.", "Variable assigned only in one branch of an if/try.",
       "Assigning to a global inside a function without 'global'.", "The first assignment of the name in that scope."),
    _e("python", "ImportError|ModuleNotFoundError", "A module (or a name inside it) could not be imported.",
       "Package not installed in the interpreter that is running (wrong venv).", "Circular import.",
       "Name moved or removed in a newer library version.",
       "'which python' / sys.executable, then pip/uv list; check for a local file shadowing the module name."),
    _e("python", "FileNotFoundError", "The path does not exist.",
       "Relative path resolved against the wrong working directory.", "Container vs host path difference.",
       "File not created yet or already removed.", "os.getcwd() and the absolute path being opened."),
    _e("python", "PermissionError", "The OS refused access to a file or port.",
       "File owned by another user or read-only mount.", "Windows: file open in another process.",
       "Binding a privileged port (<1024).", "Owner/mode of the path and the user the process runs as."),
    _e("python", "RecursionError", "Maximum recursion depth exceeded.",
       "Missing or unreachable base case.", "Mutual recursion on cyclic data (graph with cycles, __repr__ cycles).",
       "Legitimately deep structure beyond sys.getrecursionlimit().",
       "The repeating pair of frames at the bottom of the trace; make it iterative or add a visited set."),
    _e("python", "StopIteration", "next() was called on an exhausted iterator.",
       "Calling next() without a default.", "A generator returned early.", "StopIteration leaking into a coroutine (becomes RuntimeError).",
       "Use next(it, default) or a for loop."),
    _e("python", "KeyboardInterrupt", "The user pressed Ctrl+C (SIGINT).",
       "Manual interrupt.", "A supervisor or test runner timed the process out.", "Terminal closed.",
       "Usually not a bug; check what was running if it was unexpected."),
    _e("python", "SyntaxError|IndentationError|TabError", "The source text is not valid Python.",
       "Unclosed bracket/quote (the error is often reported on the NEXT line).", "Mixed tabs and spaces.",
       "Syntax from a newer Python than the interpreter (match, f-string nesting, except*).",
       "The caret line and the line above; python --version."),
    _e("python", "MemoryError", "Python could not allocate memory.",
       "Loading a whole large file/dataset into memory.", "Unbounded cache or list growth (leak).",
       "32-bit interpreter or container memory limit.", "Peak memory use; stream or chunk the data."),
    _e("python", "OSError|ConnectionError|ConnectionRefusedError|ConnectionResetError|BrokenPipeError",
       "A system call failed (network, files, devices); errno says which.",
       "Server not listening / wrong host or port (refused).", "Peer closed the connection (reset, broken pipe).",
       "Firewall, DNS or proxy settings.", "errno/strerror in the message, then connectivity to that host:port."),
    _e("python", "TimeoutError", "An operation did not finish in time.",
       "Slow or unreachable remote service.", "Timeout set too low for the workload.", "Blocking call inside an event loop.",
       "What the call was waiting on and its configured timeout."),
    _e("python", "UnicodeDecodeError|UnicodeEncodeError", "Bytes could not be decoded (or text encoded) with the chosen codec.",
       "File is not UTF-8 (Windows cp1252, UTF-16 with BOM).", "Binary data treated as text.",
       "Locale-dependent default encoding.", "Pass encoding= explicitly and check the file's real encoding."),
    _e("python", "AssertionError", "An assert statement failed.",
       "A broken invariant or precondition.", "A test expectation that no longer holds.", "Assert used for input validation.",
       "The asserted expression's operands at that line."),
    _e("python", "RuntimeError", "A generic error that fits no other category.",
       "Library-raised state errors (event loop already running, dict changed size during iteration).",
       "Re-raised wrapper around an earlier failure.", "Misuse of async APIs.", "The message and the chained cause."),
    _e("python", "NotImplementedError", "A method that must be overridden was called.",
       "Subclass did not implement an abstract method.", "Feature stub left in place.", "Wrong subclass instantiated.",
       "Which class's method ran (type(self))."),
    _e("python", "JSONDecodeError", "Text is not valid JSON.",
       "Empty response body or an HTML error page instead of JSON.", "Trailing commas, single quotes, comments.",
       "Truncated payload.", "Print the raw text being parsed (first 200 chars)."),
    _e("python", "CancelledError", "An asyncio task was cancelled.",
       "Task.cancel() or a timeout.", "Server shutdown cancelling handlers.", "Parent TaskGroup failing and cancelling siblings.",
       "Who called cancel(); look for the sibling that actually failed."),
    _e("python", "ExceptionGroup|BaseExceptionGroup", "Several exceptions raised together (TaskGroup, except*).",
       "One or more tasks in a TaskGroup failed.", "Library collecting multiple validation errors.",
       "Concurrent operations each failing.", "Read each sub-exception separately; the first one is not necessarily the cause."),
    # ------------------------------------------------------------------ Node
    _e("node", "TypeError", "A value was of the wrong type, most often undefined/null used as an object.",
       "Cannot read properties of undefined (reading 'x'): an earlier lookup returned undefined.",
       "x is not a function: wrong import shape (default vs named export).", "Async result used before awaiting.",
       "Which expression is undefined at the reported column."),
    _e("node", "ReferenceError", "A variable is not defined.",
       "Typo or missing import/require.", "ESM/CJS mismatch (require or __dirname in an ES module).",
       "Using a let/const before its declaration.", "package.json 'type' and the file extension."),
    _e("node", "RangeError", "A numeric value or size is out of the allowed range.",
       "Maximum call stack size exceeded (runaway recursion).", "Invalid array length / string repeat count.",
       "toFixed/Date arguments out of range.", "The repeating frames at the top of the stack."),
    _e("node", "SyntaxError", "The code (or JSON) could not be parsed.",
       "JSON.parse on non-JSON (often an HTML error page; 'Unexpected token <').", "import/export in a CommonJS file.",
       "Syntax newer than the Node version.", "node --version and the first characters of the text being parsed."),
    _e("node", "ECONNREFUSED", "Nothing is listening at the target address and port.",
       "Server not started or crashed.", "Wrong port/host, or localhost resolving to ::1 vs 127.0.0.1.",
       "Container networking (use the service name, not localhost).", "ss/netstat for the port, and the exact address in the message."),
    _e("node", "ENOENT", "The file or directory does not exist.",
       "Relative path resolved against process.cwd().", "Build output missing.", "Typo or case mismatch on Linux.",
       "The path in the message and process.cwd()."),
    _e("node", "EADDRINUSE", "The port is already bound by another process.",
       "A previous instance is still running.", "Two services configured for the same port.", "Watch mode restarted too fast.",
       "Find the owning process (netstat -ano | findstr :PORT, lsof -i :PORT)."),
    _e("node", "EACCES|EPERM", "Permission denied.",
       "Writing to a protected directory.", "Binding a port below 1024.", "Global npm install without proper prefix.",
       "Owner/mode of the path and the user running node."),
    _e("node", "ECONNRESET|ETIMEDOUT|EPIPE", "The connection was closed by the peer or timed out.",
       "Server crashed or restarted mid-request.", "Idle keep-alive connection reaped by a proxy.",
       "Network or firewall drops.", "Server-side logs at the same timestamp; retry/keep-alive settings."),
    _e("node", "ERR_MODULE_NOT_FOUND|MODULE_NOT_FOUND", "A module could not be resolved.",
       "Dependency not installed (run the package manager).", "ESM import missing the file extension.",
       "Build output path wrong (dist not built).", "The 'Cannot find module' path and node_modules contents."),
    _e("node", "ERR_REQUIRE_ESM", "require() was used on an ES module.",
       "Dependency became ESM-only.", "Project is CommonJS but imports an ESM package.", "Wrong 'type' in package.json.",
       "Use dynamic import() or switch the project to ESM."),
    _e("node", "UnhandledPromiseRejection|UnhandledPromiseRejectionWarning", "A promise rejected and nothing handled it; modern Node exits.",
       "Missing await/catch around an async call.", "Error thrown inside a callback or event handler.",
       "Promise.all member failing.", "The rejection reason and the async call without a catch."),
    _e("node", "FATAL ERROR|JavaScript heap out of memory", "V8 ran out of heap.",
       "Unbounded array/map/cache growth.", "Reading a huge file or response into memory.", "Default heap limit too low for the workload.",
       "Heap snapshot; node --max-old-space-size only as a stopgap."),
    # ------------------------------------------------------------------ Java / Kotlin
    _e("java", "NullPointerException", "A null reference was dereferenced.",
       "A method returned null (map.get, repository lookup).", "Field never initialised or injected (missing @Autowired/constructor arg).",
       "Auto-unboxing a null Integer/Boolean.", "The line in the top application frame; helpful NPE messages (Java 14+) name the null expression."),
    _e("java", "ClassNotFoundException|NoClassDefFoundError", "A class was missing at load time.",
       "Dependency missing from the runtime classpath/fat jar.", "Version conflict removing a class.",
       "Static initializer failed earlier (NoClassDefFoundError: Could not initialize class).",
       "Look for an earlier ExceptionInInitializerError; check the jar contents."),
    _e("java", "NoSuchMethodError|NoSuchFieldError|AbstractMethodError", "Compiled code calls a member the loaded class does not have.",
       "Two versions of a library on the classpath.", "Stale build output.", "Incompatible transitive dependency.",
       "mvn dependency:tree / gradle dependencies for duplicates."),
    _e("java", "ArrayIndexOutOfBoundsException|IndexOutOfBoundsException|StringIndexOutOfBoundsException", "An index is outside the array/list/string.",
       "Off-by-one in a loop.", "Empty collection indexed at 0.", "Concurrent modification changed the size.",
       "The index and length printed in the message."),
    _e("java", "ClassCastException", "An object was cast to an incompatible type.",
       "Raw or unchecked generics.", "Deserialisation producing a different type.", "Classloader duplicates (same class, two loaders).",
       "The two class names in the message."),
    _e("java", "IllegalArgumentException|IllegalStateException", "An argument was invalid / the object was in the wrong state for the call.",
       "Validation failure at an API boundary.", "Calling methods in the wrong order (lifecycle).", "Bad configuration value.",
       "The message and the checkArgument/checkState at the top frame."),
    _e("java", "OutOfMemoryError", "The JVM could not allocate memory.",
       "Heap leak (growing caches, listeners).", "Loading very large data sets at once.",
       "Container limit below -Xmx; 'Metaspace' or 'unable to create native thread' variants.",
       "The message suffix (Java heap space / Metaspace / GC overhead) and a heap dump."),
    _e("java", "StackOverflowError", "The call stack is exhausted.",
       "Unbounded recursion.", "Mutual toString/equals/hashCode cycles in entity graphs.", "Very deep legitimate recursion.",
       "The repeating frames in the trace."),
    _e("java", "ConcurrentModificationException", "A collection was modified while being iterated.",
       "Removing in a for-each loop.", "Another thread mutating a non-thread-safe collection.", "Callback modifying the list it is called from.",
       "Use Iterator.remove, removeIf or a concurrent collection."),
    _e("java", "NumberFormatException", "A string could not be parsed as a number.",
       "Empty or whitespace string.", "Locale decimal separator.", "Value too large for the type.", "The input in the message."),
    _e("java", "SQLException|SQLSyntaxErrorException|DataAccessException", "A database operation failed.",
       "Constraint violation (duplicate key, null).", "Connection pool exhausted or DB unreachable.", "Schema drift between code and database.",
       "SQLState and vendor code in the message and the SQL that ran."),
    _e("java", "FileNotFoundException|IOException|UncheckedIOException|NoSuchFileException", "An I/O operation failed.",
       "Wrong path or working directory.", "Permissions.", "Disk full or stream closed.", "The path and the working directory."),
    _e("java", "SocketTimeoutException|ConnectException|UnknownHostException", "A network call timed out, was refused, or the host did not resolve.",
       "Remote service down/slow.", "DNS or proxy issue.", "Timeout configured too low.", "The host:port and the configured timeouts."),
    _e("java", "InterruptedException", "A blocked thread was interrupted.",
       "Executor shutdown.", "Task cancelled by a timeout.", "Swallowed interrupt flag from earlier code.",
       "Who called interrupt()/shutdownNow()."),
    _e("java", "UnsupportedOperationException|ArithmeticException", "The operation is not supported (e.g. mutating List.of) / arithmetic failed (/ by zero).",
       "Mutating an immutable collection.", "Integer division by zero.", "Default interface method not overridden.",
       "Where the collection was created."),
    # ------------------------------------------------------------------ Go
    _e("go", "nil pointer dereference|invalid memory address or nil pointer dereference", "A nil pointer, map-of-pointers value or interface was used.",
       "An error ignored so the result is nil.", "Struct field or dependency not initialised.", "Method on a nil receiver.",
       "The top app frame line; the variable just before the dot."),
    _e("go", "index out of range", "A slice or array index is >= its length (or negative).",
       "Empty slice indexed at 0.", "Off-by-one.", "Slice shared and changed by another goroutine.", "The index and length in the message."),
    _e("go", "slice bounds out of range", "A slice expression s[a:b] has bounds outside capacity.",
       "b greater than len/cap.", "Negative or swapped indices from untrusted input.", "Reslicing a shorter slice.", "The three numbers in the message."),
    _e("go", "concurrent map writes|concurrent map read and map write", "Two goroutines used a map without synchronisation (fatal, not recoverable).",
       "Map shared between handlers.", "Cache without a mutex.", "Closure capturing the map.", "Run with -race; protect with sync.Mutex or sync.Map."),
    _e("go", "all goroutines are asleep - deadlock!", "Every goroutine is blocked; nothing can proceed.",
       "Unbuffered channel send/receive without a counterpart.", "WaitGroup count never reaching zero.", "Mutex locked twice.",
       "The goroutine dump: what each goroutine is waiting on (chan send/receive, semacquire)."),
    _e("go", "DATA RACE", "The race detector saw unsynchronised concurrent access, at least one a write.",
       "Shared variable without a lock.", "Loop variable captured by a goroutine (pre Go 1.22).", "Slice append from several goroutines.",
       "The two stacks: the first and the 'Previous' access; add a mutex or channel."),
    _e("go", "close of closed channel|send on closed channel|close of nil channel", "Channel misuse.",
       "Two goroutines closing the same channel.", "Producer sending after the consumer closed it.", "Uninitialised channel.",
       "Make only the sender close, and close exactly once (sync.Once)."),
    _e("go", "interface conversion", "A type assertion on an interface failed.",
       "Value has a different dynamic type than assumed.", "nil interface.", "JSON decoding into interface{} yielding float64/map.",
       "Use the comma-ok form and log the actual type."),
    _e("go", "negative WaitGroup counter", "Done() was called more times than Add().",
       "Add called inside the goroutine instead of before it.", "Done called twice (defer plus explicit).", "WaitGroup copied by value.",
       "Every Add/Done pair."),
    _e("go", "stack overflow|goroutine stack exceeds", "Goroutine stack exceeded the 1 GB limit.",
       "Infinite recursion.", "Cyclic String()/Error() calling itself via fmt.", "Very deep recursion on large input.",
       "The repeating frames."),
    _e("go", "integer divide by zero", "Integer division or modulo by zero.",
       "Empty input count used as a divisor.", "Unset config value.", "Duration/size of zero.", "The divisor before the failing line."),
    # ------------------------------------------------------------------ Rust
    _e("rust", "called `Option::unwrap()` on a `None` value|unwrap on None", "unwrap() was called on None.",
       "A lookup (get, find, first) returned None.", "Optional config or env var missing.", "Parsing step that can fail treated as infallible.",
       "The src/ line in the panic location; replace with ?/ok_or/expect with context."),
    _e("rust", "called `Result::unwrap()` on an `Err` value|unwrap on Err|expect failed", "unwrap()/expect() was called on Err.",
       "I/O, parse or network error ignored.", "Missing file or bad environment.", "Deserialisation failure.",
       "The Err value printed in the message (it is the real error)."),
    _e("rust", "index out of bounds", "A slice/Vec index is >= len.",
       "Empty Vec indexed at 0.", "Off-by-one.", "Index computed from untrusted data.", "'the len is X but the index is Y' in the message."),
    _e("rust", "already borrowed|already mutably borrowed|BorrowMutError|BorrowError", "RefCell runtime borrow rules were violated.",
       "A borrow still alive across a call that borrows again.", "Re-entrant callback.", "Holding a guard in a long-lived binding.",
       "Narrow borrow scopes; use try_borrow_mut to find the conflict."),
    _e("rust", "attempt to add with overflow|attempt to subtract with overflow|attempt to multiply with overflow", "Integer overflow (debug builds panic).",
       "Unsigned subtraction going below 0.", "Counter or size growing past the type width.", "Casting between widths.",
       "Use checked_/saturating_/wrapping_ arithmetic deliberately."),
    _e("rust", "attempt to divide by zero", "Integer division or remainder by zero.",
       "Empty collection length as divisor.", "Unvalidated input.", "Uninitialised config.", "The divisor at the panic location."),
    _e("rust", "explicit panic|assertion failed|assertion `left == right` failed|not yet implemented|unreachable", "panic!/assert!/todo!/unreachable! was reached.",
       "A broken invariant.", "A stubbed code path.", "A failing test assertion (left/right values are printed).",
       "The message and the left/right values."),
    _e("rust", "stack overflow|has overflowed its stack", "The thread stack was exhausted (abort, no backtrace).",
       "Unbounded recursion.", "Huge arrays on the stack.", "Deeply nested data in recursive Drop/Debug.",
       "Run in a debugger; move large data to the heap or iterate."),
    # ------------------------------------------------------------------ .NET
    _e("dotnet", "NullReferenceException", "A null reference was dereferenced.",
       "Object not created or injected.", "Method returned null (FirstOrDefault, dictionary lookup, JSON deserialisation).",
       "Uninitialised field or event with no subscribers.", "The line in the top application frame and each dot-chained member on it."),
    _e("dotnet", "InvalidOperationException", "The object state does not allow the call.",
       "Sequence contains no elements (First/Single on empty).", "Collection modified during enumeration.",
       "Calling a method before initialisation or after disposal.", "The message text; it names the state."),
    _e("dotnet", "ArgumentNullException|ArgumentException|ArgumentOutOfRangeException", "A method received an invalid argument.",
       "Null passed where not allowed (paramName in the message).", "Value outside the valid range.", "Caller bug or missing validation.",
       "The paramName and the caller one frame down."),
    _e("dotnet", "IndexOutOfRangeException|KeyNotFoundException", "Array index out of bounds / dictionary key missing.",
       "Off-by-one.", "Empty collection.", "Key never added or different casing.", "Index/key and the collection's contents."),
    _e("dotnet", "InvalidCastException|FormatException", "Wrong cast / a string was not in the expected format.",
       "Boxed value of another type.", "Culture-specific number/date formats.", "Unvalidated user input.",
       "The source type and the text being parsed."),
    _e("dotnet", "TaskCanceledException|OperationCanceledException", "An operation was cancelled or timed out.",
       "HttpClient timeout elapsed.", "CancellationToken triggered (request aborted, shutdown).", "Linked token cancelled by a sibling.",
       "Whether a token or a timeout caused it (inner TimeoutException)."),
    _e("dotnet", "AggregateException", "One or more tasks failed; the real errors are in InnerExceptions.",
       "Task.Wait()/Result on a faulted task.", "Task.WhenAll with several failures.", "Parallel.ForEach body throwing.",
       "Inspect each inner exception; await instead of blocking."),
    _e("dotnet", "StackOverflowException", "The process ran out of stack and was terminated.",
       "Unbounded recursion.", "Property getter calling itself.", "Cyclic ToString/serialisation.", "The repeating frames."),
    _e("dotnet", "DivideByZeroException|OverflowException", "Integer division by zero / arithmetic overflow in a checked context.",
       "Empty input count as a divisor.", "Narrowing conversion.", "Unvalidated values.", "The operands at the failing line."),
    _e("dotnet", "ObjectDisposedException|TimeoutException", "Use of a disposed object / an operation exceeded its timeout.",
       "Using a DbContext, stream or HttpClient after dispose (scope ended).", "Async work outliving its scope.", "Slow dependency.",
       "Who disposed the object, and the configured timeout."),
    _e("dotnet", "FileNotFoundException|DirectoryNotFoundException|UnauthorizedAccessException", "File missing / path missing / access denied.",
       "Wrong working directory or publish layout.", "Permissions of the service account.", "File locked by another process.",
       "The full path in the message and the account the process runs as."),
)


def _norm(name: str) -> str:
    n = name.strip()
    for sep in ("::", "."):
        if sep in n and not n.startswith("called ") and " " not in n:
            n = n.rsplit(sep, 1)[-1]
    return n.lower()


def lookup(name: str, language: str | None) -> list[Entry]:
    key = _norm(name)
    lang = (language or "").strip().lower() or None
    aliases = {"js": "node", "javascript": "node", "typescript": "node", "ts": "node", "kotlin": "java", "csharp": "dotnet", "c#": "dotnet", ".net": "dotnet", "py": "python", "golang": "go"}
    lang = aliases.get(lang, lang) if lang else None
    exact: list[Entry] = []
    partial: list[Entry] = []
    for e in TABLE:
        if lang and e.language != lang:
            continue
        for nm in e.names:
            n = nm.lower()
            nk = _norm(nm)
            if key in (n, nk):
                exact.append(e)
                break
            if (len(key) >= 6 and key in n) or (len(n) >= 6 and n in key):
                partial.append(e)
                break
    return exact or partial


def render(entries: list[Entry]) -> str:
    out: list[str] = []
    for e in entries:
        out.append(f"[{e.language}] {e.names[0]}")
        out.append(f"  Means: {e.meaning}")
        out.append("  Most common causes:")
        for k, c in enumerate(e.causes, 1):
            out.append(f"    {k}. {c}")
        out.append(f"  Check first: {e.check}")
    return "\n".join(out)


def languages() -> list[str]:
    return sorted({e.language for e in TABLE})
