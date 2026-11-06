"""Java / Kotlin stack trace fixtures (HotSpot format; <T> is a tab)."""

from __future__ import annotations

import pytest
from helpers import check, fx, parse

CASES: dict[str, tuple[str, dict]] = {}


def case(name: str, text: str, **exp: object) -> None:
    CASES[name] = (fx(text), exp)


case("npe_helpful_message", r"""
    Exception in thread "main" java.lang.NullPointerException: Cannot invoke "String.length()" because "s" is null
    <T>at com.acme.Util.len(Util.java:12)
    <T>at com.acme.Main.main(Main.java:7)
    """, lang="java", top="java.lang.NullPointerException", msg="because", origin=("Util.len", "Util.java", 12),
     frames=2)

case("plain_header_no_thread", r"""
    java.lang.IllegalStateException: not initialised
    <T>at com.acme.svc.Service.call(Service.java:55)
    <T>at com.acme.svc.Runner.run(Runner.java:20)
    <T>at java.base/java.lang.Thread.run(Thread.java:833)
    """, lang="java", top="java.lang.IllegalStateException", origin=("Service.call", "Service.java", 55),
     kinds={0: "app", 1: "app", 2: "stdlib"})

case("caused_by_with_more_elision", r"""
    java.lang.RuntimeException: failed to process order 42
    <T>at com.acme.OrderService.process(OrderService.java:81)
    <T>at com.acme.OrderController.post(OrderController.java:30)
    <T>at com.acme.Main.main(Main.java:10)
    Caused by: java.sql.SQLException: Connection refused
    <T>at com.acme.Db.connect(Db.java:19)
    <T>at com.acme.OrderService.process(OrderService.java:79)
    <T>... 2 more
    """, lang="java", top="java.lang.RuntimeException", root="java.sql.SQLException", chain=2,
     origin=("Db.connect", "Db.java", 19), frames=4)

case("two_caused_by_levels", r"""
    org.springframework.beans.factory.BeanCreationException: Error creating bean 'dataSource'
    <T>at org.springframework.beans.factory.support.AbstractAutowireCapableBeanFactory.doCreateBean(AbstractAutowireCapableBeanFactory.java:628)
    <T>at com.acme.App.main(App.java:14)
    Caused by: java.lang.IllegalArgumentException: url must not be null
    <T>at org.springframework.util.Assert.notNull(Assert.java:201)
    <T>at com.acme.config.DbConfig.dataSource(DbConfig.java:27)
    <T>... 1 more
    Caused by: java.lang.NullPointerException
    <T>at com.acme.config.DbConfig.url(DbConfig.java:33)
    <T>at com.acme.config.DbConfig.dataSource(DbConfig.java:26)
    <T>... 1 more
    """, lang="java", chain=3, root="java.lang.NullPointerException", origin=("DbConfig.url", "DbConfig.java", 33),
     top="org.springframework.beans.factory.BeanCreationException")

case("suppressed_try_with_resources", r"""
    java.lang.Exception: primary
    <T>at com.acme.Res.use(Res.java:10)
    <T>at com.acme.Main.main(Main.java:5)
    <T>Suppressed: java.io.IOException: close failed
    <T><T>at com.acme.Res.close(Res.java:20)
    <T><T>at com.acme.Main.main(Main.java:4)
    """, lang="java", top="java.lang.Exception", origin=("Res.use", "Res.java", 10))

case("reflection_native_method_frames", r"""
    java.lang.reflect.InvocationTargetException
    <T>at java.base/jdk.internal.reflect.NativeMethodAccessorImpl.invoke0(Native Method)
    <T>at java.base/jdk.internal.reflect.NativeMethodAccessorImpl.invoke(NativeMethodAccessorImpl.java:77)
    <T>at java.base/java.lang.reflect.Method.invoke(Method.java:568)
    <T>at com.acme.Plugin.load(Plugin.java:40)
    Caused by: java.lang.ArithmeticException: / by zero
    <T>at com.acme.Plugin.compute(Plugin.java:51)
    <T>... 1 more
    """, lang="java", root="java.lang.ArithmeticException", origin=("Plugin.compute", "Plugin.java", 51))

case("spring_wrapped_servlet", r"""
    org.springframework.web.util.NestedServletException: Request processing failed; nested exception is java.lang.NumberFormatException: For input string: "abc"
    <T>at org.springframework.web.servlet.FrameworkServlet.processRequest(FrameworkServlet.java:1014)
    <T>at javax.servlet.http.HttpServlet.service(HttpServlet.java:670)
    <T>at org.apache.catalina.core.StandardWrapper.service(StandardWrapper.java:231)
    Caused by: java.lang.NumberFormatException: For input string: "abc"
    <T>at java.base/java.lang.NumberFormatException.forInputString(NumberFormatException.java:67)
    <T>at java.base/java.lang.Integer.parseInt(Integer.java:661)
    <T>at com.acme.web.ItemController.get(ItemController.java:33)
    <T>at java.base/jdk.internal.reflect.DirectMethodHandleAccessor.invoke(DirectMethodHandleAccessor.java:103)
    <T>... 3 more
    """, lang="java", root="java.lang.NumberFormatException", origin=("ItemController.get", "ItemController.java", 33),
     kinds={0: "stdlib", 2: "app"})

case("kotlin_coroutines", r"""
    Exception in thread "DefaultDispatcher-worker-1" java.lang.IllegalStateException: no user
    <T>at com.acme.app.UserRepo$load$2.invokeSuspend(UserRepo.kt:44)
    <T>at kotlin.coroutines.jvm.internal.BaseContinuationImpl.resumeWith(ContinuationImpl.kt:33)
    <T>at kotlinx.coroutines.DispatchedTask.run(DispatchedTask.kt:108)
    <T>at kotlinx.coroutines.scheduling.CoroutineScheduler.runSafely(CoroutineScheduler.kt:584)
    """, lang="java", top="java.lang.IllegalStateException", origin=("UserRepo", "UserRepo.kt", 44),
     kinds={0: "app", 1: "stdlib", 2: "framework"})

case("logback_with_packaging_suffix", r"""
    2024-03-04 10:11:12.345 ERROR 1 --- [nio-8080-exec-1] c.a.web.ErrorHandler : Unhandled
    java.lang.IllegalArgumentException: bad id
    <T>at com.acme.web.Api.get(Api.java:18) ~[classes!/:1.0.0]
    <T>at java.base/jdk.internal.reflect.DirectMethodHandleAccessor.invoke(DirectMethodHandleAccessor.java:103) ~[na:na]
    <T>at org.springframework.web.method.support.InvocableHandlerMethod.doInvoke(InvocableHandlerMethod.java:205) ~[spring-web-6.1.2.jar!/:6.1.2]
    2024-03-04 10:11:12.400 INFO 1 --- [main] c.a.Main : next
    """, lang="java", top="java.lang.IllegalArgumentException", origin=("Api.get", "Api.java", 18))

case("app_classloader_prefix_junit", r"""
    org.opentest4j.AssertionFailedError: expected: <3> but was: <4>
    <T>at app//org.junit.jupiter.api.AssertionFailureBuilder.build(AssertionFailureBuilder.java:151)
    <T>at app//org.junit.jupiter.api.AssertEquals.assertEquals(AssertEquals.java:145)
    <T>at app//com.acme.CalcTest.adds(CalcTest.java:14)
    <T>at java.base@17.0.9/java.lang.reflect.Method.invoke(Method.java:568)
    """, lang="java", top="org.opentest4j.AssertionFailedError", origin=("CalcTest.adds", "CalcTest.java", 14))

case("stack_overflow_repeated", r"""
    Exception in thread "main" java.lang.StackOverflowError
    <T>at com.acme.Rec.f(Rec.java:5)
    <T>at com.acme.Rec.f(Rec.java:5)
    <T>at com.acme.Rec.f(Rec.java:5)
    <T>at com.acme.Rec.f(Rec.java:5)
    <T>... 1020 more
    """, lang="java", top="java.lang.StackOverflowError", origin=("Rec.f", "Rec.java", 5))

case("multiline_message", r"""
    javax.persistence.PersistenceException: could not execute statement
    SQL: insert into users (id) values (?)
    <T>at org.hibernate.internal.ExceptionConverterImpl.convert(ExceptionConverterImpl.java:154)
    <T>at com.acme.dao.UserDao.save(UserDao.java:61)
    """, lang="java", top="javax.persistence.PersistenceException", msg="insert into", origin=("UserDao.save", "UserDao.java", 61))

case("lambda_and_unknown_source", r"""
    java.lang.RuntimeException: in stream
    <T>at com.acme.Job.lambda$run$0(Job.java:22)
    <T>at java.base/java.util.ArrayList.forEach(ArrayList.java:1511)
    <T>at com.acme.Job$$Lambda$14/0x0000000800c03000.accept(Unknown Source)
    <T>at com.acme.Job.run(Job.java:21)
    """, lang="java", top="java.lang.RuntimeException", origin=("Job.lambda$run$0", "Job.java", 22), frames=4)

case("truncated_header_only", r"""
    Exception in thread "main" java.lang.RuntimeException: cut off here
    """, lang="java", partial=True, top="java.lang.RuntimeException")

case("scala_and_groovy_files", r"""
    java.lang.ClassCastException: class java.lang.String cannot be cast to class java.lang.Integer
    <T>at com.acme.Calc$.run(Calc.scala:30)
    <T>at com.acme.Main$.main(Main.scala:8)
    <T>at com.acme.Main.main(Main.scala)
    """, lang="java", top="java.lang.ClassCastException", origin=("Calc$.run", "Calc.scala", 30))

case("embedded_header_in_log_line", r"""
    12:00:01.123 [main] ERROR com.acme.Boot - Startup failed: java.io.FileNotFoundException: /etc/x.conf (No such file or directory)
    <T>at java.base/java.io.FileInputStream.open0(Native Method)
    <T>at com.acme.Boot.load(Boot.java:12)
    """, lang="java", top="java.io.FileNotFoundException", origin=("Boot.load", "Boot.java", 12))


@pytest.mark.parametrize("name", sorted(CASES))
def test_java_fixture(name: str) -> None:
    text, exp = CASES[name]
    check(text, **exp)  # type: ignore[arg-type]


def test_there_are_at_least_twelve_java_fixtures() -> None:
    assert len(CASES) >= 12


def test_more_elision_is_reconstructed_from_the_enclosing_trace() -> None:
    t = parse(CASES["caused_by_with_more_elision"][0])
    cause = t.chain[1]
    assert cause.elided == 2
    shared = [f for f in cause.frames if f.inherited]
    assert [f.function for f in shared] == ["com.acme.OrderController.post", "com.acme.Main.main"]


def test_caused_by_relations() -> None:
    t = parse(CASES["two_caused_by_levels"][0])
    assert [e.via for e in t.chain] == [None, "cause", "cause"]


def test_suppressed_is_attached_not_chained() -> None:
    t = parse(CASES["suppressed_try_with_resources"][0])
    assert len(t.chain) == 1
    assert [s.type for s in t.top.suppressed] == ["java.io.IOException"]
    assert t.top.suppressed[0].frames[0].function == "com.acme.Res.close"
    assert len(t.top.frames) == 2


def test_native_method_frame() -> None:
    t = parse(CASES["reflection_native_method_frames"][0])
    assert t.top.frames[0].native and t.top.frames[0].file is None


def test_module_prefix_is_split_off() -> None:
    t = parse(CASES["plain_header_no_thread"][0])
    assert t.top.frames[2].module == "java.base"
    assert t.top.frames[2].function == "java.lang.Thread.run"


def test_path_hint_from_package() -> None:
    t = parse(CASES["npe_helpful_message"][0])
    assert t.top.frames[0].path_hint == "com/acme/Util.java"


def test_thread_name_is_kept() -> None:
    t = parse(CASES["kotlin_coroutines"][0])
    assert t.top.thread == "DefaultDispatcher-worker-1"


def test_log_line_after_trace_is_excluded() -> None:
    t = parse(CASES["logback_with_packaging_suffix"][0])
    assert t.end_line == 5 - 1 or t.end_line <= 6
    assert len(t.top.frames) == 3
