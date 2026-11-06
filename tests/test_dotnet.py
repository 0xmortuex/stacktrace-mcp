"""C# / .NET Exception.ToString() fixtures (.NET Framework, Core and 5-9 layouts)."""

from __future__ import annotations

import pytest
from helpers import check, fx, parse

CASES: dict[str, tuple[str, dict]] = {}


def case(name: str, text: str, **exp: object) -> None:
    CASES[name] = (fx(text), exp)


case("null_reference_windows_paths", r"""
    System.NullReferenceException: Object reference not set to an instance of an object.
       at MyApp.Services.UserService.GetName(Int32 id) in C:\src\MyApp\Services\UserService.cs:line 42
       at MyApp.Program.Main(String[] args) in C:\src\MyApp\Program.cs:line 12
    """, lang="dotnet", top="System.NullReferenceException", msg="Object reference",
     origin=("UserService.GetName", "UserService.cs", 42), frames=2)

case("unhandled_exception_prefix_linq", r"""
    Unhandled exception. System.InvalidOperationException: Sequence contains no elements
       at System.Linq.ThrowHelper.ThrowNoElementsException()
       at System.Linq.Enumerable.First[TSource](IEnumerable`1 source)
       at MyApp.Report.Latest(IEnumerable`1 rows) in /src/MyApp/Report.cs:line 19
       at MyApp.Program.Main() in /src/MyApp/Program.cs:line 8
    """, lang="dotnet", top="System.InvalidOperationException", origin=("Report.Latest", "Report.cs", 19),
     kinds={0: "stdlib", 1: "stdlib", 2: "app"})

case("inner_exception_arrow_chain", r"""
    System.InvalidOperationException: outer failed ---> System.IO.IOException: disk full
       at MyApp.Store.Write(String path) in /src/MyApp/Store.cs:line 31
       --- End of inner exception stack trace ---
       at MyApp.Store.Save() in /src/MyApp/Store.cs:line 22
       at MyApp.Program.Main() in /src/MyApp/Program.cs:line 5
    """, lang="dotnet", top="System.InvalidOperationException", root="System.IO.IOException", chain=2,
     origin=("Store.Write", "Store.cs", 31), frames=1)

case("three_level_inner_chain", r"""
    System.Exception: top ---> System.ArgumentException: mid ---> System.FormatException: leaf
       at MyApp.Parse.Run(String s) in /src/Parse.cs:line 9
       --- End of inner exception stack trace ---
       at MyApp.Parse.Check(String s) in /src/Parse.cs:line 15
       --- End of inner exception stack trace ---
       at MyApp.Program.Main() in /src/Program.cs:line 3
    """, lang="dotnet", top="System.Exception", root="System.FormatException", chain=3,
     origin=("Parse.Run", "Parse.cs", 9))

case("aggregate_exception_inner_numbers", r"""
    System.AggregateException: One or more errors occurred. (boom1) (boom2)
     ---> System.InvalidOperationException: boom1
       at MyApp.Jobs.A() in /src/Jobs.cs:line 10
       --- End of inner exception stack trace ---
     ---> (Inner Exception #1) System.ArgumentException: boom2
       at MyApp.Jobs.B() in /src/Jobs.cs:line 20
       --- End of inner exception stack trace ---
       at System.Threading.Tasks.Task.WaitAll(Task[] tasks)
       at MyApp.Program.Main() in /src/Program.cs:line 6
    """, lang="dotnet", top="System.AggregateException")

case("async_state_machine_frames", r"""
    System.Net.Http.HttpRequestException: Connection refused (localhost:5001)
     ---> System.Net.Sockets.SocketException (111): Connection refused
       at System.Net.Sockets.Socket.AwaitableSocketAsyncEventArgs.ThrowException(SocketError error, CancellationToken cancellationToken)
       at System.Threading.Tasks.ValueTask`1.get_Result()
       --- End of inner exception stack trace ---
       at System.Net.Http.HttpConnectionPool.ConnectAsync(HttpRequestMessage request, Boolean async, CancellationToken cancellationToken)
       --- End of stack trace from previous location ---
       at MyApp.Client.<GetAsync>d__3.MoveNext() in /src/Client.cs:line 27
    """, lang="dotnet", top="System.Net.Http.HttpRequestException", root="System.Net.Sockets.SocketException",
     chain=2)

case("aspnetcore_framework_frames", r"""
    System.ArgumentNullException: Value cannot be null. (Parameter 'name')
       at MyApp.Controllers.HomeController.Greet(String name) in /src/Controllers/HomeController.cs:line 18
       at Microsoft.AspNetCore.Mvc.Infrastructure.ActionMethodExecutor.SyncActionResultExecutor.Execute(ActionContext actionContext, IActionResultTypeMapper mapper, ObjectMethodExecutor executor, Object controller, Object[] arguments)
       at Microsoft.AspNetCore.Mvc.Infrastructure.ControllerActionInvoker.<InvokeActionMethodAsync>g__Awaited|12_0(ControllerActionInvoker invoker, ValueTask`1 actionResultValueTask)
    """, lang="dotnet", top="System.ArgumentNullException", msg="Parameter 'name'",
     origin=("HomeController.Greet", "HomeController.cs", 18), kinds={0: "app", 1: "framework", 2: "framework"})

case("linux_paths_and_dotnet_runtime_src", r"""
    System.IndexOutOfRangeException: Index was outside the bounds of the array.
       at MyApp.Grid.Cell(Int32 x, Int32 y) in /home/runner/work/app/src/Grid.cs:line 14
       at MyApp.Program.<>c.<Main>b__0_0(Int32 i) in /home/runner/work/app/src/Program.cs:line 6
       at System.Threading.Tasks.Parallel.<>c__DisplayClass19_0`2.<ForWorker>b__1(RangeWorker& currentWorker, Int64 timeout, Boolean& replicationDelegateYieldedBeforeCompletion)
    """, lang="dotnet", top="System.IndexOutOfRangeException", origin=("Grid.Cell", "Grid.cs", 14),
     kinds={0: "app", 1: "app", 2: "stdlib"})

case("frames_without_pdb_info", r"""
    System.InvalidCastException: Unable to cast object of type 'System.String' to type 'System.Int32'.
       at MyApp.Convert.ToInt(Object o)
       at MyApp.Program.Main()
    """, lang="dotnet", top="System.InvalidCastException", origin=("Convert.ToInt", "", None))

case("ef_core_three_levels", r"""
    Microsoft.EntityFrameworkCore.DbUpdateException: An error occurred while saving the entity changes. See the inner exception for details.
     ---> Microsoft.Data.SqlClient.SqlException (0x80131904): Violation of PRIMARY KEY constraint 'PK_Users'.
       at Microsoft.Data.SqlClient.SqlConnection.OnError(SqlException exception, Boolean breakConnection, Action`1 wrapCloseInAction)
       at Microsoft.Data.SqlClient.SqlCommand.EndExecuteNonQueryInternal(IAsyncResult asyncResult)
       --- End of inner exception stack trace ---
       at Microsoft.EntityFrameworkCore.Update.ReaderModificationCommandBatch.ExecuteAsync(IRelationalConnection connection, CancellationToken cancellationToken)
       at MyApp.Data.UserRepo.AddAsync(User u) in /src/Data/UserRepo.cs:line 33
    """, lang="dotnet", top="Microsoft.EntityFrameworkCore.DbUpdateException", root="Microsoft.Data.SqlClient.SqlException",
     chain=2)

case("type_initialization_exception", r"""
    System.TypeInitializationException: The type initializer for 'MyApp.Settings' threw an exception.
     ---> System.IO.FileNotFoundException: Could not find file '/app/appsettings.json'.
       at Interop.ThrowExceptionForIoErrno(ErrorInfo errorInfo, String path, Boolean isDirError)
       at MyApp.Settings..cctor() in /src/Settings.cs:line 8
       --- End of inner exception stack trace ---
       at MyApp.Program.Main() in /src/Program.cs:line 4
    """, lang="dotnet", root="System.IO.FileNotFoundException", chain=2, origin=("Settings..cctor", "Settings.cs", 8))

case("task_canceled", r"""
    System.Threading.Tasks.TaskCanceledException: The request was canceled due to the configured HttpClient.Timeout of 100 seconds elapsing.
     ---> System.TimeoutException: The operation was canceled.
       at System.Net.Http.HttpClient.HandleFailure(Exception e, Boolean telemetryStarted, HttpResponseMessage response, CancellationTokenSource cts, CancellationToken cancellationToken, CancellationTokenSource pendingRequestsCts)
       --- End of inner exception stack trace ---
       at MyApp.Api.CallAsync() in /src/Api.cs:line 40
    """, lang="dotnet", top="System.Threading.Tasks.TaskCanceledException", root="System.TimeoutException", chain=2)

case("key_not_found_in_lambda", r"""
    System.Collections.Generic.KeyNotFoundException: The given key 'tenant-9' was not present in the dictionary.
       at System.Collections.Generic.Dictionary`2.get_Item(TKey key)
       at MyApp.Tenants.<>c__DisplayClass2_0.<Lookup>b__0(Order o) in /src/Tenants.cs:line 11
       at System.Linq.Enumerable.SelectListIterator`2.MoveNext()
    """, lang="dotnet", top="System.Collections.Generic.KeyNotFoundException", origin=("Tenants", "Tenants.cs", 11))

case("truncated_header_only", r"""
    System.InvalidOperationException: cut off
    """, lang="unknown", partial=True, top="System.InvalidOperationException")

case("serilog_multiline_message", r"""
    [ERR] Unhandled
    System.Exception: line one
    line two
       at MyApp.X.Run() in /src/X.cs:line 5
    [INF] next
    """, lang="dotnet", top="System.Exception", msg="line two", origin=("X.Run", "X.cs", 5))


@pytest.mark.parametrize("name", sorted(CASES))
def test_dotnet_fixture(name: str) -> None:
    text, exp = CASES[name]
    check(text, **exp)  # type: ignore[arg-type]


def test_there_are_at_least_twelve_dotnet_fixtures() -> None:
    assert len(CASES) >= 12


def test_inner_exception_frames_come_first_per_exception() -> None:
    t = parse(CASES["inner_exception_arrow_chain"][0])
    assert t.chain[0].frames[0].function == "MyApp.Store.Save"
    assert t.chain[1].frames[0].function == "MyApp.Store.Write"


def test_aggregate_children() -> None:
    t = parse(CASES["aggregate_exception_inner_numbers"][0])
    kids = [c[0].type for c in t.top.group]
    assert kids == ["System.InvalidOperationException", "System.ArgumentException"]
    assert len(t.top.frames) == 2


def test_async_flag_on_state_machine_frame() -> None:
    t = parse(CASES["async_state_machine_frames"][0])
    assert t.chain[0].frames[-1].is_async


def test_line_marker_forms() -> None:
    t = parse(CASES["null_reference_windows_paths"][0])
    assert t.top.frames[0].file == r"C:\src\MyApp\Services\UserService.cs"
    assert t.top.frames[0].line == 42
